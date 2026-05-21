"""
services/pvp_service.py â€” Business logic for PvP matchmaking and match management.

Features:
  - Elo-based matchmaking with concept affinity scoring
  - Shared quiz generation (both players get identical questions)
  - Per-player answer tracking and score aggregation
  - Elo rating updates after match completion (K=32 for <30 games, K=16 after)

Matchmaking algorithm:
  1. Find players in queue with same topic
  2. Score each pair by Elo proximity (|elo1 - elo2| < 300)
  3. Prefer pairs with shared concept knowledge
  4. Create match with 5 shared questions
"""

from __future__ import annotations

import json
import uuid
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from math import log10 as math_log10, pow as math_pow

from sqlalchemy import select, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from database.pvp_models import (
    PvPMatchmakingQueue,
    PvPMatch,
    PvPMatchAnswer,
    PvPRating,
)
from database.models import User, QuestionBank
from database.concept_models import UserConceptTheta

logger = logging.getLogger(__name__)

# â”€â”€ Elo Constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
ELO_K_NEW     = 32   # K-factor for players with < 30 games
ELO_K_REGULAR = 16   # K-factor for experienced players
ELO_DEFAULT   = 1000.0
ELO_MAX_DIFF  = 300  # Maximum Elo difference for matchmaking


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# MATCHMAKING
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


# Load rating row for a user, creating defaults when missing.
async def get_or_create_rating(db: AsyncSession, user_id: uuid.UUID) -> PvPRating:
    """Get or create a PvP rating record for a user.

    Args:
        db: AsyncSession
        user_id: User UUID

    Returns:
        PvPRating row (created with defaults if not found)
    """
    result = await db.execute(
        select(PvPRating).where(PvPRating.user_id == user_id)
    )
    rating = result.scalar_one_or_none()
    if rating is None:
        rating = PvPRating(user_id=user_id, elo_rating=ELO_DEFAULT)
        db.add(rating)
        await db.flush()
        logger.info("Created PvP rating for user=%s", str(user_id)[:8])
    return rating


# Add user to matchmaking queue and trigger immediate pairing attempt.
async def join_queue(
    db: AsyncSession,
    user_id: uuid.UUID,
    topic: str,
) -> PvPMatchmakingQueue:
    """Add a player to the matchmaking queue.

    Removes any existing stale queue entries for this user first.

    Args:
        db: AsyncSession
        user_id: User UUID
        topic: Quiz topic ("History", "Geography", "Mixed")

    Returns:
        PvPMatchmakingQueue row with status="waiting"
    """
    # Remove stale entries for this user
    await db.execute(
        delete(PvPMatchmakingQueue).where(PvPMatchmakingQueue.user_id == user_id)
    )

    rating = await get_or_create_rating(db, user_id)

    # Get user's concept IDs for matching
    concept_rows = await db.execute(
        select(UserConceptTheta.concept_id)
        .where(UserConceptTheta.user_id == user_id)
        .order_by(UserConceptTheta.response_count.desc())
        .limit(10)
    )
    concept_ids = [str(row[0]) for row in concept_rows.fetchall()]

    entry = PvPMatchmakingQueue(
        user_id=user_id,
        topic=topic,
        elo_rating=rating.elo_rating,
        concepts_json=json.dumps(concept_ids),
        status="waiting",
    )
    db.add(entry)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("Already in matchmaking queue")
    await db.refresh(entry)

    logger.info("User %s joined PvP queue (topic=%s, elo=%.0f)", str(user_id)[:8], topic, rating.elo_rating)

    # Try to find a match immediately
    match = await _try_matchmaking(db, entry)
    if match:
        logger.info("Immediate match found: %s vs %s", str(match.user1_id)[:8], str(match.user2_id)[:8])

    return entry


# Remove waiting queue entry for a user.
async def leave_queue(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Remove a player from the matchmaking queue.

    Args:
        db: AsyncSession
        user_id: User UUID

    Returns:
        True if an entry was removed, False if player wasn't in queue
    """
    result = await db.execute(
        delete(PvPMatchmakingQueue).where(
            PvPMatchmakingQueue.user_id == user_id,
            PvPMatchmakingQueue.status == "waiting",
        )
    )
    await db.commit()
    removed = result.rowcount > 0
    if removed:
        logger.info("User %s left PvP queue", str(user_id)[:8])
    return removed


# Return current queue/match status for a user.
async def get_queue_status(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Check if a player has been matched or is still waiting.

    Args:
        db: AsyncSession
        user_id: User UUID

    Returns:
        dict with status, match_id, opponent_username
    """
    # Prefer active matches first and tolerate duplicate active rows safely.
    active_matches_result = await db.execute(
        select(PvPMatch)
        .where(
            and_(
                PvPMatch.status == "active",
                (PvPMatch.user1_id == user_id) | (PvPMatch.user2_id == user_id),
            )
        )
        .order_by(PvPMatch.created_at.desc(), PvPMatch.started_at.desc())
        .limit(2)
    )
    active_matches = active_matches_result.scalars().all()

    if active_matches:
        match_row = active_matches[0]
        if len(active_matches) > 1:
            logger.warning(
                "Multiple active PvP matches found for user=%s; using latest match=%s",
                str(user_id)[:8],
                str(match_row.id)[:8],
            )

        opponent_id = match_row.user2_id if match_row.user1_id == user_id else match_row.user1_id
        opponent = await db.get(User, opponent_id)
        return {
            "status": "matched",
            "match_id": str(match_row.id),
            "opponent_username": opponent.username if opponent else "Unknown",
            "topic": match_row.topic,
            "message": f"Match found! Playing against {opponent.username if opponent else 'Unknown'}",
        }

    # Check if user is in queue
    result = await db.execute(
        select(PvPMatchmakingQueue)
        .where(PvPMatchmakingQueue.user_id == user_id)
        .order_by(PvPMatchmakingQueue.joined_at.desc())
        .limit(1)
    )
    entry = result.scalars().first()

    if entry and entry.status == "waiting":
        # Try matchmaking again
        match = await _try_matchmaking(db, entry)
        if match:
            opponent_id = match.user2_id if match.user1_id == user_id else match.user1_id
            opponent = await db.get(User, opponent_id)
            return {
                "status": "matched",
                "match_id": str(match.id),
                "opponent_username": opponent.username if opponent else "Unknown",
                "topic": match.topic,
                "message": f"Match found! Playing against {opponent.username if opponent else 'Unknown'}",
            }
        return {
            "status": "waiting",
            "match_id": None,
            "opponent_username": None,
            "topic": entry.topic,
            "message": "Still searching for an opponent...",
        }

    if entry and entry.status == "matched":
        # Transitional state: queue row says matched but no active match is visible yet.
        return {
            "status": "waiting",
            "match_id": None,
            "opponent_username": None,
            "topic": entry.topic,
            "message": "Match is being prepared. Please refresh shortly.",
        }

    return {"status": "not_in_queue", "match_id": None, "message": "Not in queue"}


# Attempt to pair one queue entry with the best available opponent.
async def _try_matchmaking(
    db: AsyncSession,
    entry: PvPMatchmakingQueue,
) -> Optional[PvPMatch]:
    """Try to find an opponent for the given queue entry.

    Matching criteria:
      1. Same topic (or at least one is "Mixed")
      2. Elo difference â‰¤ ELO_MAX_DIFF
      3. Not the same user

    Args:
        db: AsyncSession
        entry: The player's queue entry

    Returns:
        PvPMatch if matched, None if no opponent found
    """
    # Clean stale queue entries (older than 10 minutes)
    stale_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
    await db.execute(
        delete(PvPMatchmakingQueue).where(
            PvPMatchmakingQueue.status == "waiting",
            PvPMatchmakingQueue.joined_at < stale_cutoff,
        )
    )

    # Find potential opponents
    query = (
        select(PvPMatchmakingQueue)
        .where(
            PvPMatchmakingQueue.user_id != entry.user_id,
            PvPMatchmakingQueue.status == "waiting",
            PvPMatchmakingQueue.elo_rating >= entry.elo_rating - ELO_MAX_DIFF,
            PvPMatchmakingQueue.elo_rating <= entry.elo_rating + ELO_MAX_DIFF,
        )
        .order_by(func.random())
        .limit(5)
    )

    # Filter by topic compatibility
    if entry.topic != "Mixed":
        query = query.where(
            (PvPMatchmakingQueue.topic == entry.topic)
            | (PvPMatchmakingQueue.topic == "Mixed")
        )

    result = await db.execute(query)
    candidates = result.scalars().all()

    if not candidates:
        return None

    # ── Rematch cooldown: skip opponents matched in the last 5 minutes ──
    cooldown_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    recent_opponents_result = await db.execute(
        select(PvPMatch.user1_id, PvPMatch.user2_id).where(
            PvPMatch.status == "completed",
            PvPMatch.ended_at >= cooldown_cutoff,
            (PvPMatch.user1_id == entry.user_id) | (PvPMatch.user2_id == entry.user_id),
        )
    )
    recent_opponent_ids: set[uuid.UUID] = set()
    for row in recent_opponents_result.fetchall():
        u1, u2 = row
        recent_opponent_ids.add(u2 if u1 == entry.user_id else u1)

    # Pick best candidate (highest concept overlap + Elo closeness)
    best = None
    best_score = -1.0
    my_concepts = set(json.loads(entry.concepts_json or "[]"))

    for candidate in candidates:
        # Skip recent opponents (rematch cooldown)
        if candidate.user_id in recent_opponent_ids:
            logger.debug("Skipping rematch with %s (cooldown)", str(candidate.user_id)[:8])
            continue
        their_concepts = set(json.loads(candidate.concepts_json or "[]"))
        overlap = len(my_concepts & their_concepts)
        elo_closeness = 1.0 - abs(entry.elo_rating - candidate.elo_rating) / ELO_MAX_DIFF
        score = overlap * 2 + elo_closeness
        if score > best_score:
            best = candidate
            best_score = score

    if best is None:
        return None

    # Create the match
    topic = entry.topic if entry.topic != "Mixed" else best.topic
    match = await _create_match(db, entry.user_id, best.user_id, topic)

    # Mark both as matched
    entry.status = "matched"
    best.status = "matched"
    await db.commit()

    return match


# Create an active PvP match and attach shared question payload.
async def _create_match(
    db: AsyncSession,
    user1_id: uuid.UUID,
    user2_id: uuid.UUID,
    topic: str,
) -> PvPMatch:
    """Create a PvP match with shared questions.

    Selects 5 random questions from the question bank for the given topic.
    Both players will answer the same questions.

    Args:
        db: AsyncSession
        user1_id: First player UUID
        user2_id: Second player UUID
        topic: Quiz topic

    Returns:
        PvPMatch row with questions_json populated
    """
    governance_enabled = False
    try:
        from services.governance_service import GovernanceService

        governance_enabled = GovernanceService.enabled()
    except Exception:
        governance_enabled = False

    # Fetch 5 random questions for the topic
    topic_filter = topic.lower()
    # Exclude questions either player has already seen in any session
    union_seen_ids: set[uuid.UUID] = set()
    try:
        from services.classic_service import ClassicService

        # Request global seen question ids across all topics to avoid repeats
        seen1 = await ClassicService.get_user_seen_question_ids(db, user1_id, "mix")
        seen2 = await ClassicService.get_user_seen_question_ids(db, user2_id, "mix")
        union_seen_ids = set(seen1) | set(seen2)
        logger.debug("PvP global seen ids count: %d (user1=%d user2=%d)", len(union_seen_ids), len(seen1), len(seen2))
    except Exception:
        union_seen_ids = set()

    stmt = select(QuestionBank).where(QuestionBank.topic.ilike(f"%{topic_filter}%"))
    if union_seen_ids:
        stmt = stmt.where(QuestionBank.id.notin_(list(union_seen_ids)))
    stmt = stmt.order_by(func.random()).limit(50 if governance_enabled else 5)

    if governance_enabled:
        stmt = stmt.where(QuestionBank.gov_approved == True)  # noqa: E712
        stmt = stmt.where(QuestionBank.gov_safe == True)  # noqa: E712

    result = await db.execute(stmt)
    candidates = result.scalars().all()

    questions: list[QuestionBank] = []
    if governance_enabled:
        for candidate in candidates:
            try:
                decision = await GovernanceService.evaluate_bank_row_for_serving(
                    db,
                    row=candidate,
                    room="pvp",
                    topic=topic,
                )
                if not decision.approved:
                    continue
            except Exception:
                pass
            questions.append(candidate)
            if len(questions) >= 5:
                break
    else:
        questions = candidates[:5]

    # Fallback: if not enough topic-specific questions, add random ones
    if len(questions) < 5:
        extra_stmt = (
            select(QuestionBank)
            .where(QuestionBank.id.notin_([q.id for q in questions]))
            .order_by(func.random())
            .limit(100 if governance_enabled else (5 - len(questions)))
        )

        if union_seen_ids:
            extra_stmt = extra_stmt.where(QuestionBank.id.notin_(list(union_seen_ids)))

        if governance_enabled:
            extra_stmt = extra_stmt.where(QuestionBank.gov_approved == True)  # noqa: E712
            extra_stmt = extra_stmt.where(QuestionBank.gov_safe == True)  # noqa: E712

        extra_result = await db.execute(extra_stmt)
        extras = extra_result.scalars().all()
        if governance_enabled:
            for candidate in extras:
                if len(questions) >= 5:
                    break
                try:
                    decision = await GovernanceService.evaluate_bank_row_for_serving(
                        db,
                        row=candidate,
                        room="pvp",
                        topic=topic,
                    )
                    if not decision.approved:
                        continue
                except Exception:
                    pass
                questions.append(candidate)
        else:
            questions.extend(extras)

    # Build questions JSON
    questions_data = []
    for i, q in enumerate(questions):
        options = json.loads(q.options_json)
        random.shuffle(options)
        questions_data.append({
            "id": str(q.id),
            "text": q.question_text,
            "options": options,
            "correctAnswer": q.correct_answer,
            "explanation": q.explanation or "",
            "index": i,
        })

    match = PvPMatch(
        user1_id=user1_id,
        user2_id=user2_id,
        topic=topic,
        status="active",
        total_questions=len(questions_data),
        questions_json=json.dumps(questions_data),
    )
    db.add(match)
    await db.commit()
    await db.refresh(match)

    logger.info("PvP match created: %s (%s vs %s, %d questions)",
                str(match.id)[:8], str(user1_id)[:8], str(user2_id)[:8], len(questions_data))
    return match


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# MATCH GAMEPLAY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


# Fetch one PvP match by id.
async def get_match(db: AsyncSession, match_id: uuid.UUID) -> Optional[PvPMatch]:
    """Get a PvP match by ID.

    Args:
        db: AsyncSession
        match_id: Match UUID

    Returns:
        PvPMatch or None
    """
    return await db.get(PvPMatch, match_id)


# Count how many questions a player has already answered in a match.
async def _count_player_answers(
    db: AsyncSession,
    match_id: uuid.UUID,
    user_id: uuid.UUID,
) -> int:
    result = await db.execute(
        select(func.count()).select_from(PvPMatchAnswer).where(
            PvPMatchAnswer.match_id == match_id,
            PvPMatchAnswer.user_id == user_id,
        )
    )

    if hasattr(result, "scalar_one"):
        value = result.scalar_one()
    else:
        value = result.scalar_one_or_none()

    return int(value or 0)


# Validate and persist one answer submission for a PvP match.
async def submit_answer(
    db: AsyncSession,
    match_id: uuid.UUID,
    user_id: uuid.UUID,
    question_id: str,
    question_index: int,
    answer: str,
    time_taken: Optional[float],
) -> dict:
    """Record a player's answer and update match scores.

    Args:
        db: AsyncSession
        match_id: Match UUID
        user_id: Player UUID
        question_id: Question UUID string
        question_index: 0-based question position
        answer: Player's chosen answer text
        time_taken: Seconds taken to answer

    Returns:
        dict with is_correct, your_score, opponent_score, match_finished
    """
    match = await get_match(db, match_id)
    if not match:
        raise ValueError("Match not found")
    if match.status != "active":
        raise ValueError("Match is not active")

    # Verify user is in this match (compare as strings for UUID consistency)
    if str(user_id) not in (str(match.user1_id), str(match.user2_id)):
        logger.error(
            "PvP user mismatch: user_id=%s user1=%s user2=%s",
            str(user_id), str(match.user1_id), str(match.user2_id)
        )
        raise ValueError("User is not in this match")

    # Resolve question list early and use it as a safe fallback for total count.
    questions = json.loads(match.questions_json or "[]")
    total_questions = int(getattr(match, "total_questions", 0) or len(questions))
    if total_questions <= 0:
        raise ValueError("Match has no questions")

    answered_before = await _count_player_answers(db, match_id, user_id)
    if answered_before >= total_questions:
        raise ValueError("All questions in this match are already answered")
    if question_index != answered_before:
        raise ValueError(f"Question must be answered in order. Expected question index {answered_before}")

    # Check if already answered this question
    existing = await db.execute(
        select(PvPMatchAnswer).where(
            PvPMatchAnswer.match_id == match_id,
            PvPMatchAnswer.user_id == user_id,
            PvPMatchAnswer.question_index == question_index,
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("Already answered this question")

    # Find correct answer from questions JSON
    if question_index < 0 or question_index >= len(questions):
        raise ValueError("Invalid question index")

    q_data = questions[question_index]
    expected_question_id = str(q_data.get("id", "")).strip()
    try:
        normalized_question_id = str(uuid.UUID(question_id))
    except ValueError:
        raise ValueError("Invalid question ID")

    try:
        normalized_expected_id = str(uuid.UUID(expected_question_id))
    except ValueError:
        logger.error(
            "Invalid server question payload in match: match=%s index=%s expected_id=%s",
            str(match_id)[:8],
            question_index,
            expected_question_id,
        )
        raise ValueError("Invalid match question payload")

    if normalized_question_id != normalized_expected_id:
        logger.warning(
            "Rejected PvP answer with mismatched question payload: match=%s user=%s index=%s sent=%s expected=%s",
            str(match_id)[:8],
            str(user_id)[:8],
            question_index,
            normalized_question_id[:8],
            normalized_expected_id[:8],
        )
        raise ValueError("Question payload mismatch")

    correct_answer = q_data["correctAnswer"]
    submitted_answer = (answer or "").strip()
    if not submitted_answer:
        # Represent timeout/missed-answer submissions explicitly in storage.
        submitted_answer = "__timeout__"
    is_correct = submitted_answer.lower() == correct_answer.strip().lower()

    # Record answer
    db.add(PvPMatchAnswer(
        match_id=match_id,
        user_id=user_id,
        question_id=uuid.UUID(normalized_question_id),
        question_index=question_index,
        chosen_answer=submitted_answer,
        is_correct=is_correct,
        time_taken=time_taken,
    ))

    # Flush early so duplicate-answer races are mapped to a user-safe error
    # before any later query triggers an implicit autoflush.
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("Already answered this question")

    # Update score
    if str(user_id) == str(match.user1_id):
        if is_correct:
            match.user1_score += 1
    else:
        if is_correct:
            match.user2_score += 1

    # Check if player finished all questions
    answers_count = await _count_player_answers(db, match_id, user_id)

    if answers_count >= total_questions:
        if str(user_id) == str(match.user1_id):
            match.user1_finished = True
        else:
            match.user2_finished = True

    match_finished = match.user1_finished and match.user2_finished
    if match_finished:
        match.status = "completed"
        match.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # Determine winner
        if match.user1_score > match.user2_score:
            match.winner_id = match.user1_id
        elif match.user2_score > match.user1_score:
            match.winner_id = match.user2_id
        # else: draw, winner_id stays None

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("Already answered this question")

    # Prepare response
    your_score = match.user1_score if str(user_id) == str(match.user1_id) else match.user2_score
    opponent_score = match.user2_score if str(user_id) == str(match.user1_id) else match.user1_score

    next_question = None
    if answers_count < len(questions):
        next_q = questions[answers_count]
        next_options = next_q.get("options") if isinstance(next_q.get("options"), list) else []
        next_question = {
            "id": str(next_q.get("id", "")),
            "text": str(next_q.get("text", "")),
            "options": [str(opt) for opt in next_options],
            "index": int(next_q.get("index", answers_count)),
        }

    return {
        "is_correct": is_correct,
        "correct_answer": correct_answer,
        "explanation": q_data.get("explanation", ""),
        "your_score": your_score,
        "opponent_score": opponent_score,
        "questions_answered": answers_count,
        "match_finished": match_finished,
        "next_question": next_question,
    }


# Complete a match, apply Elo updates, and return final outcome data.
async def end_match(
    db: AsyncSession,
    match_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """Finalize match and compute Elo changes.

    Called when both players finish or when a player requests to end early.

    Args:
        db: AsyncSession
        match_id: Match UUID
        user_id: Requesting user UUID

    Returns:
        dict with winner, scores, elo_change, new_elo
    """
    match = await get_match(db, match_id)
    if not match:
        raise ValueError("Match not found")

    if user_id not in (match.user1_id, match.user2_id):
        logger.warning(
            "Blocked unauthorized end_match attempt: match=%s requester=%s user1=%s user2=%s",
            str(match_id)[:8], str(user_id)[:8], str(match.user1_id)[:8], str(match.user2_id)[:8]
        )
        raise ValueError("You are not in this match")

    is_user1 = (user_id == match.user1_id)
    your_score = match.user1_score if is_user1 else match.user2_score
    opponent_score = match.user2_score if is_user1 else match.user1_score
    opponent_id = match.user2_id if is_user1 else match.user1_id
    opponent = await db.get(User, opponent_id)

    # Idempotency: if already completed, return persisted result without
    # re-applying Elo updates.
    if match.status != "active":
        rating_user1 = (
            await db.execute(select(PvPRating).where(PvPRating.user_id == match.user1_id))
        ).scalar_one_or_none()
        rating_user2 = (
            await db.execute(select(PvPRating).where(PvPRating.user_id == match.user2_id))
        ).scalar_one_or_none()

        rating_row = rating_user1 if is_user1 else rating_user2
        opponent_rating_row = rating_user2 if is_user1 else rating_user1

        user1_delta = _normalize_user1_delta_from_match(match, rating_user1, rating_user2)
        user2_delta = _infer_user2_delta_from_post_state(match, rating_user1, rating_user2, user1_delta)

        if match.winner_id == user_id:
            result = "win"
        elif match.winner_id is None:
            result = "draw"
        else:
            result = "loss"

        signed_delta = user1_delta if is_user1 else user2_delta

        logger.info(
            "Idempotent end_match return: match=%s requester=%s status=%s winner=%s",
            str(match.id)[:8], str(user_id)[:8], match.status, str(match.winner_id)[:8] if match.winner_id else "draw"
        )

        return {
            "match_id": str(match.id),
            "winner_id": str(match.winner_id) if match.winner_id else None,
            "result": result,
            "your_score": your_score,
            "opponent_score": opponent_score,
            "elo_change": signed_delta,
            "new_elo": rating_row.elo_rating if rating_row else ELO_DEFAULT,
            "opponent_username": opponent.username if opponent else "Unknown",
        }

    # Force-complete if not already
    match.status = "completed"
    match.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if match.user1_score > match.user2_score:
        match.winner_id = match.user1_id
    elif match.user2_score > match.user1_score:
        match.winner_id = match.user2_id

    # Compute Elo changes
    rating1 = await get_or_create_rating(db, match.user1_id)
    rating2 = await get_or_create_rating(db, match.user2_id)

    elo_change_user1 = _compute_elo_change(
        rating1.elo_rating, rating2.elo_rating,
        match.winner_id, match.user1_id, match.user2_id,
        rating1.total_matches,
    )
    elo_change_user2 = _compute_elo_change(
        rating2.elo_rating, rating1.elo_rating,
        match.winner_id, match.user2_id, match.user1_id,
        rating2.total_matches,
    )

    # Persist user1's signed Elo delta for idempotent replay responses.
    match.elo_change = elo_change_user1

    # Update ratings
    _update_rating_after_match(rating1, match.winner_id, match.user1_id, elo_change_user1)
    _update_rating_after_match(rating2, match.winner_id, match.user2_id, elo_change_user2)

    # Clean up queue entries
    await db.execute(delete(PvPMatchmakingQueue).where(
        PvPMatchmakingQueue.user_id.in_([match.user1_id, match.user2_id])
    ))

    await db.commit()

    logger.info(
        "PvP match finalized: match=%s winner=%s score=%s-%s elo_change_user1=%.1f elo_change_user2=%.1f",
        str(match.id)[:8],
        str(match.winner_id)[:8] if match.winner_id else "draw",
        match.user1_score,
        match.user2_score,
        elo_change_user1,
        elo_change_user2,
    )

    # Build response for requesting user
    your_rating = rating1 if is_user1 else rating2
    your_elo_change = elo_change_user1 if is_user1 else elo_change_user2

    if match.winner_id == user_id:
        result = "win"
    elif match.winner_id is None:
        result = "draw"
    else:
        result = "loss"

    return {
        "match_id": str(match.id),
        "winner_id": str(match.winner_id) if match.winner_id else None,
        "result": result,
        "your_score": your_score,
        "opponent_score": opponent_score,
        "elo_change": your_elo_change,
        "new_elo": your_rating.elo_rating,
        "opponent_username": opponent.username if opponent else "Unknown",
    }


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ELO CALCULATION
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


# Compute signed Elo delta for one player using expected-score formula.
def _compute_elo_change(
    elo1: float,
    elo2: float,
    winner_id: Optional[uuid.UUID],
    user1_id: uuid.UUID,
    user2_id: uuid.UUID,
    total_matches: int,
) -> float:
    """Compute Elo change for user1.

    Uses standard Elo formula: K * (actual - expected)
    K = 32 for new players (< 30 games), 16 for experienced.

    Args:
        elo1: User 1's current Elo
        elo2: User 2's current Elo
        winner_id: UUID of the winner (None for draw)
        user1_id: User 1 UUID
        user2_id: User 2 UUID
        total_matches: User 1's total match count (for K-factor)

    Returns:
        float: Elo change for user1 (positive = gain, negative = loss)
    """
    k = ELO_K_NEW if total_matches < 30 else ELO_K_REGULAR
    expected = 1.0 / (1.0 + math_pow(10, (elo2 - elo1) / 400.0))

    if winner_id == user1_id:
        actual = 1.0
    elif winner_id == user2_id:
        actual = 0.0
    else:
        actual = 0.5  # Draw

    return round(k * (actual - expected), 1)


# Normalize stored user1 delta for both legacy and new match rows.
def _normalize_user1_delta_from_match(
    match: PvPMatch,
    rating_user1: Optional[PvPRating],
    rating_user2: Optional[PvPRating],
) -> float:
    """Normalize stored user1 delta for both new and legacy rows.

    New rows store signed user1 delta directly.
    Legacy rows stored absolute winner delta; this function infers sign.
    """
    user1_delta = float(match.elo_change or 0.0)

    # Legacy rows may store a positive absolute value for winner's gain.
    if match.winner_id == match.user2_id and user1_delta > 0:
        user1_delta = -user1_delta
    elif match.winner_id == match.user1_id and user1_delta < 0:
        user1_delta = -user1_delta
    elif match.winner_id is None and user1_delta > 0 and rating_user1 and rating_user2:
        if rating_user1.elo_rating > rating_user2.elo_rating:
            user1_delta = -user1_delta
        elif rating_user1.elo_rating == rating_user2.elo_rating:
            user1_delta = 0.0

    return round(user1_delta, 1)


# Infer user2 signed delta from post-state ratings and user1 delta.
def _infer_user2_delta_from_post_state(
    match: PvPMatch,
    rating_user1: Optional[PvPRating],
    rating_user2: Optional[PvPRating],
    user1_delta: float,
) -> float:
    """Infer user2 delta from post-match ratings and stored user1 delta.

    This preserves accurate idempotent responses without schema changes.
    """
    if rating_user1 is None or rating_user2 is None:
        return round(-user1_delta, 1)

    if match.winner_id == match.user1_id:
        actual_user1 = 1.0
    elif match.winner_id == match.user2_id:
        actual_user1 = 0.0
    else:
        actual_user1 = 0.5

    user1_total_matches_before = max(int(rating_user1.total_matches or 0) - 1, 0)
    k_user1 = ELO_K_NEW if user1_total_matches_before < 30 else ELO_K_REGULAR
    if k_user1 <= 0:
        return round(-user1_delta, 1)

    expected_user1 = actual_user1 - (float(user1_delta) / float(k_user1))
    expected_user1 = min(max(expected_user1, 1e-6), 1.0 - 1e-6)

    try:
        pre_gap = 400.0 * math_log10((1.0 / expected_user1) - 1.0)
    except (ValueError, ZeroDivisionError):
        return round(-user1_delta, 1)

    user1_pre_elo = float(rating_user1.elo_rating) - float(user1_delta)
    user2_pre_elo = user1_pre_elo + pre_gap
    user2_delta = float(rating_user2.elo_rating) - user2_pre_elo
    return round(user2_delta, 1)


# Apply Elo/streak/win-loss updates to one rating row.
def _update_rating_after_match(
    rating: PvPRating,
    winner_id: Optional[uuid.UUID],
    user_id: uuid.UUID,
    elo_delta: float,
) -> None:
    """Update a user's rating record after a match.

    Args:
        rating: PvPRating row to update
        winner_id: UUID of the match winner (None for draw)
        user_id: This user's UUID
        elo_delta: Elo change (positive or negative)
    """
    rating.elo_rating += elo_delta
    rating.total_matches += 1
    rating.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    if winner_id == user_id:
        rating.total_wins += 1
        rating.win_streak += 1
        rating.best_streak = max(rating.best_streak, rating.win_streak)
    elif winner_id is None:
        rating.total_draws += 1
        rating.win_streak = 0
    else:
        rating.total_losses += 1
        rating.win_streak = 0


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# LEADERBOARD / RATING QUERIES
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


# Return one user's rating and PvP aggregate statistics.
async def get_user_rating(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Get a user's PvP rating and stats.

    Args:
        db: AsyncSession
        user_id: User UUID

    Returns:
        dict with elo, wins, losses, etc.
    """
    user_exists = await db.scalar(select(User.id).where(User.id == user_id))
    if user_exists is None:
        raise ValueError("User not found")

    rating = await get_or_create_rating(db, user_id)
    total = rating.total_matches or 1  # avoid division by zero
    return {
        "user_id": str(user_id),
        "elo_rating": rating.elo_rating,
        "total_matches": rating.total_matches,
        "total_wins": rating.total_wins,
        "total_losses": rating.total_losses,
        "total_draws": rating.total_draws,
        "win_streak": rating.win_streak,
        "best_streak": rating.best_streak,
        "win_rate": round(rating.total_wins / total * 100, 1) if rating.total_matches > 0 else 0.0,
    }


# Return leaderboard entries ordered by Elo.
async def get_leaderboard(db: AsyncSession, limit: int = 20) -> dict:
    """Get the top PvP players by Elo rating.

    Args:
        db: AsyncSession
        limit: Max number of entries (capped at 50)

    Returns:
        dict with entries list and total_players count
    """
    capped = max(1, min(50, limit))

    total_players = await db.scalar(
        select(func.count()).select_from(PvPRating)
    ) or 0

    rows = await db.execute(
        select(PvPRating, User.username)
        .join(User, PvPRating.user_id == User.id)
        .order_by(PvPRating.elo_rating.desc())
        .limit(capped)
    )

    entries = []
    for i, (rating, username) in enumerate(rows.all(), 1):
        total = rating.total_matches or 1
        entries.append({
            "rank": i,
            "user_id": str(rating.user_id),
            "username": username,
            "elo_rating": rating.elo_rating,
            "total_wins": rating.total_wins,
            "total_matches": rating.total_matches,
            "win_rate": round(rating.total_wins / total * 100, 1) if rating.total_matches > 0 else 0.0,
        })

    return {"entries": entries, "total_players": total_players}

