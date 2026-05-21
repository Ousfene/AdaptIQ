import asyncio
import json
import uuid
import logging
import hashlib
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.core.dependencies import get_current_user
from config import (
    GROQ_API_KEY,
    POINTS_BASE_AWARD,
    POINTS_TIME_BONUS_DIVISOR,
    QUIZ_TIME_LIMIT_SECONDS,
    compute_level,
    ENABLE_CONCEPT_TRACKING,
)
from database.models import User, UserResponse, QuestionBank, QuestionConcept, Concept, ClassicSession
from database.irt import difficulty_to_beta, beta_to_difficulty
from database.concept_irt import ConceptIRT
from database.crud import get_cached_question
from dependencies import get_db, get_http_client, get_redis, limiter
from rag.agentic import AgenticRAGPipeline
from schemas import (
    GenerateHintRequest,
    GenerateQuestionRequest,
    HintOut,
    QuestionOut,
    SubmitAnswerOut,
    SubmitAnswerRequest,
)
from services.llm import LLMClient
from services.session import SessionService
from services.concept_extractor import ConceptExtractor
from services.concept_cache_service import ConceptCacheService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rooms/classic", tags=["classic-room"])
rag_pipeline = AgenticRAGPipeline()


def _normalize_answer(value: str) -> str:
    # Normalize user-provided answers to avoid false negatives caused by casing/spacing variance.
    return value.strip().casefold()


def get_llm() -> LLMClient:
    return LLMClient(api_key=GROQ_API_KEY, timeout=20.0)


def get_session_service(redis=Depends(get_redis)) -> SessionService:
    return SessionService(redis=redis)


@router.post("/questions", response_model=QuestionOut)
async def generate_question(
    request: Request,
    body: GenerateQuestionRequest,
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Debug checkpoint for code reload verification
    logger.debug("generate_question function CALLED")

    if body.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="user_id does not match authenticated user")

    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="LLM not configured - set GROQ_API_KEY in .env")

    session = await session_service.get_session(str(body.session_id)) or {}
    current_difficulty = session.get("current_difficulty", body.difficulty)
    score = session.get("score", 0)
    total = session.get("total", 0)
    accuracy = score / total if total > 0 else 0.5
    seen_question_ids = set(session.get("seen_ids", []))

    llm = get_llm()
    question = None
    try:
        # ── PHASE 1: Try to fetch from cache (content reuse optimization) ────
        cached_question = await get_cached_question(db, body.topic, current_difficulty, seen_question_ids)
        if cached_question:
            question = {
                "id": cached_question.id,
                "text": cached_question.text,
                "options": cached_question.options,
                "correctAnswer": cached_question.correctAnswer,
                "explanation": cached_question.explanation,
            }
            logger.info("cache_hit", extra={"question_id": cached_question.id, "topic": body.topic})
        else:
            # Cache miss: generate via RAG pipeline
            try:
                http_client = getattr(request.app.state, "http_client", None)
                if http_client is None:
                    raise HTTPException(status_code=503, detail="HTTP client unavailable")

                question = await asyncio.wait_for(
                    rag_pipeline.run(
                        topic=body.topic,
                        difficulty=current_difficulty,
                        user_accuracy=accuracy,
                        llm_client=llm,
                        http_client=http_client,
                    ),
                    timeout=10.0  # Shorter than global 15s to force fallback faster
                )
            except asyncio.TimeoutError:
                logger.warning(f"RAG pipeline timeout for topic={body.topic}, difficulty={current_difficulty}")
                question = None  # Use fallback
    except Exception as e:
        logger.error(f"Question generation error: {type(e).__name__}: {e}", exc_info=True)
        question = None
    finally:
        await llm.close()

    if question is None:
        fallback_llm = get_llm()
        try:
            question = await fallback_llm.generate_mcq(
                context="Use your knowledge about this topic.",
                topic=body.topic,
                difficulty=body.difficulty,
                strategy="easy_recall",
            )
        finally:
            await fallback_llm.close()

    if question is None:
        raise HTTPException(status_code=503, detail="Could not generate question")

    question.setdefault("id", str(uuid.uuid4()))
    question.setdefault("explanation", "")
    question_id = question["id"] if isinstance(question["id"], uuid.UUID) else uuid.UUID(str(question["id"]))

    # ── SAVE QUESTION TO DATABASE (Critical for FK constraints) ────
    # The generated question must be persisted before creating QuestionConcept links
    # First check if question already exists (from cache or previous generation)
    existing_question = await db.get(QuestionBank, question_id)
    if existing_question:
        logger.info("question_already_exists", extra={"question_id": str(question_id), "topic": body.topic})
        # Update last_served_at and times_seen for the existing question
        existing_question.times_seen = (existing_question.times_seen or 0) + 1
        existing_question.last_served_at = datetime.utcnow()  # Use naive UTC for TIMESTAMP WITHOUT TIME ZONE
        await db.flush()
    else:
        try:
            qb = QuestionBank(
                id=question_id,
                question_text=question["text"],
                correct_answer=question["correctAnswer"],
                options_json=json.dumps(question["options"]),
                explanation=question.get("explanation", ""),
                topic=body.topic,
                difficulty_irt=difficulty_to_beta(current_difficulty),
                source="llm"
            )
            db.add(qb)
            await db.flush()
            logger.info("question_persisted", extra={"question_id": str(question_id), "topic": body.topic})
        except Exception as e:
            logger.error(f"Failed to persist question to database: {type(e).__name__}: {e}", exc_info=True)
            raise HTTPException(status_code=503, detail="Failed to persist question")

    # ── CONCEPT EXTRACTION & DIFFICULTY SELECTION (Phase 2) ──────────────────
    final_difficulty = current_difficulty
    concept_extractor = None  # Initialize outside try block

    if ENABLE_CONCEPT_TRACKING:
        try:
            concept_extractor = ConceptExtractor(get_llm())
            
            # ── OPTIMIZATION: Use LLM-provided concept if available (from MCQ generation) ──
            # This saves an additional LLM call when the MCQ generation already extracted concepts
            llm_provided_concept = question.get("concept")
            llm_provided_description = question.get("concept_description")

            if llm_provided_concept and isinstance(llm_provided_concept, str) and len(llm_provided_concept.strip()) > 2:
                # Use the concept already extracted during MCQ generation
                logger.info(f"Using LLM-provided concept: '{llm_provided_concept}'")
                primary_concept_id = await concept_extractor.ensure_concept_exists(
                    db, llm_provided_concept.strip(), body.topic
                )
                primary_concept_uuid = uuid.UUID(primary_concept_id)
                secondary_concept_uuid = None  # Secondary not provided inline
            else:
                # Fallback: Extract concepts from the question using separate Groq LLM call
                try:
                    concepts = await concept_extractor.extract_concepts(
                        question_text=question["text"],
                        options=question["options"],
                        topic=body.topic,
                    )

                    # Ensure concepts exist in DB
                    primary_name = concepts["primary"][0] if isinstance(concepts["primary"], list) else concepts["primary"]
                    primary_concept_id = await concept_extractor.ensure_concept_exists(
                        db, primary_name, body.topic
                    )
                    primary_concept_uuid = uuid.UUID(primary_concept_id)

                    # Get secondary concept but don't fail if it doesn't exist
                    try:
                        secondary_name = concepts["secondary"][0] if isinstance(concepts["secondary"], list) else concepts["secondary"]
                        secondary_concept_id = await concept_extractor.ensure_concept_exists(
                            db, secondary_name, body.topic
                        )
                        secondary_concept_uuid = uuid.UUID(secondary_concept_id)
                    except Exception as e:
                        logger.warning(f"Failed to create secondary concept: {e}")
                        secondary_concept_uuid = None
                except Exception as e:
                    logger.warning(f"Concept extraction failed, using fallback: {e}")
                    # Ultimate fallback: generic topic concept
                    primary_concept_id = await concept_extractor.ensure_concept_exists(
                        db, f"{body.topic.title()} General", body.topic
                    )
                    primary_concept_uuid = uuid.UUID(primary_concept_id)
                    secondary_concept_uuid = None

            # Link concepts to question in DB (runs for both LLM-provided and extracted concepts)
            try:
                primary_qc = QuestionConcept(
                    question_id=question_id,
                    concept_id=primary_concept_uuid,
                    is_primary=True,
                )
                db.add(primary_qc)

                if secondary_concept_uuid:
                    secondary_qc = QuestionConcept(
                        question_id=question_id,
                        concept_id=secondary_concept_uuid,
                        is_primary=False,
                    )
                    db.add(secondary_qc)

                await db.flush()
            except Exception as e:
                logger.warning(f"Failed to save question concepts: {e}")

            # ── TRACK CONCEPT EXPOSURE: Increment exposure_count for shown concepts ────
            # This helps us understand which concepts have been shown to the user
            try:
                await ConceptIRT.track_concept_exposure(db, uuid.UUID(str(current_user.id)), primary_concept_uuid)
                if secondary_concept_uuid:
                    await ConceptIRT.track_concept_exposure(db, uuid.UUID(str(current_user.id)), secondary_concept_uuid)
            except Exception as e:
                logger.warning(f"Failed to track exposure: {e}")

            # ── Initialize concept list for IRT calculation (before auto-discovery) ────────────────
            concept_ids = [primary_concept_uuid]
            if secondary_concept_uuid:
                concept_ids.append(secondary_concept_uuid)

            # ── AUTO-DISCOVERY: Inject new concept with 20% probability ────────────────
            # Goal: Users gradually discover new concepts, not just master known ones
            try:
                known_concept_count = await ConceptIRT.get_user_concept_count(db, uuid.UUID(str(current_user.id)))

                # If user has seen fewer than 5 concepts, 20% chance to introduce a new one
                if known_concept_count < 5 and random.random() < 0.20:
                    # Get all concepts that user hasn't encountered yet
                    all_concepts_stmt = select(Concept).where(Concept.topic == body.topic)
                    all_concepts_result = await db.execute(all_concepts_stmt)
                    all_concepts = all_concepts_result.scalars().all()

                    if all_concepts:
                        all_concept_ids = [uuid.UUID(str(c.id)) for c in all_concepts]
                        unknown_concept_ids = await ConceptIRT.get_unknown_concepts(
                            db, uuid.UUID(str(current_user.id)), all_concept_ids
                        )

                        if unknown_concept_ids:
                            # Randomly pick one unknown concept for discovery
                            new_concept_id = random.choice(unknown_concept_ids)

                            # Add it to the question's concepts (as secondary discovery)
                            discovery_qc = QuestionConcept(
                                question_id=question_id,
                                concept_id=new_concept_id,
                                is_primary=False,  # Mark as discovery, not primary focus
                            )
                            db.add(discovery_qc)

                            # Track the exposure (first_seen_at = now)
                            await ConceptIRT.track_concept_exposure(db, uuid.UUID(str(current_user.id)), new_concept_id)

                            # Add to concept list for IRT calculation
                            concept_ids.append(new_concept_id)

                            logger.info(
                                "concept_discovery_event",
                                extra={
                                    "user_id": str(current_user.id),
                                    "discovered_concept_id": str(new_concept_id),
                                    "topic": body.topic,
                                }
                            )

                            await db.flush()
            except Exception as e:
                logger.warning(f"Auto-discovery failed (non-critical): {e}")

            # ── SMART DIFFICULTY SELECTION: Use weakest concept ────────────────
            # Get user's theta for all question concepts (concept_ids already initialized above)
            weakest_theta = await ConceptIRT.get_weakest_concept_theta(
                db, uuid.UUID(str(current_user.id)), concept_ids
            )

            # Convert theta to difficulty level (1-5)
            ideal_difficulty = beta_to_difficulty(weakest_theta)
            assert 1 <= ideal_difficulty <= 5, f"ideal_difficulty {ideal_difficulty} out of range"

            # Clamp to ±1 from current difficulty (smooth progression)
            min_diff = max(1, current_difficulty - 1)
            max_diff = min(5, current_difficulty + 1)
            final_difficulty = max(min_diff, min(max_diff, ideal_difficulty))
            assert 1 <= final_difficulty <= 5, f"final_difficulty {final_difficulty} out of range after clamping"

            logger.info(
                "concept_aware_difficulty",
                extra={
                    "user_id": str(current_user.id),
                    "weakest_theta": round(weakest_theta, 2),
                    "ideal_difficulty": ideal_difficulty,
                    "final_difficulty": final_difficulty,
                }
            )

        except Exception as e:
            # If concept processing fails, fall back to current difficulty
            logger.warning(
                "concept_tracking_failover",
                extra={"error": str(e), "user_id": str(current_user.id)}
            )
            final_difficulty = current_difficulty
        
        finally:
            if concept_extractor:
                try:
                    await concept_extractor.llm_client.close()
                except Exception:
                    pass  # Ignore cleanup errors

    # Store the correct answer and topic server-side so submit_answer can verify and record
    session["correct_answer"] = question["correctAnswer"]
    session["current_difficulty"] = final_difficulty
    session["topic"] = body.topic
    session["user_id"] = str(current_user.id)
    session["question_id"] = str(question["id"])
    session["question_sent_at"] = datetime.now(timezone.utc).timestamp()  # ADDED: Server-side timestamp for time calculation
    await session_service.set_session(str(body.session_id), session)

    # Unlock submission state: UI can now accept answers
    await session_service.set_submission_state(str(body.session_id), "ready")

    return QuestionOut(
        id=question["id"],
        text=question["text"],
        options=question["options"],
        # Legacy V1 compatibility: this endpoint still returns correctAnswer.
        correctAnswer=question["correctAnswer"],
        explanation=question["explanation"],
        locked=False,  # UI can accept answers
    )


@limiter.limit("30/minute")
@router.post("/hints", response_model=HintOut)
async def generate_hint(
    request: Request,
    body: GenerateHintRequest,
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user)
):
    _ = current_user
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="LLM not configured - set GROQ_API_KEY in .env")

    # Prefer secure session-based answer lookup; allow legacy fallback for older clients.
    correct_answer = None
    if body.session_id is not None:
        session = await session_service.get_session(str(body.session_id))
        if session and session.get("correct_answer"):
            correct_answer = session["correct_answer"]

    if correct_answer is None:
        if not body.correctAnswer:
            raise HTTPException(status_code=400, detail="No active question in session")
        correct_answer = body.correctAnswer

    llm = get_llm()
    try:
        hint = await llm.generate_hint(body.questionText, correct_answer)
    finally:
        await llm.close()

    if hint is None:
        raise HTTPException(status_code=503, detail="Could not generate hint")
    return HintOut(hint=hint)


@limiter.limit("20/minute")
@router.post("/answers", response_model=SubmitAnswerOut, response_model_exclude_none=True)
async def submit_answer(
    request: Request,
    body: SubmitAnswerRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
):
    if body.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="user_id does not match authenticated user")

    # CRITICAL FIX 8.1: Verify session ownership to prevent cross-user access
    session_data = await session_service.get_session(str(body.session_id))
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    if session_data.get("user_id") != str(current_user.id):
        raise HTTPException(status_code=403, detail="Session does not belong to you")

    if not body.selected_answer.strip():
        raise HTTPException(status_code=422, detail="selected_answer cannot be empty")

    # ── Idempotency Check: Prevent duplicate answer processing ────────────────
    # CRITICAL FIX 4.2: Include session_id to prevent cross-session collisions
    answer_hash = hashlib.sha256(
        f"{str(body.user_id)}{str(body.session_id)}{str(body.question_id)}{body.selected_answer}".encode()
    ).hexdigest()

    cached_result = await session_service.is_submission_duplicate(
        str(body.user_id), str(body.question_id), answer_hash
    )
    if cached_result:
        logger.info("idempotent_resubmission", extra={"user_id": str(body.user_id), "question_id": str(body.question_id)})
        return SubmitAnswerOut(
            success=cached_result.get("success", True),
            updated_difficulty=cached_result.get("updated_difficulty", 2),
            locked=True,  # Stay locked until next question ready
        )

    # ── Set submission state to processing (lock UI) ─────────────────────────
    await session_service.set_submission_state(str(body.session_id), "processing")

    session = await session_service.get_session(str(body.session_id)) or {
        "current_difficulty": 2,
        "score": 0,
        "total": 0,
    }

    seen_ids = session.get("seen_ids", [])
    if str(body.question_id) in seen_ids:
        raise HTTPException(status_code=409, detail="Question already answered in this session")

    # Verify answer correctness server-side using the answer stored during generate_question
    is_correct = bool(
        session.get("correct_answer")
        and _normalize_answer(str(session["correct_answer"])) == _normalize_answer(body.selected_answer)
    )

    total = session.get("total", 0) + 1
    score = session.get("score", 0) + (1 if is_correct else 0)
    accuracy = score / total if total > 0 else 0.5

    difficulty = session.get("current_difficulty", 2)
    if accuracy > 0.75:
        difficulty = min(5, difficulty + 1)
    elif accuracy < 0.40:
        difficulty = max(1, difficulty - 1)

    session["current_difficulty"] = difficulty
    session["total"] = total
    session["score"] = score

    # Track seen questions for cache avoidance
    seen_ids = session.get("seen_ids", [])
    if str(body.question_id) not in seen_ids:
        seen_ids.append(str(body.question_id))
    session["seen_ids"] = seen_ids

    # ADDED: Calculate server-side time instead of trusting client
    question_sent_at = session.get("question_sent_at", datetime.now(timezone.utc).timestamp())
    now = datetime.now(timezone.utc).timestamp()
    time_taken_seconds = max(0, min(
        now - question_sent_at,  # Actual server time
        QUIZ_TIME_LIMIT_SECONDS  # Cap at time limit
    ))

    await session_service.set_session(str(body.session_id), session)

    # Persist response record for statistics queries
    try:
        resp_record = UserResponse(
            id=uuid.uuid4(),
            user_id=current_user.id,
            session_id=body.session_id,  # Already a UUID from Pydantic
            question_id=body.question_id,  # Already a UUID from Pydantic
            topic=session.get("topic", "Mixed"),
            difficulty_sent=difficulty,
            answered_correct=is_correct,
            time_taken=int(time_taken_seconds),  # SERVER-CALCULATED time (not client value)
            used_hint=body.used_hint,
        )
        db.add(resp_record)
    except ValueError as e:
        logger.error("invalid_uuid_format", extra={"error": str(e)})
        raise HTTPException(status_code=400, detail="Invalid request format")
    except (AttributeError, Exception) as e:
        logger.error("response_recording_failed", extra={"error": str(e), "user_id": str(current_user.id)})
        raise HTTPException(status_code=500, detail="Failed to record answer")

    # Award points for correct answers (configurable constants live in config.py)
    if is_correct:
        # Use server-calculated time (already in seconds above)
        time_left = max(0, QUIZ_TIME_LIMIT_SECONDS - time_taken_seconds)
        points_earned = POINTS_BASE_AWARD + int(time_left) // POINTS_TIME_BONUS_DIVISOR
        result = await db.execute(select(User).where(User.id == current_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.points = (user.points or 0) + points_earned  # type: ignore[assignment]
            user.level = compute_level(user.points)  # type: ignore[assignment]

    # ── UPDATE CONCEPT THETAS (Phase 2.7) ──────────────────────────────────────
    # If concept tracking enabled, update per-concept ability estimates
    if ENABLE_CONCEPT_TRACKING:
        try:
            # Fetch all concepts for this question
            stmt = select(QuestionConcept).where(QuestionConcept.question_id == body.question_id)
            result = await db.execute(stmt)
            question_concepts = result.scalars().all()

            if question_concepts:
                # Convert difficulty to IRT beta for accurate theta calculation
                beta = difficulty_to_beta(session.get("current_difficulty", 2))

                # Update theta for each concept
                for qc in question_concepts:
                    try:
                        new_theta = await ConceptIRT.update_concept_theta(
                            db,
                            uuid.UUID(str(current_user.id)),
                            uuid.UUID(str(qc.concept_id)),
                            beta,
                            is_correct,
                        )
                        logger.info(
                            "concept_theta_updated",
                            extra={
                                "user_id": str(current_user.id),
                                "concept_id": str(qc.concept_id),
                                "new_theta": round(new_theta, 2),
                                "correct": is_correct,
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update concept theta: {e}")
        except Exception as e:
            logger.warning(f"Concept theta update skipped: {e}")

    await db.commit()

    # ── Cache result for idempotency and return locked ────────────────────────
    correct_answer = session.get("correct_answer", "")
    result_to_cache = {
        "success": True,
        "updated_difficulty": difficulty,
    }
    await session_service.record_submission(str(body.user_id), str(body.question_id), answer_hash, result_to_cache)

    return SubmitAnswerOut(
        success=True,
        updated_difficulty=difficulty,
        locked=True
    )


# ────────────────────────────────────────────────────────────────────────────
# V2 Session-Based Endpoints (per AGENT_PROMPT.md spec)
# ────────────────────────────────────────────────────────────────────────────
from schemas import (
    ClassicStartRequest,
    ClassicStartResponse,
    ClassicAnswerRequest,
    ClassicAnswerResponse,
    ClassicHintRequest,
    ClassicHintResponse,
    ClassicMetricsResponse,
    ClassicQuestionOut,
    SessionStatsOut,
)
from services.classic_service import ClassicService


@limiter.limit("20/minute")
@router.post("/start", response_model=ClassicStartResponse)
async def start_classic_session(
    request: Request,
    body: ClassicStartRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
):
    """
    Start a new classic room session.
    
    Creates a session, selects concepts, and returns the first question.
    """
    result = await ClassicService.start_session(
        db=db,
        user_id=current_user.id,
        topic=body.topic,
        session_service=session_service,
    )
    
    await db.commit()
    
    # Transform question to ClassicQuestionOut (no correct answer)
    first_q = result["first_question"]
    question_out = None
    if first_q:
        question_out = ClassicQuestionOut(
            id=first_q["id"],
            text=first_q["text"],
            options=first_q["options"],
            topic=first_q["topic"],
            difficulty=first_q["difficulty"],
        )
    
    return ClassicStartResponse(
        session_id=result["session_id"],
        first_question=question_out,
        session_stats=SessionStatsOut(**result["session_stats"]),
    )


@limiter.limit("20/minute")
@router.post("/answer/{session_id}", response_model=ClassicAnswerResponse)
async def answer_classic_question(
    request: Request,
    session_id: str,
    body: ClassicAnswerRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
):
    """
    Submit an answer to a classic room question.
    
    Updates concept thetas and returns the next question.
    """
    # ═══════ SESS-1 FIX: Pre-validate session ownership ═══════
    # Validate session ownership before processing to give clear error
    # and prevent unnecessary DB queries
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")
    
    session_stmt = select(ClassicSession).where(ClassicSession.id == session_uuid)
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Session does not belong to you")
    # ═════════════════════════════════════════════════════════════
    
    # ═══════ V2-1 FIX: Add idempotency check ═══════
    # Prevent duplicate answer submissions using hash of user+session+question+answer
    answer_hash = hashlib.sha256(
        f"{current_user.id}:{session_id}:{str(body.question_id)}:{body.selected_index}".encode()
    ).hexdigest()  # Use full 64-char hash; add explicit str() for UUID
    
    cached_result = await session_service.is_submission_duplicate(
        str(current_user.id), body.question_id, answer_hash
    )
    if cached_result:
        # Return cached result for idempotent replay
        logger.info("idempotent_replay", extra={
            "user_id": str(current_user.id),
            "session_id": session_id,
            "question_id": body.question_id,
        })
        next_q = cached_result.get("next_question")
        next_question_out = None
        if next_q:
            next_question_out = ClassicQuestionOut(
                id=next_q["id"],
                text=next_q["text"],
                options=next_q["options"],
                topic=next_q["topic"],
                difficulty=next_q["difficulty"],
            )
        return ClassicAnswerResponse(
            correct=cached_result["correct"],
            correct_index=cached_result["correct_index"],
            explanation=cached_result["explanation"],
            theta_change=cached_result.get("theta_change", 0.0),
            next_question=next_question_out,
            session_stats=SessionStatsOut(**cached_result["session_stats"]),
            session_ended=cached_result["session_ended"],
        )
    # ═════════════════════════════════════════════════════════════
    
    try:
        result = await ClassicService.process_answer(
            db=db,
            user_id=current_user.id,
            session_id=session_uuid,
            question_id=uuid.UUID(body.question_id),
            selected_index=body.selected_index,
            time_taken_seconds=body.time_taken_seconds,
            session_service=session_service,
            used_hint=body.used_hint,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    await db.commit()
    
    # ═══════ V2-1 FIX: Cache result for idempotency ═══════
    await session_service.record_submission(
        str(current_user.id), body.question_id, answer_hash, result
    )
    # ═════════════════════════════════════════════════════════════
    
    # Transform next question
    next_q = result["next_question"]
    next_question_out = None
    if next_q:
        next_question_out = ClassicQuestionOut(
            id=next_q["id"],
            text=next_q["text"],
            options=next_q["options"],
            topic=next_q["topic"],
            difficulty=next_q["difficulty"],
        )
    
    return ClassicAnswerResponse(
        correct=result["correct"],
        correct_index=result["correct_index"],
        explanation=result["explanation"],
        theta_change=result["theta_change"],
        next_question=next_question_out,
        session_stats=SessionStatsOut(**result["session_stats"]),
        session_ended=result["session_ended"],
    )


@limiter.limit("30/minute")
@router.post("/hint/{session_id}", response_model=ClassicHintResponse)
async def get_classic_hint(
    request: Request,
    session_id: str,
    body: ClassicHintRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
):
    """
    Get a hint for a question.

    Returns cached hint if available, otherwise generates one.
    Verifies session ownership before serving hint.
    """
    # Verify session ownership
    # V2 sessions use store_session_state (key: "state:{id}"), try that first
    session_data = await session_service.get_session_state(session_id)
    if not session_data:
        # Fallback to V1 session (key: "session:{id}")
        session_data = await session_service.get_session(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    stored_user_id = session_data.get("user_id")
    if str(stored_user_id) != str(current_user.id):
        logger.warning(f"Session {session_id} ownership check failed: user {current_user.id} tried to access session of user {stored_user_id}")
        raise HTTPException(status_code=403, detail="Session does not belong to you")
    
    llm = get_llm() if GROQ_API_KEY else None
    try:
        hint = await ClassicService.get_hint(
            db=db,
            question_id=uuid.UUID(body.question_id),
            llm_client=llm,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        if llm:
            await llm.close()
    
    await db.commit()
    
    return ClassicHintResponse(hint=hint)


@router.get("/metrics/{session_id}", response_model=ClassicMetricsResponse)
async def get_classic_metrics(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get metrics for a classic room session.
    
    Returns accuracy, theta progress, and adaptivity score.
    """
    try:
        metrics = await ClassicService.get_session_metrics(
            db=db,
            user_id=current_user.id,
            session_id=uuid.UUID(session_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    return ClassicMetricsResponse(
        accuracy=metrics["accuracy"],
        theta_progress=[],  # Would need session state tracking for full progress
        adaptivity_score=metrics["adaptivity_score"],
        total_questions=metrics["total_questions"],
        correct_count=metrics["correct_count"],
        topic=metrics["topic"],
    )