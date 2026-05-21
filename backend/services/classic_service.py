"""
services/classic_service.py

Classic Room Service - Question selection, concept management, IRT updates.

Key Features:
  - Concept selection (weighted by mastery_gap, recency, repeat_due)
  - Question selection using IRT ZPD targeting
  - Repeat queue management (25% wrong â†’ repeat queue, 1% correct)
  - Session state management with locking
"""

import json
import random
import uuid
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_, func, or_, update as sqlalchemy_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from config import (
    POINTS_BASE_AWARD,
    POINTS_TIME_BONUS_DIVISOR,
    POINTS_HINT_PENALTY,
    POINTS_WRONG_PENALTY,
    compute_level,
)

try:
    from database.models import QuestionBank, UserResponse, User
    from database.challenge_models import ChallengeAnswer, ChallengeSession
    from database.pvp_models import PvPMatch, PvPMatchAnswer
    from database.concept_models import (
        Concept,
        ClassicSession,
        QuestionConcept,
        UserConceptTheta,
        UserConceptRepeatQueue,
    )
    from database.irt import target_beta_range, beta_to_difficulty
    from services.concept_irt import ConceptIRT
    from services.session import SessionService
except ImportError:
    from .database.models import QuestionBank, UserResponse, User
    from .database.challenge_models import ChallengeAnswer, ChallengeSession
    from .database.pvp_models import PvPMatch, PvPMatchAnswer
    from .database.concept_models import (
        Concept,
        ClassicSession,
        QuestionConcept,
        UserConceptTheta,
        UserConceptRepeatQueue,
    )
    from .database.irt import target_beta_range, beta_to_difficulty
    from .concept_irt import ConceptIRT
    from .session import SessionService


logger = logging.getLogger(__name__)


class ClassicService:
    """Classic Room quiz service."""

    MAX_QUESTIONS_PER_SESSION = 10
    COLD_START_THRESHOLD = 5  # Responses below this = learning mode
    NON_CLASSIC_SOURCES = ("challenge_llm", "custom_llm")

    # Spaced repetition
    WRONG_ANSWER_REPEAT_PROBABILITY = 0.25
    CORRECT_ANSWER_REPEAT_PROBABILITY = 0.01
    REPEAT_DUE_SESSIONS = 7  # Show repeat after 7 more sessions

    @staticmethod
    def _compute_points_delta(
        *,
        correct: bool,
        time_taken_seconds: int,
        used_hint: bool,
    ) -> int:
        """Compute per-answer points using the same rules as ClassicRoom UI."""
        if correct:
            remaining_seconds = max(0, 30 - int(time_taken_seconds or 0))
            delta = int(POINTS_BASE_AWARD) + int(remaining_seconds // int(POINTS_TIME_BONUS_DIVISOR))
        else:
            delta = -int(POINTS_WRONG_PENALTY)

        if used_hint:
            delta -= int(POINTS_HINT_PENALTY)

        return int(delta)

    @staticmethod
    async def get_user_seen_question_ids(
        db: AsyncSession,
        user_id: uuid.UUID,
        topic: str,
        asked_question_ids: list[str] | None = None,
        extra_question_ids: list[str] | None = None,
        history_limit: int = 5000,
    ) -> set[uuid.UUID]:
        """Return question IDs already seen by this user for the topic/session context."""
        seen_ids: set[uuid.UUID] = set()

        for raw in (asked_question_ids or []) + (extra_question_ids or []):
            try:
                seen_ids.add(uuid.UUID(str(raw)))
            except ValueError:
                continue

        history_stmt = (
            select(UserResponse.question_id)
            .where(UserResponse.user_id == user_id)
            .order_by(UserResponse.created_at.desc())
            .limit(history_limit)
        )
        if topic != "mix":
            history_stmt = history_stmt.where(func.lower(UserResponse.topic) == topic.lower())

        history_ids = (await db.execute(history_stmt)).scalars().all()
        for qid in history_ids:
            try:
                seen_ids.add(uuid.UUID(str(qid)))
            except ValueError:
                continue

        cross_topic = topic.lower() == "mix"

        challenge_stmt = (
            select(ChallengeAnswer.question_id)
            .join(ChallengeSession, ChallengeSession.id == ChallengeAnswer.session_id)
            .where(ChallengeSession.user_id == user_id)
        )
        if not cross_topic:
            challenge_stmt = challenge_stmt.where(func.lower(ChallengeSession.topic) == topic.lower())

        challenge_ids = (await db.execute(challenge_stmt)).scalars().all()
        for qid in challenge_ids:
            try:
                seen_ids.add(uuid.UUID(str(qid)))
            except ValueError:
                continue

        pvp_stmt = (
            select(PvPMatchAnswer.question_id)
            .join(PvPMatch, PvPMatch.id == PvPMatchAnswer.match_id)
            .where(
                or_(
                    PvPMatch.user1_id == user_id,
                    PvPMatch.user2_id == user_id,
                )
            )
        )
        if not cross_topic:
            pvp_stmt = pvp_stmt.where(func.lower(PvPMatch.topic) == topic.lower())

        pvp_ids = (await db.execute(pvp_stmt)).scalars().all()
        for qid in pvp_ids:
            try:
                seen_ids.add(uuid.UUID(str(qid)))
            except ValueError:
                continue

        return seen_ids

    @staticmethod
    async def start_session(
        db: AsyncSession,
        user_id: uuid.UUID,
        topic: str,
        session_service: SessionService,
    ) -> dict:
        """
        Start a Classic Room session.

        1. Select 5 concepts based on weighted scoring
        2. Get user's current theta for each concept
        3. Store session state in Redis
        4. Select first question

        Returns: {session_id, first_question, session_stats}
        """
        session_id = uuid.uuid4()

        # Select concepts for session (weighted scoring)
        concepts = await ClassicService.select_concepts_for_session(
            db, user_id, topic, n_concepts=5
        )
        concept_ids = [c.id for c in concepts]

        if not concept_ids:
            logger.warning(
                "Classic session started without concept matches; using question fallback path user=%s topic=%s",
                str(user_id)[:8],
                topic,
            )

        # Persist a classic session row so dashboard room progress reflects activity.
        db.add(
            ClassicSession(
                id=session_id,
                user_id=user_id,
                topic=topic,
                questions_answered=0,
                correct_count=0,
                concepts=[str(cid) for cid in concept_ids],
            )
        )
        await db.commit()

        # Get user's theta snapshot for these concepts (if any)
        theta_snapshot = {}
        if concept_ids:
            theta_snapshot = await ConceptIRT.get_user_concept_thetas(
                db, user_id, concept_ids
            )

        # Store in Redis session
        session_state = {
            "user_id": str(user_id),
            "topic": topic,
            "concept_ids": [str(cid) for cid in concept_ids],
            "theta_snapshot": theta_snapshot,
            "questions_asked": [],
            "current_question_id": None,
        }
        await session_service.store_session_state(str(session_id), session_state)

        # Select first question
        first_question = await ClassicService.select_next_question(
            db,
            user_id,
            topic,
            concept_ids,
            asked_question_ids=[],
            theta_snapshot=theta_snapshot,
        )

        # Store shuffled options + correct answer in session
        if first_question:
            await session_service.set_current_question(
                str(session_id),
                {
                    "id": first_question["id"],
                    "correct_answer": first_question["correct_answer"],
                    "shuffled_options": first_question["options"],
                    "correct_index_shuffled": first_question["correct_index"],
                    "question_sent_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                },
            )

        return {
            "session_id": str(session_id),
            "first_question": first_question,
            "session_stats": {"questions_answered": 0, "correct_count": 0},
        }

    @staticmethod
    async def select_concepts_for_session(
        db: AsyncSession, user_id: uuid.UUID, topic: str, n_concepts: int = 5
    ) -> list[Concept]:
        """
        Select N concepts using weighted scoring:

        Score = 0.4*mastery_gap + 0.3*recency_bonus + 0.2*repeat_due + 0.1*zpd_fit

        Where:
          mastery_gap = (3.0 - theta) / 6.0    # Higher for lower theta
          recency_bonus = min(days_since / 14, 1.0)  # Higher for stale concepts
          repeat_due = 1.0 if in_repeat_queue else 0.0
          zpd_fit â‰ˆ 0.5
        """
        # Get all concepts for topic (case-insensitive); "mix" can draw from any topic.
        normalized_topic = (topic or "mix").strip().lower()
        stmt = select(Concept)
        if normalized_topic != "mix":
            stmt = stmt.where(func.lower(Concept.topic) == normalized_topic)
        result = await db.execute(stmt)
        concepts = result.scalars().all()

        scored_concepts = []
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for concept in concepts:
            # Get theta record
            theta_stmt = select(UserConceptTheta).where(
                (UserConceptTheta.user_id == user_id)
                & (UserConceptTheta.concept_id == concept.id)
            )
            theta_result = await db.execute(theta_stmt)
            theta_record = theta_result.scalar_one_or_none()

            if not theta_record:
                # New concept: start with theta=0.0
                theta = 0.0
                days_since = 30
                repeat_due = 0.0
            else:
                theta = theta_record.theta
                days_since = (
                    (now - theta_record.last_updated).days
                    if theta_record.last_updated
                    else 30
                )

                # Check repeat queue
                repeat_stmt = select(UserConceptRepeatQueue).where(
                    (UserConceptRepeatQueue.user_id == user_id)
                    & (UserConceptRepeatQueue.concept_id == concept.id)
                )
                repeat_result = await db.execute(repeat_stmt)
                repeat_due = 1.0 if repeat_result.scalars().first() else 0.0

            # Calculate score
            mastery_gap = (3.0 - theta) / 6.0
            recency_bonus = min(days_since / 14.0, 1.0)
            zpd_fit = 0.5

            score = (
                0.4 * mastery_gap
                + 0.3 * recency_bonus
                + 0.2 * repeat_due
                + 0.1 * zpd_fit
            )
            scored_concepts.append((concept, score))

        # Sort and return top n
        scored_concepts.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored_concepts[:n_concepts]]

    @staticmethod
    async def select_next_question(
        db: AsyncSession,
        user_id: uuid.UUID,
        topic: str,
        concept_ids: list[uuid.UUID],
        asked_question_ids: list[str],
        theta_snapshot: dict[str, float],
    ) -> dict:
        """
        Select next question using IRT Zone of Proximal Development (ZPD).

        Algorithm:
        1. Calculate average theta for selected concepts
        2. Check if user is in warm-up mode (< 5 responses)
        3. If warm-up: use wide difficulty range
           Otherwise: calculate target ZPD (P_correct 60-75%)
        4. Query questions in beta range, excluding already-asked
        5. Shuffle options and return with new correct_index

        Returns: {id, text, options, correct_index, correct_answer, topic, difficulty}
        """
        normalized_topic = (topic or "mix").strip().lower()

        seen_question_ids = await ClassicService.get_user_seen_question_ids(
            db=db,
            user_id=user_id,
            topic=normalized_topic,
            asked_question_ids=asked_question_ids,
        )

        # Get average theta
        thetas = [theta_snapshot.get(str(cid), 0.0) for cid in concept_ids]
        avg_theta = sum(thetas) / len(thetas) if thetas else 0.0

        # Check if user is in warm-up mode (few responses)
        response_count_stmt = (
            select(func.count())
            .select_from(UserResponse)
            .where(UserResponse.user_id == user_id)
        )
        response_count = int((await db.scalar(response_count_stmt)) or 0)

        if response_count < ClassicService.COLD_START_THRESHOLD:
            # Warm-up mode: wide range
            beta_low, beta_high = -2.0, 2.0
        else:
            # Normal mode: ZPD targeting (P_correct 60-75%)
            beta_low, beta_high = target_beta_range(avg_theta)

        # Query questions
        governance_enabled = False
        try:
            from services.governance_service import GovernanceService

            governance_enabled = GovernanceService.enabled()
        except Exception:
            governance_enabled = False

        candidate_limit = 20 if governance_enabled else 1

        filters = [
            QuestionBank.difficulty_irt >= beta_low,
            QuestionBank.difficulty_irt <= beta_high,
            QuestionBank.source.notin_(ClassicService.NON_CLASSIC_SOURCES),
        ]

        if governance_enabled:
            filters.append(QuestionBank.gov_approved == True)  # noqa: E712
            filters.append(QuestionBank.gov_safe == True)  # noqa: E712

        if seen_question_ids:
            filters.append(QuestionBank.id.notin_(list(seen_question_ids)))

        stmt = select(QuestionBank).where(and_(*filters))

        if normalized_topic != "mix":
            stmt = stmt.where(func.lower(QuestionBank.topic) == normalized_topic)

        # Use concept-targeted selection when concepts exist, otherwise fall back to topic-only.
        if concept_ids:
            stmt = (
                stmt.join(QuestionConcept, QuestionBank.id == QuestionConcept.question_id)
                .where(QuestionConcept.concept_id.in_(concept_ids))
                .order_by(func.random())
                .limit(candidate_limit)
            )
        else:
            stmt = stmt.order_by(func.random()).limit(candidate_limit)

        result = await db.execute(stmt)
        candidates = result.scalars().all()

        question = None
        if candidates:
            for candidate in candidates:
                if governance_enabled:
                    try:
                        decision = await GovernanceService.evaluate_bank_row_for_serving(
                            db,
                            row=candidate,
                            room="classic",
                            topic=topic,
                        )
                        if not decision.approved:
                            continue
                    except Exception:
                        # Governance must not block core gameplay.
                        pass
                question = candidate
                break

        # Fallback: if no question in ZPD, expand search
        if not question:
            stmt = select(QuestionBank)
            stmt = stmt.where(QuestionBank.source.notin_(ClassicService.NON_CLASSIC_SOURCES))
            if governance_enabled:
                stmt = stmt.where(QuestionBank.gov_approved == True)  # noqa: E712
                stmt = stmt.where(QuestionBank.gov_safe == True)  # noqa: E712
            if seen_question_ids:
                stmt = stmt.where(QuestionBank.id.notin_(list(seen_question_ids)))
            if normalized_topic != "mix":
                stmt = stmt.where(func.lower(QuestionBank.topic) == normalized_topic)
            stmt = stmt.order_by(func.random()).limit(candidate_limit)

            result = await db.execute(stmt)
            candidates = result.scalars().all()

            if candidates:
                for candidate in candidates:
                    if governance_enabled:
                        try:
                            decision = await GovernanceService.evaluate_bank_row_for_serving(
                                db,
                                row=candidate,
                                room="classic",
                                topic=topic,
                            )
                            if not decision.approved:
                                continue
                        except Exception:
                            pass
                    question = candidate
                    break

        if not question:
            return None

        # Shuffle options
        try:
            raw_options = json.loads(question.options_json or "[]")
        except (TypeError, json.JSONDecodeError):
            logger.warning(
                "Invalid classic options_json; skipping question_id=%s",
                str(question.id)[:8],
            )
            return None

        options = [str(option) for option in (raw_options or []) if str(option).strip()]
        correct_answer = str(question.correct_answer or "").strip()

        if not options or not correct_answer:
            logger.warning(
                "Classic question missing options or correct_answer; skipping question_id=%s",
                str(question.id)[:8],
            )
            return None
        if correct_answer not in options:
            logger.warning(
                "Classic question correct_answer not found in options; skipping question_id=%s",
                str(question.id)[:8],
            )
            return None

        random.shuffle(options)
        correct_index = options.index(correct_answer)

        # Update times_seen
        await db.execute(
            sqlalchemy_update(QuestionBank)
            .where(QuestionBank.id == question.id)
            .values(
                times_seen=QuestionBank.times_seen + 1,
                last_served_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        await db.commit()

        return {
            "id": str(question.id),
            "text": question.question_text,
            "options": options,
            "correct_index": correct_index,
            "correct_answer": correct_answer,
            "topic": question.topic,
            "difficulty": beta_to_difficulty(question.difficulty_irt),
        }

    @staticmethod
    async def process_answer(
        db: AsyncSession,
        user_id: uuid.UUID,
        session_id: str,
        question_id: str,
        selected_index: int,
        time_taken_seconds: int,
        session_service: SessionService,
        used_hint: bool = False,
    ) -> dict:
        """
        Process answer submission.

        1. Acquire session lock (prevent race conditions)
        2. Verify question is current in session
        3. Get shuffled options from session
        4. Compare selected answer to correct answer
        5. Update concept theta via IRT
        6. Add to repeat queue if applicable (25% wrong, 1% correct)
        7. Select next question (or end session if 10 questions done)

        Returns: {correct, correct_index, explanation, theta_changes, next_question, session_stats}
        """
        async with session_service.session_lock(session_id):
            # Get question
            question = await db.get(QuestionBank, uuid.UUID(question_id))

            if not question:
                raise ValueError("Question not found")

            # Get shuffled options from session
            current_question = await session_service.get_current_question(session_id)
            if not current_question or current_question["id"] != question_id:
                raise ValueError("Question mismatch")

            session_state = await session_service.get_session_state(session_id)
            if not session_state:
                raise ValueError("Session state not found")
            if question_id in session_state.get("questions_asked", []):
                raise ValueError("Question already answered")

            # Check answer
            if selected_index == -1:  # Timeout
                selected_answer = None
                correct = False
            else:
                shuffled_options = list(current_question.get("shuffled_options", []))
                if selected_index < 0 or selected_index >= len(shuffled_options):
                    logger.warning(
                        "Invalid classic selected_index: user=%s session=%s question=%s index=%s options=%s",
                        str(user_id)[:8],
                        str(session_id)[:8],
                        str(question_id)[:8],
                        selected_index,
                        len(shuffled_options),
                    )
                    raise ValueError("Invalid selected index")
                selected_answer = shuffled_options[selected_index]
                correct = selected_answer == current_question["correct_answer"]

            # Get concepts for this question
            concept_stmt = select(QuestionConcept).where(
                QuestionConcept.question_id == uuid.UUID(question_id)
            )
            question_concepts = (await db.execute(concept_stmt)).scalars().all()

            # Update theta for each concept
            theta_changes = []
            for qc in question_concepts:
                old_theta = await ConceptIRT.get_concept_theta(
                    db, user_id, qc.concept_id
                )
                new_theta = await ConceptIRT.update_concept_theta(
                    db, user_id, qc.concept_id, question.difficulty_irt or 0.0, correct
                )
                theta_changes.append(
                    {
                        "concept_id": str(qc.concept_id),
                        "theta_before": old_theta,
                        "theta_after": new_theta,
                    }
                )

            # Record answer in database
            response = UserResponse(
                id=uuid.uuid4(),
                user_id=user_id,
                session_id=uuid.UUID(session_id),
                question_id=uuid.UUID(question_id),
                topic=question.topic,
                difficulty_sent=beta_to_difficulty(question.difficulty_irt),
                answered_correct=correct,
                time_taken=time_taken_seconds,
                used_hint=used_hint,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.add(response)

            points_delta = ClassicService._compute_points_delta(
                correct=bool(correct),
                time_taken_seconds=int(time_taken_seconds or 0),
                used_hint=bool(used_hint),
            )

            user_row = await db.get(User, user_id)
            if user_row is not None:
                new_points = max(0, int(user_row.points or 0) + int(points_delta))
                user_row.points = int(new_points)
                user_row.level = compute_level(int(new_points))

            asked_ids = list(session_state.get("questions_asked", []))
            question_count = len(asked_ids) + 1
            is_finished = question_count >= ClassicService.MAX_QUESTIONS_PER_SESSION

            session_row = await db.get(ClassicSession, uuid.UUID(session_id))
            if session_row is None:
                session_row = ClassicSession(
                    id=uuid.UUID(session_id),
                    user_id=user_id,
                    topic=session_state.get("topic", "mix"),
                    questions_answered=question_count,
                    correct_count=(1 if correct else 0),
                    concepts=session_state.get("concept_ids", []),
                    ended_at=datetime.now(timezone.utc).replace(tzinfo=None) if is_finished else None,
                )
                db.add(session_row)
            else:
                session_row.questions_answered = int(question_count)
                if correct:
                    session_row.correct_count = int(session_row.correct_count or 0) + 1
                if is_finished and session_row.ended_at is None:
                    session_row.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)

            # Add to repeat queue if applicable
            for qc in question_concepts:
                if correct and random.random() < ClassicService.CORRECT_ANSWER_REPEAT_PROBABILITY:
                    # 1% chance to repeat correct answer
                    pass  # Could implement, but uncommon
                elif not correct and random.random() < ClassicService.WRONG_ANSWER_REPEAT_PROBABILITY:
                    # 25% chance to repeat wrong answer
                    repeat_queue_entry = UserConceptRepeatQueue(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        concept_id=qc.concept_id,
                        question_id=uuid.UUID(question_id),
                        repeat_probability=0.5,
                        due_after_session=7,  # Show repeat after 7 more sessions
                        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    )
                    db.add(repeat_queue_entry)

            await db.commit()

            asked_ids.append(question_id)
            session_state["questions_asked"] = asked_ids

            # Increment question count (for repeat queue)
            session_state["is_finished"] = is_finished

            # Persist session state on every answer, including the final one.
            await session_service.store_session_state(session_id, session_state)

            # Select next question or end session
            if is_finished:
                next_question = None
                next_question_public = None
            else:
                next_question = await ClassicService.select_next_question(
                    db,
                    user_id,
                    session_state["topic"],
                    [uuid.UUID(cid) for cid in session_state.get("concept_ids", [])],
                    asked_ids,
                    theta_snapshot=session_state.get("theta_snapshot", {}),
                )

                # Store next question shuffled options
                if next_question:
                    await session_service.set_current_question(
                        session_id,
                        {
                            "id": next_question["id"],
                            "correct_answer": next_question["correct_answer"],
                            "shuffled_options": next_question["options"],
                            "correct_index_shuffled": next_question["correct_index"],
                            "question_sent_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                        },
                    )

                    # Never expose the next question's answer metadata to clients.
                    next_question_public = {
                        "id": next_question["id"],
                        "text": next_question["text"],
                        "options": next_question["options"],
                        "topic": next_question.get("topic"),
                        "difficulty": next_question.get("difficulty"),
                    }
                else:
                    next_question_public = None

            correct_index_shuffled = current_question.get("correct_index_shuffled")
            if correct_index_shuffled is None:
                try:
                    correct_index_shuffled = current_question["shuffled_options"].index(
                        current_question["correct_answer"]
                    )
                except Exception:
                    correct_index_shuffled = -1

            return {
                "correct": correct,
                "correct_index": correct_index_shuffled,
                "explanation": question.explanation,
                "theta_changes": theta_changes,
                "next_question": next_question_public,
                "session_stats": {
                    "questions_answered": question_count,
                    "correct_count": 1 if correct else 0,  # This answer's correctness
                    "is_finished": is_finished,
                },
            }

