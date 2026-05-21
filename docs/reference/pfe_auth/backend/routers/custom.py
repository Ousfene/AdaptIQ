"""
routers/custom.py — Custom Room REST endpoints.

Implements topic-focused study mode where users select a concept
(History theme or Geography country) and answer personalized MCQs.

Endpoints:
- GET /topics — List available topics
- POST /start-session — Initialize new Custom Room session
- POST /generate-question — Get next question
- POST /submit-answer — Submit answer and update progress
- POST /session/{id}/end — Finalize session
"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.core.dependencies import get_current_user
from database.models import User, QuestionBank
from dependencies import get_db, get_redis
from schemas import (
    CustomStartSessionRequest,
    CustomStartSessionResponse,
    GenerateCustomQuestionRequest,
    GenerateCustomQuestionResponse,
    SubmitCustomAnswerRequest,
    SubmitCustomAnswerResponse,
    CustomSessionEndRequest,
    CustomSessionEndResponse,
    TopicsListResponse,
    TopicOut,
)
from services.custom_service import CustomService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/custom", tags=["custom-room"])


# ──────────────────────────────────────────────────────────────────────────────
# GET /topics — List available topics
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/topics", response_model=TopicsListResponse)
async def get_topics():
    """
    Get list of all available Custom Room topics.

    Returns topics grouped by type (History, Geography) with descriptions
    and fact count (typically 1000 per topic).

    No authentication required (informational endpoint).
    """
    service = CustomService(None)
    topics_dict = service.get_topics()

    # Convert to TopicsListResponse format
    formatted_topics = {}
    for topic_type, topic_list in topics_dict.items():
        formatted_topics[topic_type] = [
            TopicOut(
                name=t["name"],
                slug=t["slug"],
                description=t["description"],
                total_facts=t["total_facts"],
            )
            for t in topic_list
        ]

    return TopicsListResponse(topics=formatted_topics)


# ──────────────────────────────────────────────────────────────────────────────
# POST /start-session — Create new Custom Room session
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/start-session", response_model=CustomStartSessionResponse, status_code=201)
async def start_custom_session(
    body: CustomStartSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Start a new Custom Room study session on a topic.

    User selects a topic (e.g., "History - World War II" or "Geography - France")
    and begins studying with personalized MCQs.

    Request body:
        - topic: str (full topic name, e.g., "History - World War II")

    Response:
        - session_id: UUID string
        - topic: str
        - progress_percentage: float (0-100, user's mastery % for this topic)
        - total_facts: int (typically 1000)
    """
    try:
        service = CustomService(db, redis)

        # Validate topic exists
        from config import CUSTOM_ROOM_TOPICS

        topic_found = False
        for topic_type, themes in CUSTOM_ROOM_TOPICS.items():
            if body.topic in [f"{topic_type} - {theme}" for theme in themes.keys()]:
                topic_found = True
                break

        if not topic_found:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid topic: {body.topic}",
            )

        # Create session
        result = await service.create_session(current_user.id, body.topic)

        logger.info(f"User {current_user.id} started Custom Room session on {body.topic}")

        return CustomStartSessionResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting Custom Room session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start session",
        )


# ──────────────────────────────────────────────────────────────────────────────
# POST /generate-question — Get next question
# ──────────────────────────────────────────────────────────────────────────────


@router.post(
    "/generate-question",
    response_model=GenerateCustomQuestionResponse,
)
async def generate_custom_question(
    body: GenerateCustomQuestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Generate next question for Custom Room session.

    Strategy:
    1. Pick unmastered fact first (user hasn't answered correctly yet)
    2. If all mastered, pick random fact for review
    3. Generate MCQ from fact via LLM (cache-first)
    4. Save question + question-fact link
    5. Store correct answer server-side in Redis session

    Request body:
        - session_id: str (UUID)
        - topic: str

    Response:
        - id: str
        - text: str
        - options: list[str] (4 options, shuffled)
        - explanation: null (revealed after answer submitted)
    """
    try:
        service = CustomService(db, redis)

        # Pick fact for this user on this topic
        fact = await service.pick_fact_for_user(current_user.id, body.topic)
        if not fact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No facts available for this topic",
            )

        # Generate question from fact
        question_dict = await service.generate_question_from_fact(fact, body.topic)
        if not question_dict:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate question",
            )

        # Update Redis session with correct answer (server-side)
        session_state = await service.session_service.get_session(body.session_id) or {}
        session_state["correct_answer"] = question_dict.get("correctAnswer")
        session_state["current_fact_id"] = str(fact.id)
        session_state["question_id"] = question_dict["id"]
        await service.session_service.set_session(body.session_id, session_state)

        logger.info(
            f"Generated question {question_dict['id']} for user {current_user.id}"
        )

        return GenerateCustomQuestionResponse(
            id=question_dict["id"],
            text=question_dict["text"],
            options=question_dict["options"],
            explanation=None,  # Don't reveal yet
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating Custom Room question: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate question",
        )


# ──────────────────────────────────────────────────────────────────────────────
# POST /submit-answer — Submit answer and update progress
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/submit-answer", response_model=SubmitCustomAnswerResponse)
async def submit_custom_answer(
    body: SubmitCustomAnswerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Submit answer to a Custom Room question.

    Flow:
    1. Get session from Redis (server-side correct answer stored)
    2. Check if user's answer matches correct answer
    3. Create UserResponse record for audit trail
    4. If correct: update user_topic_mastery (increment mastered count, recalculate %)
    5. Return correctness + explanation + new progress %

    Request body:
        - session_id: str (UUID)
        - question_id: str (UUID)
        - answer: str (user's chosen answer)

    Response:
        - is_correct: bool
        - explanation: str
        - new_progress_percentage: float
    """
    try:
        service = CustomService(db, redis)

        # Get session from Redis
        session_state = await service.session_service.get_session(body.session_id)
        if not session_state:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

        # Get correct answer (stored server-side)
        correct_answer = session_state.get("correct_answer")
        if not correct_answer:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Question state corrupted",
            )

        # Check correctness (case-insensitive, trimmed)
        is_correct = (
            body.answer.lower().strip() == correct_answer.lower().strip()
        )

        # Get question for explanation
        try:
            question_id = UUID(body.question_id)
            question = await db.get(QuestionBank, question_id)
        except ValueError:
            question = None

        if not question:
            explanation = "No explanation available"
        else:
            explanation = question.explanation or ""

        # Record in UserResponse (audit trail)
        from database.models import UserResponse
        from uuid import uuid4

        resp = UserResponse(
            id=uuid4(),
            user_id=current_user.id,
            session_id=UUID(body.session_id),
            question_id=UUID(body.question_id),
            topic=session_state.get("topic", "unknown"),
            difficulty_sent=3,  # Custom Room uses relative difficulty
            answered_correct=is_correct,
            time_taken=0,  # Could add time tracking later
            used_hint=False,
        )
        db.add(resp)
        await db.commit()

        # Update mastery if correct
        topic = session_state.get("topic")
        current_fact_id = session_state.get("current_fact_id")

        if is_correct and topic and current_fact_id:
            try:
                mastery = await service.update_topic_mastery(
                    current_user.id, topic, UUID(current_fact_id), is_correct
                )
                new_progress = mastery.completion_percentage
            except Exception as e:
                logger.warning(f"Failed to update mastery: {e}")
                new_progress = 0.0
        else:
            # Get current progress without update
            try:
                mastery = await service.get_or_create_mastery(
                    current_user.id, session_state.get("topic", "")
                )
                new_progress = mastery.completion_percentage
            except Exception:
                new_progress = 0.0

        # Update session counters
        session_state["questions_answered"] = session_state.get("questions_answered", 0) + 1
        if is_correct:
            session_state["correct_count"] = session_state.get("correct_count", 0) + 1
        await service.session_service.set_session(body.session_id, session_state)

        logger.info(
            f"User {current_user.id} answered question {body.question_id}: {is_correct}"
        )

        return SubmitCustomAnswerResponse(
            is_correct=is_correct,
            explanation=explanation,
            new_progress_percentage=round(new_progress, 2),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting Custom Room answer: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit answer",
        )


# ──────────────────────────────────────────────────────────────────────────────
# POST /session/{session_id}/end — End session
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/session/{session_id}/end", response_model=CustomSessionEndResponse)
async def end_custom_session(
    session_id: str,
    body: CustomSessionEndRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    End a Custom Room session and get summary.

    Finalizes the session in database, calculates session duration,
    and returns final statistics.

    URL params:
        - session_id: str (UUID)

    Response:
        - session_id: str
        - topic: str
        - questions_answered: int
        - correct_count: int
        - completion_percentage: float (final % for topic)
        - duration_seconds: int
    """
    try:
        service = CustomService(db, redis)

        result = await service.end_session(session_id)

        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result["error"],
            )

        logger.info(f"User {current_user.id} ended Custom Room session {session_id}")

        return CustomSessionEndResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending Custom Room session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to end session",
        )
