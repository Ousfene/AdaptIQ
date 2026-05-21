"""
services/classic_service.py — Classic Room business logic.

Handles:
- Session creation and management
- Concept selection for sessions
- Question selection using IRT
- Answer processing and theta updates
- Repeat queue management
"""
import json
import logging
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, update as sqlalchemy_update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    User, Concept, QuestionBank, QuestionConcept, UserConceptTheta,
    UserConceptRepeatQueue, ClassicSession, UserResponse
)
from database.irt import (
    irt_probability, update_theta, target_beta_range, 
    difficulty_to_beta, beta_to_difficulty, THETA_INIT
)
from database.concept_irt import ConceptIRT, MIN_RESPONSES_FOR_CONFIDENCE
from services.session import SessionService
from services.decay_service import apply_inactivity_decay


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ClassicService:
    """Business logic for Classic Room quizzes."""
    
    # Session settings
    MAX_QUESTIONS_PER_SESSION = 10
    COLD_START_THRESHOLD = 5  # n_responses below this = cold start
    
    # Repeat queue settings
    WRONG_ANSWER_REPEAT_PROBABILITY = 0.25  # 25% chance to queue after wrong
    CORRECT_ANSWER_REPEAT_PROBABILITY = 0.01  # 1% chance to queue after correct
    REPEAT_DUE_SESSIONS = 7  # Show repeat after N more sessions (user vision: 7 quizzes)
    
    @staticmethod
    async def start_session(
        db: AsyncSession,
        user_id: uuid.UUID,
        topic: str,  # "geography", "history", "mix"
        session_service: SessionService,
    ) -> dict:
        """
        Start a new Classic Room session.
        
        Returns dict with session_id, first_question, session_stats.
        """
        # Apply inactivity decay before starting session
        # This ensures users returning after a break aren't thrown into too-hard content
        decayed_count = await apply_inactivity_decay(db, user_id)
        if decayed_count > 0:
            logger.info("session_decay_applied", extra={
                "user_id": str(user_id), "concepts_decayed": decayed_count
            })
        
        # Create session record
        session = ClassicSession(
            id=uuid.uuid4(),
            user_id=user_id,
            topic=topic,
            questions_answered=0,
            correct_count=0,
            created_at=utc_now(),
        )
        db.add(session)
        await db.flush()

        logger.info("classic_session_started", extra={
            "user_id": str(user_id), "session_id": str(session.id), "topic": topic
        })
        
        # Select concepts for this session
        concepts = await ClassicService.select_concepts_for_session(
            db, user_id, topic, n_concepts=5
        )
        concept_ids = [c.id for c in concepts]
        
        # Get user's theta snapshot for these concepts (with confidence tracking)
        theta_snapshot = {}
        confidence_snapshot = {}  # Track which concepts have confident estimates
        for concept in concepts:
            theta_result = await ConceptIRT.get_concept_theta_with_confidence(db, user_id, concept.id)
            theta_snapshot[str(concept.id)] = theta_result.theta
            confidence_snapshot[str(concept.id)] = theta_result.is_confident
        
        # Store session state in Redis
        session_state = {
            "user_id": str(user_id),
            "topic": topic,
            "concept_ids": [str(cid) for cid in concept_ids],
            "theta_snapshot": theta_snapshot,
            "confidence_snapshot": confidence_snapshot,  # Warm-up period tracking
            "questions_asked": [],
            "current_question_id": None,
        }
        await session_service.store_session_state(str(session.id), session_state)
        
        # Select first question (pass confidence_snapshot for warm-up period handling)
        first_question = await ClassicService.select_next_question(
            db, user_id, topic, concept_ids, asked_question_ids=[], 
            theta_snapshot=theta_snapshot, confidence_snapshot=confidence_snapshot
        )

        if first_question:
            # Store current question with shuffled options for answer verification (Fix 1.1)
            # Include question_sent_at for server-side time calculation (TIME-1 fix)
            await session_service.set_current_question(str(session.id), {
                "id": first_question["id"],
                "correct_answer": first_question["correct_answer"],
                "shuffled_options": first_question["options"],
                "correct_index_shuffled": first_question["correct_index"],
                "question_sent_at": utc_now().isoformat(),  # Server-side timestamp
            })

            # Update session state with current question
            session_state["current_question_id"] = str(first_question["id"])
            await session_service.store_session_state(str(session.id), session_state)
        
        return {
            "session_id": str(session.id),
            "first_question": first_question,
            "session_stats": {
                "questions_answered": 0,
                "correct_count": 0,
            }
        }
    
    @staticmethod
    async def select_concepts_for_session(
        db: AsyncSession,
        user_id: uuid.UUID,
        topic: str,
        n_concepts: int = 5,
    ) -> list[Concept]:
        """
        Select concepts for a session using scoring algorithm.
        
        Strategy:
        1. Load all concepts matching topic
        2. For each concept, load user_concept_theta (or default theta=0)
        3. If user has n_responses < 5 for a concept → 'cold start' mode
           Cold start: pick concepts with moderate difficulty_profile
        4. If user has n_responses >= 5:
           score = 0.4 * mastery_gap    # room to grow
                 + 0.3 * recency_bonus  # hasn't practiced recently
                 + 0.2 * repeat_due     # flagged for repetition
                 + 0.1 * zpd_fit        # currently in ZPD range
        5. Pick top n_concepts by score
        """
        # Load concepts matching topic
        if topic == "mix":
            stmt = select(Concept)
        else:
            stmt = select(Concept).where(Concept.topic == topic)
        
        result = await db.execute(stmt)
        all_concepts = list(result.scalars().all())
        
        if not all_concepts:
            logger.warning(f"No concepts found for topic: {topic}")
            return []
        
        if len(all_concepts) <= n_concepts:
            return all_concepts
        
        # Score each concept
        scored_concepts = []
        
        for concept in all_concepts:
            # Get user's theta for this concept
            theta_stmt = select(UserConceptTheta).where(
                (UserConceptTheta.user_id == user_id) &
                (UserConceptTheta.concept_id == concept.id)
            )
            theta_result = await db.execute(theta_stmt)
            theta_record = theta_result.scalar_one_or_none()
            
            if not theta_record or theta_record.response_count < ClassicService.COLD_START_THRESHOLD:
                # Cold start: prioritize concepts with moderate difficulty
                # Random score to ensure variety
                score = 0.5 + random.uniform(-0.2, 0.2)
            else:
                # Calculate scoring components
                theta = theta_record.theta
                
                # Mastery gap: how much room to grow (higher theta = less gap)
                mastery_gap = (3.0 - theta) / 6.0  # Normalize to 0-1
                
                # Recency bonus: hasn't practiced recently
                days_since = 30  # Default if never practiced
                if theta_record.last_updated:
                    days_since = (utc_now() - theta_record.last_updated).days
                recency_bonus = min(days_since / 14.0, 1.0)  # Cap at 14 days
                
                # Repeat due: check if concept is in repeat queue
                repeat_stmt = select(UserConceptRepeatQueue).where(
                    (UserConceptRepeatQueue.user_id == user_id) &
                    (UserConceptRepeatQueue.concept_id == concept.id)
                )
                repeat_result = await db.execute(repeat_stmt)
                # Be tolerant of duplicate queue rows from legacy data.
                repeat_due = 1.0 if repeat_result.scalars().first() else 0.0
                
                # ZPD fit: is current theta near questions available for this concept?
                beta_low, beta_high = target_beta_range(theta)
                # For now, assume ZPD fit is 0.5 (would need question analysis)
                zpd_fit = 0.5
                
                # Calculate weighted score
                score = (
                    0.4 * mastery_gap +
                    0.3 * recency_bonus +
                    0.2 * repeat_due +
                    0.1 * zpd_fit
                )
            
            scored_concepts.append((concept, score))
            
            logger.debug(f"Concept {concept.name}: score={score:.3f}")
        
        # Sort by score descending and take top n
        scored_concepts.sort(key=lambda x: x[1], reverse=True)
        selected = [c for c, _ in scored_concepts[:n_concepts]]
        
        logger.info("concepts_selected", extra={
            "extra": {
                "user_id": str(user_id),
                "topic": topic,
                "concepts": [c.name for c in selected]
            }
        })
        
        return selected
    
    @staticmethod
    async def select_next_question(
        db: AsyncSession,
        user_id: uuid.UUID,
        topic: str,
        concept_ids: list[uuid.UUID],
        asked_question_ids: list[uuid.UUID],
        theta_snapshot: dict[str, float],
        confidence_snapshot: dict[str, bool] = None,
    ) -> Optional[dict]:
        """
        Select next question using IRT ZPD targeting.
        
        If confidence_snapshot provided and most concepts are not confident
        (< MIN_RESPONSES_FOR_CONFIDENCE responses), use wider difficulty range
        to gather more data before trusting theta estimates.
        
        Returns question dict with shuffled options and updated correct_index.
        """
        if not concept_ids:
            return None
        
        # Get user's average theta for these concepts
        thetas = [theta_snapshot.get(str(cid), 0.0) for cid in concept_ids]
        avg_theta = sum(thetas) / len(thetas) if thetas else 0.0
        
        # Check confidence: if most concepts lack sufficient data, widen range
        # This prevents marking user as "easy" after 2 lucky guesses
        use_wide_range = False
        if confidence_snapshot:
            confident_count = sum(1 for cid in concept_ids if confidence_snapshot.get(str(cid), False))
            # If less than half of concepts are confident, use wide range
            use_wide_range = confident_count < len(concept_ids) / 2
        
        if use_wide_range:
            # Warm-up period: use medium difficulty with wide range to gather data
            logger.info(f"Warm-up mode for user {user_id}: using wide difficulty range")
            beta_low, beta_high = -2.0, 2.0  # Covers difficulty 1-5
        else:
            # Normal IRT: target zone of proximal development (60-75% correct probability)
            beta_low, beta_high = target_beta_range(avg_theta)
        
        # Query questions in target range
        filters = [
            QuestionBank.difficulty_irt >= beta_low,
            QuestionBank.difficulty_irt <= beta_high,
        ]

        # Exclude previously answered questions (if any)
        if asked_question_ids:
            filters.append(QuestionBank.id.notin_(asked_question_ids))

        stmt = select(QuestionBank).where(and_(*filters))
        
        # Filter by topic
        if topic != "mix":
            stmt = stmt.where(QuestionBank.topic == topic)
        
        # Filter by concept (at least one concept match)
        if concept_ids:
            # Join with question_concepts to filter by concept
            stmt = stmt.join(QuestionConcept, QuestionBank.id == QuestionConcept.question_id)
            stmt = stmt.where(QuestionConcept.concept_id.in_(concept_ids))
        
        stmt = stmt.order_by(func.random()).limit(1)
        
        result = await db.execute(stmt)
        question = result.scalar_one_or_none()
        
        # If no question in ZPD, expand search
        if not question:
            stmt = select(QuestionBank).where(
                QuestionBank.id.notin_(asked_question_ids) if asked_question_ids else True
            )
            if topic != "mix":
                stmt = stmt.where(QuestionBank.topic == topic)
            stmt = stmt.order_by(func.random()).limit(1)
            
            result = await db.execute(stmt)
            question = result.scalar_one_or_none()
        
        if not question:
            return None

        # Shuffle options and update correct_index
        try:
            options = json.loads(question.options_json)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse options_json for question {question.id}: {e}")
            return None

        correct_answer = question.correct_answer

        # Validate correct_answer exists in options (Fix 1.4)
        if correct_answer not in options:
            logger.error(f"Question {question.id}: correct_answer '{correct_answer}' not in options {options}")
            return None

        # Shuffle
        random.shuffle(options)
        new_correct_index = options.index(correct_answer)
        
        # Update times_seen
        await db.execute(
            sqlalchemy_update(QuestionBank)
            .where(QuestionBank.id == question.id)
            .values(
                times_seen=QuestionBank.times_seen + 1,
                last_served_at=utc_now()
            )
        )

        logger.info("question_selected", extra={
            "user_id": str(user_id),
            "question_id": str(question.id),
            "beta": question.difficulty_irt,
            "theta_avg": avg_theta,
            "in_zpd": beta_low <= question.difficulty_irt <= beta_high
        })
        
        return {
            "id": str(question.id),
            "text": question.question_text,
            "options": options,
            "correct_index": new_correct_index,
            "correct_answer": correct_answer,  # NEW: Include for session storage
            "topic": question.topic,
            "difficulty": beta_to_difficulty(question.difficulty_irt),
        }
    
    @staticmethod
    async def process_answer(
        db: AsyncSession,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        question_id: uuid.UUID,
        selected_index: int,
        time_taken_seconds: int,
        session_service: SessionService,
        used_hint: bool = False,
    ) -> dict:
        """
        Process an answer submission using shuffled options stored in session.
        Protected by session lock to prevent race conditions (Fix 1.2).

        Returns dict with correct, correct_index, explanation, theta_change,
        next_question, session_stats.
        """
        # ═══════ FIX 1.2: Acquire session lock to prevent race conditions ═══════
        async with session_service.session_lock(str(session_id)):
            # All operations within this block are atomic w.r.t. this session
            # ═════════════════════════════════════════════════════════════════

            # Get session from DB
            session_stmt = select(ClassicSession).where(ClassicSession.id == session_id)
            session_result = await db.execute(session_stmt)
            session = session_result.scalar_one_or_none()

            if not session or session.user_id != user_id:
                raise ValueError("Session not found or doesn't belong to user")

            # Get question from DB (for explanation and theta calculation)
            question_stmt = select(QuestionBank).where(QuestionBank.id == question_id)
            question_result = await db.execute(question_stmt)
            question = question_result.scalar_one_or_none()

            if not question:
                raise ValueError("Question not found")

            # Get session state from Redis
            session_state = await session_service.get_session_state(str(session_id))
            if not session_state:
                raise ValueError("Session state not found")

            # ═══════ FIX 1.1: Use shuffled options from session ═══════
            # Get current question with shuffled options from session
            current_question = await session_service.get_current_question(str(session_id))
            if not current_question or current_question["id"] != str(question_id):
                raise ValueError("Current question mismatch or not stored in session")

            # ═══════ TIME-2 FIX: Calculate server-side time ═══════
            # Use server-side timestamp to calculate actual time taken
            # This prevents client manipulation of time for bonus points
            question_sent_at_str = current_question.get("question_sent_at")
            if question_sent_at_str:
                try:
                    from datetime import datetime
                    question_sent_at = datetime.fromisoformat(question_sent_at_str)
                    server_time_taken = int((utc_now() - question_sent_at).total_seconds())
                    # Clamp to valid range (0 to quiz time limit)
                    from config import QUIZ_TIME_LIMIT_SECONDS
                    server_time_taken = max(0, min(server_time_taken, QUIZ_TIME_LIMIT_SECONDS + 5))
                    # Use server time, not client time (ignore client-provided value)
                    time_taken_seconds = server_time_taken
                except (ValueError, TypeError):
                    # Fallback to client time if timestamp parsing fails
                    logger.warning("failed_to_parse_question_sent_at", extra={
                        "session_id": str(session_id),
                        "question_sent_at": question_sent_at_str,
                    })
            # ═════════════════════════════════════════════════════════

            # selected_index == -1 is treated as timeout (valid, always incorrect).
            if selected_index == -1:
                selected_answer = None
                correct = False
            else:
                if not (0 <= selected_index < len(current_question["shuffled_options"])):
                    raise ValueError(f"Invalid option index: {selected_index}")
                selected_answer = current_question["shuffled_options"][selected_index]
                correct = selected_answer == current_question["correct_answer"]
            correct_index = current_question["correct_index_shuffled"]
            # ═════════════════════════════════════════════════════════
            
            logger.info("answer_submitted", extra={
                "user_id": str(user_id),
                "session_id": str(session_id),
                "question_id": str(question_id),
                "correct": correct,
                "time_taken_seconds": time_taken_seconds,
                "selected_index": selected_index,
            })

            # Get question's concepts
            concept_stmt = select(QuestionConcept).where(QuestionConcept.question_id == question_id)
            concept_result = await db.execute(concept_stmt)
            question_concepts = concept_result.scalars().all()

            # Calculate theta changes for each concept
            theta_changes = []
            for qc in question_concepts:
                old_theta = await ConceptIRT.get_concept_theta(db, user_id, qc.concept_id)
                new_theta = await ConceptIRT.update_concept_theta(
                    db, user_id, qc.concept_id, question.difficulty_irt, correct
                )
                theta_changes.append({
                    "concept_id": str(qc.concept_id),
                    "theta_before": old_theta,
                    "theta_after": new_theta,
                })

                logger.info("theta_updated", extra={
                    "user_id": str(user_id),
                    "concept_id": str(qc.concept_id),
                    "theta_before": old_theta,
                    "theta_after": new_theta,
                    "correct": correct
                })

            # Maybe add to repeat queue
            if not correct and random.random() < ClassicService.WRONG_ANSWER_REPEAT_PROBABILITY:
                await ClassicService._add_to_repeat_queue(
                    db, user_id, question_concepts[0].concept_id if question_concepts else None,
                    question_id, session.questions_answered
                )
            elif correct and random.random() < ClassicService.CORRECT_ANSWER_REPEAT_PROBABILITY:
                await ClassicService._add_to_repeat_queue(
                    db, user_id, question_concepts[0].concept_id if question_concepts else None,
                    question_id, session.questions_answered
                )

            # Record response
            response = UserResponse(
                id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
                question_id=question_id,
                topic=question.topic,
                difficulty_sent=beta_to_difficulty(question.difficulty_irt),
                answered_correct=correct,
                time_taken=time_taken_seconds,
                used_hint=used_hint,
                created_at=utc_now(),
            )
            db.add(response)

            # Update session stats
            session.questions_answered += 1
            session.correct_count += 1 if correct else 0

            # Update theta snapshot in session state
            # Also update confidence: after each response, concept gets more confident
            for tc in theta_changes:
                session_state["theta_snapshot"][tc["concept_id"]] = tc["theta_after"]
                # Fetch updated response count to check confidence
                concept_uuid = uuid.UUID(tc["concept_id"])
                theta_result = await ConceptIRT.get_concept_theta_with_confidence(db, user_id, concept_uuid)
                if "confidence_snapshot" not in session_state:
                    session_state["confidence_snapshot"] = {}
                session_state["confidence_snapshot"][tc["concept_id"]] = theta_result.is_confident

            # Track asked questions
            asked_ids = session_state.get("questions_asked", [])
            asked_ids.append(str(question_id))
            session_state["questions_asked"] = asked_ids

            # Check if session should end
            session_ended = session.questions_answered >= ClassicService.MAX_QUESTIONS_PER_SESSION
            next_question = None

            if not session_ended:
                # Select next question
                concept_ids = [uuid.UUID(cid) for cid in session_state.get("concept_ids", [])]
                asked_question_ids = [uuid.UUID(qid) for qid in asked_ids]
                confidence_snapshot = session_state.get("confidence_snapshot", {})

                next_question = await ClassicService.select_next_question(
                    db, user_id, session.topic, concept_ids,
                    asked_question_ids, session_state["theta_snapshot"],
                    confidence_snapshot=confidence_snapshot
                )

                if next_question:
                    # Store next question with shuffled options in session
                    # Include question_sent_at for server-side time calculation (TIME-1 fix)
                    await session_service.set_current_question(str(session_id), {
                        "id": next_question["id"],
                        "correct_answer": next_question.get("correct_answer"),
                        "shuffled_options": next_question["options"],
                        "correct_index_shuffled": next_question["correct_index"],
                        "question_sent_at": utc_now().isoformat(),  # Server-side timestamp
                    })
                    session_state["current_question_id"] = next_question["id"]
            else:
                session.ended_at = utc_now()
                # Only clear the stored question when session ends
                await session_service.clear_current_question(str(session_id))

            await session_service.store_session_state(str(session_id), session_state)
            await db.flush()  # Ensure all DB operations complete before releasing lock

            return {
                "correct": correct,
                "correct_index": correct_index,
                "explanation": question.explanation,
                "theta_change": theta_changes[0]["theta_after"] - theta_changes[0]["theta_before"] if theta_changes else 0.0,
                "next_question": next_question,
                "session_stats": {
                    "questions_answered": session.questions_answered,
                    "correct_count": session.correct_count,
                },
                "session_ended": session_ended,
            }
    
    @staticmethod
    async def _add_to_repeat_queue(
        db: AsyncSession,
        user_id: uuid.UUID,
        concept_id: Optional[uuid.UUID],
        question_id: uuid.UUID,
        current_session_count: int,
    ) -> None:
        """Add a concept/question to the repeat queue."""
        if not concept_id:
            return
        
        repeat = UserConceptRepeatQueue(
            id=uuid.uuid4(),
            user_id=user_id,
            concept_id=concept_id,
            question_id=question_id,
            repeat_probability=0.5,
            due_after_session=current_session_count + ClassicService.REPEAT_DUE_SESSIONS,
            created_at=utc_now(),
        )
        db.add(repeat)

        logger.info("repeat_queued", extra={
            "user_id": str(user_id),
            "concept_id": str(concept_id),
            "question_id": str(question_id),
        })
    
    @staticmethod
    async def get_hint(
        db: AsyncSession,
        question_id: uuid.UUID,
        llm_client=None,
    ) -> str:
        """
        Get hint for a question.
        
        Returns stored hint if available, otherwise generates one.
        """
        question_stmt = select(QuestionBank).where(QuestionBank.id == question_id)
        result = await db.execute(question_stmt)
        question = result.scalar_one_or_none()
        
        if not question:
            raise ValueError("Question not found")
        
        # Return cached hint if available
        if question.hint:
            return question.hint
        
        # Generate hint via LLM
        if llm_client:
            hint = await llm_client.generate_hint(
                question_text=question.question_text,
                correct_answer=question.correct_answer,
            )
            
            if not hint:
                return "Think about the key concepts tested in this question."
            
            # Validate hint doesn't reveal answer
            hint_lower = hint.lower()
            if question.correct_answer.lower() in hint_lower:
                hint = "Think carefully about the question and eliminate unlikely options."

            # Also check options don't appear in hint
            try:
                options = json.loads(question.options_json)
                for opt in options:
                    if opt.lower() in hint_lower:
                        hint = "Think carefully about the question and eliminate unlikely options."
                        break
            except (json.JSONDecodeError, ValueError):
                pass  # Skip option check if can't parse
            
            # Cache the hint
            await db.execute(
                sqlalchemy_update(QuestionBank)
                .where(QuestionBank.id == question_id)
                .values(hint=hint)
            )
            
            return hint
        
        return "Consider all options carefully before choosing."
    
    @staticmethod
    async def get_session_metrics(
        db: AsyncSession,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> dict:
        """
        Get metrics for a completed session.
        
        Returns accuracy, theta_progress, adaptivity_score.
        """
        # Get session
        session_stmt = select(ClassicSession).where(
            (ClassicSession.id == session_id) &
            (ClassicSession.user_id == user_id)
        )
        session_result = await db.execute(session_stmt)
        session = session_result.scalar_one_or_none()
        
        if not session:
            raise ValueError("Session not found")
        
        # Calculate accuracy
        accuracy = session.correct_count / session.questions_answered if session.questions_answered > 0 else 0.0
        
        # Get all responses for this session
        resp_stmt = select(UserResponse).where(UserResponse.session_id == session_id)
        resp_result = await db.execute(resp_stmt)
        responses = resp_result.scalars().all()
        
        # Calculate theta progress per concept
        # (Would need to track start/end thetas in session state for accurate progress)
        theta_progress = []
        
        # Calculate adaptivity score (% of questions in ZPD)
        # ZPD = 60-75% probability, which means difficulty_sent should match user theta
        in_zpd_count = 0
        for resp in responses:
            # Rough approximation: difficulty 3 is "medium", close to user's level
            if 2 <= resp.difficulty_sent <= 4:
                in_zpd_count += 1
        
        adaptivity_score = in_zpd_count / len(responses) if responses else 0.0
        
        return {
            "accuracy": accuracy,
            "theta_progress": theta_progress,
            "adaptivity_score": adaptivity_score,
            "total_questions": session.questions_answered,
            "correct_count": session.correct_count,
            "topic": session.topic,
        }
