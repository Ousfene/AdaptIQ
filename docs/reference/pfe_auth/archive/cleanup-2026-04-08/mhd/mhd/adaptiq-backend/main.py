"""
main.py — FastAPI application for AdaptIQ Classic Room backend.

Endpoints:
  POST /api/classic/generate-question  → QuestionOut
  POST /api/classic/generate-hint      → HintOut
  POST /api/classic/submit-answer      → SubmitAnswerOut
  GET  /health                         → HealthOut
"""

import os
import time
import uuid
import random
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import httpx
import structlog
from fastapi import FastAPI, HTTPException, Request, Depends, Body
from typing import Annotated
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from pydantic_types import (
    TopicType,
    QuestionOut,
    GenerateQuestionRequest,
    GenerateHintRequest,
    HintOut,
    SubmitAnswerRequest,
    SubmitAnswerOut,
    HealthOut,
)
from database.models import Base
from database.irt import (
    UserAbilityTracker,
    next_difficulty,
    difficulty_to_beta,
    update_theta,
)
from database import crud
from rag.agentic import AgenticRAGPipeline
from rag.hf_dataset import load_hf_dataset
from services.llm import LLMClient
from services.session import SessionService
from routers.challenge import challenge_router

# ═══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://adaptiq:adaptiq@localhost:5432/adaptiq_db")
REDIS_URL    = os.getenv("REDIS_URL", "redis://localhost:6379")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LOG_LEVEL    = os.getenv("LOG_LEVEL", "INFO")
ENVIRONMENT  = os.getenv("ENVIRONMENT", "development")

# ═══════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer() if ENVIRONMENT == "development"
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# APP STATE
# ═══════════════════════════════════════════════════════════════════════
class AppState:
    db_engine          = None
    db_session_factory = None
    redis              = None
    llm_client: Optional[LLMClient] = None
    http_client: Optional[httpx.AsyncClient] = None
    session_service: Optional[SessionService] = None
    rag_pipeline: Optional[AgenticRAGPipeline] = None

app_state = AppState()


# ═══════════════════════════════════════════════════════════════════════
# LIFESPAN
# ═══════════════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AdaptIQ backend starting up")

    try:
        app_state.db_engine = create_async_engine(
            DATABASE_URL, echo=(ENVIRONMENT == "development"),
            pool_size=10, max_overflow=20,
        )
        app_state.db_session_factory = async_sessionmaker(
            app_state.db_engine, expire_on_commit=False
        )
        async with app_state.db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL connected and tables ready")
    except Exception as e:
        logger.warning(f"PostgreSQL unavailable ({e}) — DB features disabled")
        app_state.db_engine = None

    redis_instance = None
    try:
        import redis.asyncio as aioredis
        redis_instance = await aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        await redis_instance.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}) — using in-memory session store")

    app_state.redis = redis_instance
    app_state.http_client = httpx.AsyncClient(
        timeout=15.0, limits=httpx.Limits(max_connections=50, max_keepalive_connections=20)
    )
    app_state.session_service = SessionService(redis=redis_instance)

    if GROQ_API_KEY:
        app_state.llm_client = LLMClient(api_key=GROQ_API_KEY)
        logger.info("Groq LLM client ready")
    else:
        logger.warning("GROQ_API_KEY not set — LLM generation disabled")

    app_state.rag_pipeline = AgenticRAGPipeline()
    asyncio.create_task(load_hf_dataset())
    logger.info("HF dataset loading in background")
    logger.info("AdaptIQ backend ready ✓")
    app.state.db_session_factory = app_state.db_session_factory
    app.state.llm_client         = app_state.llm_client
    app.state.rag_pipeline       = app_state.rag_pipeline
    app.state.http_client        = app_state.http_client

    yield

    logger.info("Shutting down")
    if app_state.http_client:  await app_state.http_client.aclose()
    if app_state.llm_client:   await app_state.llm_client.close()
    if app_state.db_engine:    await app_state.db_engine.dispose()
    if app_state.redis:        await app_state.redis.aclose()
    logger.info("Shutdown complete")


# ═══════════════════════════════════════════════════════════════════════
# RATE LIMITER + APP
# ═══════════════════════════════════════════════════════════════════════
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="AdaptIQ Classic Room API",
    version="1.0.0",
    description="Adaptive MCQ backend — IRT + Agentic RAG",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(challenge_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.4f}s"
    return response


# ═══════════════════════════════════════════════════════════════════════
# DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════
async def get_db() -> AsyncSession:
    if app_state.db_session_factory is None:
        raise HTTPException(503, detail="Database unavailable")
    async with app_state.db_session_factory() as session:
        yield session

def get_session_service() -> SessionService:
    return app_state.session_service

def get_llm() -> LLMClient:
    if app_state.llm_client is None:
        raise HTTPException(503, detail="LLM client unavailable — set GROQ_API_KEY")
    return app_state.llm_client

def get_rag() -> AgenticRAGPipeline:
    return app_state.rag_pipeline

def get_http() -> httpx.AsyncClient:
    return app_state.http_client


# ═══════════════════════════════════════════════════════════════════════
# DIRECT LLM QUESTION GENERATION (used when RAG fails / network blocked)
# This is the KEY FIX — generates fresh unique questions without needing
# Wikipedia/Wikidata which are blocked in your network environment.
# ═══════════════════════════════════════════════════════════════════════
TOPIC_PROMPTS = {
    "History": [
        "ancient civilizations (Egypt, Greece, Rome, Mesopotamia)",
        "medieval kingdoms and empires (Byzantine, Ottoman, Mongol)",
        "the Renaissance and Age of Exploration",
        "the French Revolution and Napoleonic era",
        "World War I causes and major battles",
        "World War II turning points and aftermath",
        "the Cold War and space race",
        "African empires and kingdoms",
        "Asian dynasties (Tang, Ming, Mughal, Qing)",
        "revolutions and independence movements",
    ],
    "Geography": [
        "world capitals and major cities",
        "rivers, mountains, and natural wonders",
        "countries of Africa and their geography",
        "countries of Asia and their borders",
        "South American geography and landmarks",
        "European geography and countries",
        "oceans, seas, and island nations",
        "deserts and climate zones",
        "landlocked countries and island chains",
        "population and area statistics of countries",
    ],
    "Mixed": [
        "famous scientists and their discoveries",
        "world religions and their origins",
        "ancient and modern wonders of the world",
        "famous historical figures and their impact",
        "significant inventions and their inventors",
        "world records and superlatives",
        "famous battles across different eras",
        "major empires throughout history",
        "cultural achievements and arts",
        "economic history and trade routes",
    ],
}

async def _generate_with_llm_direct(
    topic: str,
    difficulty: int,
    llm_client: LLMClient,
    seen_texts: list[str] = None,
) -> Optional[dict]:
    """
    Call the LLM directly with a rich prompt — no RAG needed.
    Used as primary fallback when network-based RAG fails.
    """
    subtopics = TOPIC_PROMPTS.get(topic, TOPIC_PROMPTS["Mixed"])
    # Pick a random subtopic to ensure variety
    subtopic = random.choice(subtopics)

    # Include seen question texts to avoid repeats
    avoid_str = ""
    if seen_texts:
        avoid_str = f"\nDo NOT generate questions about: {'; '.join(seen_texts[-5:])}"

    context = f"""Topic area: {subtopic} (part of {topic})
Generate a question specifically about {subtopic}.
Make it unique and specific — not a generic textbook question.{avoid_str}"""

    return await llm_client.generate_mcq(
        context=context,
        topic=topic,
        difficulty=difficulty,
        strategy="direct",
        user_accuracy=0.5,
    )


def _make_fallback_question(topic: str, difficulty: int) -> QuestionOut:
    """
    Last-resort static fallback — only reached if LLM itself fails.
    Options are now SHUFFLED so correct answer is never always first.
    """
    fallbacks = {
        "History": [
            {"text": "Which battle marked the turning point of WWII on the Eastern Front?",
             "correct": "Battle of Stalingrad",
             "wrong": ["Battle of Kursk", "Operation Barbarossa", "Siege of Leningrad"],
             "explanation": "The Battle of Stalingrad (1942–43) ended German advances into the Soviet Union."},
            {"text": "In which year did the French Revolution begin?",
             "correct": "1789",
             "wrong": ["1776", "1804", "1815"],
             "explanation": "The French Revolution began in 1789 with the storming of the Bastille on July 14."},
            {"text": "Who was the first Roman Emperor?",
             "correct": "Augustus",
             "wrong": ["Julius Caesar", "Nero", "Constantine"],
             "explanation": "Augustus (Octavian) became the first Roman Emperor in 27 BC after defeating Mark Antony."},
            {"text": "The Magna Carta was signed in which year?",
             "correct": "1215",
             "wrong": ["1066", "1348", "1492"],
             "explanation": "King John of England signed the Magna Carta in 1215, limiting royal power."},
            {"text": "Which empire was ruled by Genghis Khan?",
             "correct": "Mongol Empire",
             "wrong": ["Ottoman Empire", "Roman Empire", "Persian Empire"],
             "explanation": "Genghis Khan founded and ruled the Mongol Empire, the largest contiguous empire in history."},
            {"text": "The Berlin Wall fell in which year?",
             "correct": "1989",
             "wrong": ["1991", "1985", "1979"],
             "explanation": "The Berlin Wall fell on November 9, 1989, symbolizing the end of the Cold War."},
        ],
        "Geography": [
            {"text": "What is the capital city of Australia?",
             "correct": "Canberra",
             "wrong": ["Sydney", "Melbourne", "Brisbane"],
             "explanation": "Canberra is Australia's capital, chosen as a compromise between Sydney and Melbourne in 1901."},
            {"text": "Which is the longest river in Africa?",
             "correct": "Nile River",
             "wrong": ["Congo River", "Niger River", "Zambezi River"],
             "explanation": "The Nile River stretches approximately 6,650 km, making it the longest river in Africa."},
            {"text": "Which country has the largest land area in the world?",
             "correct": "Russia",
             "wrong": ["Canada", "China", "United States"],
             "explanation": "Russia covers approximately 17.1 million km², making it the world's largest country by area."},
            {"text": "What is the smallest country in the world by area?",
             "correct": "Vatican City",
             "wrong": ["Monaco", "San Marino", "Liechtenstein"],
             "explanation": "Vatican City covers only 0.44 km², making it the world's smallest internationally recognized state."},
            {"text": "Which ocean is the largest by surface area?",
             "correct": "Pacific Ocean",
             "wrong": ["Atlantic Ocean", "Indian Ocean", "Arctic Ocean"],
             "explanation": "The Pacific Ocean covers about 165 million km², making it the largest ocean on Earth."},
            {"text": "Mount Everest is located in which mountain range?",
             "correct": "Himalayas",
             "wrong": ["Andes", "Alps", "Rockies"],
             "explanation": "Mount Everest, the world's highest peak at 8,849m, is part of the Himalayan mountain range."},
        ],
        "Mixed": [
            {"text": "Which country has the most UNESCO World Heritage Sites?",
             "correct": "Italy",
             "wrong": ["France", "China", "Spain"],
             "explanation": "Italy leads with the most UNESCO World Heritage Sites, reflecting its extraordinary heritage."},
            {"text": "Who invented the telephone?",
             "correct": "Alexander Graham Bell",
             "wrong": ["Thomas Edison", "Nikola Tesla", "Guglielmo Marconi"],
             "explanation": "Alexander Graham Bell patented the telephone in 1876, revolutionizing communication."},
            {"text": "What is the chemical symbol for gold?",
             "correct": "Au",
             "wrong": ["Go", "Gd", "Ag"],
             "explanation": "Gold's symbol Au comes from the Latin word 'aurum', meaning gold."},
        ],
    }

    pool = fallbacks.get(topic, fallbacks["Mixed"])
    chosen = random.choice(pool)

    # Build and SHUFFLE options
    options = [chosen["correct"]] + chosen["wrong"]
    random.shuffle(options)

    return QuestionOut(
        id=str(uuid.uuid4()),
        text=chosen["text"],
        options=options,
        correctAnswer=chosen["correct"],
        explanation=chosen["explanation"],
    )


# ═══════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════

@app.get("/health", response_model=HealthOut)
async def health_check():
    services = {}
    services["database"] = "ok" if app_state.db_engine else "unavailable"
    if app_state.redis:
        try:
            await app_state.redis.ping()
            services["redis"] = "ok"
        except Exception:
            services["redis"] = "error"
    else:
        services["redis"] = "in-memory fallback"
    services["llm"] = "ok" if app_state.llm_client else "no api key"
    from rag.hf_dataset import _dataset
    services["hf_dataset"] = "ok" if _dataset is not None else "loading"
    return HealthOut(status="ok", version="1.0.0", services=services)


@app.post("/api/classic/generate-question", response_model=QuestionOut)
@limiter.limit("30/minute")
async def generate_question(
    request: Request,
    body: Annotated[GenerateQuestionRequest, Body()],
    session_svc: SessionService = Depends(get_session_service),
    rag: AgenticRAGPipeline = Depends(get_rag),
    http_client: httpx.AsyncClient = Depends(get_http),
):
    logger.info("generate_question", topic=body.topic, difficulty=body.difficulty,
                user_id=body.user_id, session_id=body.session_id)

    # Session init / load
    session_data = await session_svc.get_session(body.session_id)
    if session_data is None:
        await session_svc.initialize_session(
            session_id=body.session_id, user_id=body.user_id,
            topic=body.topic, difficulty=body.difficulty,
        )
        session_data = {}

    effective_difficulty = session_data.get("current_difficulty", body.difficulty)

    user_accuracy = 0.5
    if app_state.db_engine:
        try:
            async with app_state.db_session_factory() as db:
                user_accuracy = await crud.get_user_accuracy_by_topic(db, body.user_id, body.topic)
        except Exception as e:
            logger.warning(f"Could not fetch user accuracy: {e}")

    seen_ids = await session_svc.get_seen_ids(body.session_id)
    # Collect seen question texts for LLM dedup prompt
    seen_texts = session_data.get("seen_texts", [])

    question_dict = None

    # ── Step 1: Try Agentic RAG (Wikipedia/Wikidata) ─────────────────────
    if app_state.llm_client:
        try:
            question_dict = await rag.run(
                topic=body.topic,
                difficulty=effective_difficulty,
                user_accuracy=user_accuracy,
                llm_client=app_state.llm_client,
                http_client=http_client,
            )
            if question_dict:
                logger.info("question_source: rag")
        except Exception as e:
            logger.warning(f"RAG pipeline failed: {e}")

    # ── Step 2: RAG failed (network blocked) → call LLM directly ─────────
    if not question_dict and app_state.llm_client:
        try:
            logger.info("RAG unavailable — using direct LLM generation")
            question_dict = await _generate_with_llm_direct(
                topic=body.topic,
                difficulty=effective_difficulty,
                llm_client=app_state.llm_client,
                seen_texts=seen_texts,
            )
            if question_dict:
                question_dict["source"] = "llm_direct"
                logger.info("question_source: llm_direct")
        except Exception as e:
            logger.error(f"Direct LLM generation failed: {e}")

    # ── Step 3: Everything failed → static fallback ───────────────────────
    if not question_dict:
        logger.warning("All generation methods failed — using static fallback")
        q = _make_fallback_question(body.topic, effective_difficulty)
    else:
        if "id" not in question_dict or not question_dict["id"]:
            question_dict["id"] = str(uuid.uuid4())
        q = QuestionOut(**question_dict)

    # Cache question in DB
    if app_state.db_engine:
        try:
            async with app_state.db_session_factory() as db:
                await crud.store_question(
                    db,
                    question_id   = q.id,
                    question_text = q.text,
                    correct_answer= q.correctAnswer,
                    options       = q.options,
                    explanation   = q.explanation,
                    topic         = body.topic,
                    difficulty    = effective_difficulty,
                    source        = question_dict.get("source", "llm_direct") if question_dict else "fallback",
                )
        except Exception as e:
            logger.warning(f"Could not cache question in DB: {e}")

    # Mark as seen (both id and text)
    await session_svc.add_seen_id(body.session_id, q.id)
    await session_svc.increment_question_count(body.session_id)

    # Store seen text in session for LLM dedup
    seen_texts.append(q.text[:60])
    await session_svc.update_session(body.session_id, {"seen_texts": seen_texts[-10:]})

    logger.info("question_generated", question_id=q.id,
                source=question_dict.get("source", "fallback") if question_dict else "fallback")
    return q


@app.post("/api/classic/generate-hint", response_model=HintOut)
@limiter.limit("20/minute")
async def generate_hint(
    request: Request,
    body: Annotated[GenerateHintRequest, Body()],
    llm: LLMClient = Depends(get_llm),
):
    logger.info("generate_hint", question=body.questionText[:60])

    hint = await llm.generate_hint(
        question_text=body.questionText,
        correct_answer=body.correctAnswer,
    )

    if not hint:
        hint = "Consider the broader historical and geographical context of this topic."

    return HintOut(hint=hint)


@app.post("/api/classic/submit-answer", response_model=SubmitAnswerOut)
@limiter.limit("60/minute")
async def submit_answer(
    request: Request,
    body: Annotated[SubmitAnswerRequest, Body()],
    session_svc: SessionService = Depends(get_session_service),
):
    logger.info("submit_answer", user_id=body.user_id, session_id=body.session_id,
                question_id=body.question_id, selected=body.selected_answer)

    session_data = await session_svc.get_session(body.session_id) or {}
    current_difficulty = session_data.get("current_difficulty", 2)
    theta = session_data.get("theta", 0.0)

    answered_correct = False
    if app_state.db_engine:
        try:
            async with app_state.db_session_factory() as db:
                from sqlalchemy import select
                from database.models import QuestionBank
                import uuid as _uuid
                stmt = select(QuestionBank.correct_answer).where(
                    QuestionBank.id == _uuid.UUID(body.question_id)
                )
                result = await db.execute(stmt)
                row = result.scalar_one_or_none()
                if row:
                    answered_correct = (body.selected_answer.strip() == row.strip())
        except Exception as e:
            logger.warning(f"Could not look up correct answer: {e}")

    beta = difficulty_to_beta(current_difficulty)
    new_theta = update_theta(theta, beta, answered_correct)

    if answered_correct:
        new_difficulty = min(current_difficulty + 1, 5)
    else:
        new_difficulty = max(current_difficulty - 1, 1)

    await session_svc.update_session(body.session_id, {
        "current_difficulty": new_difficulty,
        "theta": new_theta,
    })

    if app_state.db_engine:
        try:
            async with app_state.db_session_factory() as db:
                await crud.create_user_response(
                    db,
                    user_id          = body.user_id,
                    session_id       = body.session_id,
                    question_id      = body.question_id,
                    topic            = session_data.get("topic", "Mixed"),
                    difficulty_sent  = current_difficulty,
                    answered_correct = answered_correct,
                    time_taken       = body.time_taken,
                    used_hint        = body.used_hint,
                )
                await crud.recalibrate_question_irt(
                    db, question_id=body.question_id,
                    theta=new_theta, answered_correct=answered_correct,
                )
        except Exception as e:
            logger.warning(f"DB write failed (non-fatal): {e}")

    logger.info("answer_processed", correct=answered_correct,
                old_difficulty=current_difficulty, new_difficulty=new_difficulty,
                theta=round(new_theta, 3))

    return SubmitAnswerOut(success=True, updated_difficulty=new_difficulty)


# ═══════════════════════════════════════════════════════════════════════
# IRT RECALIBRATION CRON
# ═══════════════════════════════════════════════════════════════════════
async def irt_recalibration_job():
    if not app_state.db_engine:
        return
    logger.info("IRT recalibration job starting")
    from database.irt import estimate_theta_from_history
    try:
        async with app_state.db_session_factory() as db:
            from sqlalchemy import select, distinct
            from database.models import UserResponse
            stmt = select(distinct(UserResponse.user_id)).limit(100)
            result = await db.execute(stmt)
            user_ids = [str(uid) for uid in result.scalars().all()]
            for uid in user_ids:
                responses = await crud.get_user_recent_responses(db, uid, limit=50)
                if responses:
                    theta = estimate_theta_from_history(responses)
                    logger.debug(f"User {uid[:8]} θ = {theta:.3f}")
    except Exception as e:
        logger.error(f"IRT recalibration failed: {e}")


@app.on_event("startup")
async def schedule_irt_cron():
    async def _cron():
        while True:
            await asyncio.sleep(1800)
            await irt_recalibration_job()
    asyncio.create_task(_cron())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000,
                reload=(ENVIRONMENT == "development"), log_level=LOG_LEVEL.lower())