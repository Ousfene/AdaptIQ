"""
routers/admin.py — Admin dashboard API endpoints.

By default, endpoints require admin privileges (user.is_admin = True).
In local development only, read-only GET endpoints can be accessed from
localhost without a token so the local static admin dashboard can load data.

Covers:
  - GET  /api/admin/overview       → System-wide statistics
  - GET  /api/admin/top-concepts   → Most-tracked concepts
  - GET  /api/admin/users          → Paginated user list
  - GET  /api/admin/users/{id}     → User detail with sessions & mastery
  - PATCH /api/admin/users/{id}    → Toggle user active/admin status
  - GET  /api/admin/questions      → Paginated question list
  - GET  /api/admin/sessions       → All session types combined
  - GET  /api/admin/monitoring     → Request stats and error log

Internal helpers:
    - _as_iso: safe datetime serializer
    - _require_admin: strict admin guard
    - _is_local_read_only_request: localhost-only read bypass in dev
    - get_admin_read_access: dependency that combines admin token and local read rules
"""

import logging
import uuid
from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import MetaData, Table, func, inspect as sa_inspect, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.challenge_models import ChallengeSession
from database.concept_models import ClassicSession, Concept, UserConceptTheta, QuestionConcept, UserConceptRepeatQueue
from database.custom_models import CustomSession
from database.models import QuestionBank, User, UserResponse
from config import ENVIRONMENT
from routers.auth import get_current_user, get_db
from services.monitoring import get_monitoring

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/api/admin", tags=["Admin"])

_LOCALHOST_CLIENTS = {"127.0.0.1", "::1", "localhost"}
_LOCAL_ADMIN_ORIGINS = (
    "http://localhost:9000",
    "http://127.0.0.1:9000",
)


# Serialize datetimes consistently for JSON payloads.
def _as_iso(dt: Optional[datetime]) -> Optional[str]:
    """Convert a datetime to ISO string, returning None if input is None."""
    return dt.isoformat() if dt else None


# Convert DB values to JSON-safe primitives for admin inspector payloads.
def _to_jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


# Enforce admin-only access for protected admin operations.
def _require_admin(current) -> User:
    """Extract user from current tuple and verify admin privileges.

    Args:
        current: (User, issued_at) tuple from get_current_user

    Returns:
        User object if admin

    Raises:
        HTTPException 403 if not admin
    """
    user, _issued_at = current
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# Detect trusted local read-only dashboard access in non-production.
def _is_local_read_only_request(request: Request) -> bool:
    """Allow localhost read-only admin dashboard access in non-production."""
    if ENVIRONMENT.lower() == "production":
        return False

    client_host = ((request.client.host if request.client else "") or "").lower()
    if client_host not in _LOCALHOST_CLIENTS:
        return False

    origin = (request.headers.get("origin") or "").lower()
    referer = (request.headers.get("referer") or "").lower()
    if not origin and not referer:
        return True

    return any(
        origin.startswith(prefix) or referer.startswith(prefix)
        for prefix in _LOCAL_ADMIN_ORIGINS
    )


# Authorize admin reads via token or localhost dev-only bypass.
async def get_admin_read_access(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Authorize read access for admin token or trusted localhost dashboard."""
    if authorization:
        current = await get_current_user(request=request, authorization=authorization, db=db)
        _require_admin(current)
        return current

    if _is_local_read_only_request(request):
        return None

    raise HTTPException(status_code=401, detail="Missing bearer token")


# ═══════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════


@admin_router.get("/overview")
# Aggregate top-level admin dashboard counters and health stats.
async def admin_overview(
    current=Depends(get_admin_read_access),
    db: AsyncSession = Depends(get_db),
):
    """System-wide dashboard statistics.

    Returns counts of users, questions, sessions, concepts, and responses.
    """
    if current is not None:
        _require_admin(current)

    total_users = await db.scalar(select(func.count()).select_from(User)) or 0
    active_users = await db.scalar(
        select(func.count()).select_from(User).where(User.is_active == True)
    ) or 0
    admin_users = await db.scalar(
        select(func.count()).select_from(User).where(User.is_admin == True)
    ) or 0

    total_questions = await db.scalar(select(func.count()).select_from(QuestionBank)) or 0
    llm_questions = await db.scalar(
        select(func.count()).select_from(QuestionBank).where(QuestionBank.source == "llm")
    ) or 0
    cached_questions = await db.scalar(
        select(func.count()).select_from(QuestionBank).where(QuestionBank.times_seen > 0)
    ) or 0

    total_responses = await db.scalar(select(func.count()).select_from(UserResponse)) or 0
    classic_sessions = await db.scalar(select(func.count()).select_from(ClassicSession)) or 0
    challenge_sessions = await db.scalar(select(func.count()).select_from(ChallengeSession)) or 0
    custom_sessions = await db.scalar(select(func.count()).select_from(CustomSession)) or 0
    total_concepts = await db.scalar(select(func.count()).select_from(Concept)) or 0
    concept_mastery_rows = await db.scalar(select(func.count()).select_from(UserConceptTheta)) or 0

    latest_user_created = await db.scalar(select(func.max(User.created_at)))
    latest_question_created = await db.scalar(select(func.max(QuestionBank.created_at)))

    # PvP stats (optional — table may not exist yet)
    pvp_matches = 0
    pvp_players = 0
    try:
        from database.pvp_models import PvPMatch, PvPRating
        pvp_matches = await db.scalar(select(func.count()).select_from(PvPMatch)) or 0
        pvp_players = await db.scalar(select(func.count()).select_from(PvPRating)) or 0
    except Exception as exc:
        logger.warning("PvP stats unavailable for admin overview: %s", exc)

    return {
        "users": {
            "total": int(total_users),
            "active": int(active_users),
            "admin": int(admin_users),
            "latest_created_at": _as_iso(latest_user_created),
        },
        "questions": {
            "total": int(total_questions),
            "llm_generated": int(llm_questions),
            "cached": int(cached_questions),
            "latest_created_at": _as_iso(latest_question_created),
        },
        "sessions": {
            "classic": int(classic_sessions),
            "challenge": int(challenge_sessions),
            "custom": int(custom_sessions),
            "pvp": int(pvp_matches),
        },
        "concepts": {
            "total": int(total_concepts),
            "mastery_rows": int(concept_mastery_rows),
        },
        "responses": {
            "total": int(total_responses),
        },
        "pvp": {
            "total_matches": int(pvp_matches),
            "rated_players": int(pvp_players),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# TOP CONCEPTS
# ═══════════════════════════════════════════════════════════════════════════


@admin_router.get("/top-concepts")
# Return concepts ordered by tracking volume and average mastery.
async def admin_top_concepts(
    limit: int = Query(default=10, ge=1, le=50),
    current=Depends(get_admin_read_access),
    db: AsyncSession = Depends(get_db),
):
    """Most-tracked concepts by user engagement count.

    Returns concepts ranked by number of users who have interacted with them.
    """
    if current is not None:
        _require_admin(current)

    rows = await db.execute(
        select(
            Concept.id,
            Concept.name,
            Concept.topic,
            func.count(UserConceptTheta.id).label("tracked_users"),
            func.avg(UserConceptTheta.theta).label("avg_theta"),
        )
        .outerjoin(UserConceptTheta, UserConceptTheta.concept_id == Concept.id)
        .group_by(Concept.id, Concept.name, Concept.topic)
        .order_by(func.count(UserConceptTheta.id).desc(), Concept.name.asc())
        .limit(limit)
    )

    items = []
    for concept_id, name, topic, tracked_users, avg_theta in rows.all():
        items.append({
            "concept_id": str(concept_id),
            "name": name,
            "topic": topic,
            "tracked_users": int(tracked_users or 0),
            "avg_theta": round(float(avg_theta or 0.0), 3),
        })

    return {"items": items}

# ═════════════════════════════════════════════════════════════════════════════
# CONCEPTS (FULL TABLE)
# ═══════════════════════════════════════════════════════════════════════════


@admin_router.get("/concepts")
# Return paginated concept catalog with aggregate usage metadata.
async def admin_list_concepts(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    topic: Optional[str] = Query(default=None),
    sort_by: str = Query(default="tracked_users"),
    current=Depends(get_admin_read_access),
    db: AsyncSession = Depends(get_db),
):
    """Paginated list of all concepts with comprehensive stats."""
    if current is not None:
        _require_admin(current)

    base_query = select(Concept)
    count_query = select(func.count()).select_from(Concept)

    if topic:
        topic_filter = Concept.topic.ilike(f"%{topic}%")
        base_query = base_query.where(topic_filter)
        count_query = count_query.where(topic_filter)

    result = await db.execute(count_query)
    total = result.scalar() or 0

    result = await db.execute(
        base_query.order_by(Concept.name.asc()).offset((page - 1) * per_page).limit(per_page)
    )
    concepts = result.scalars().all()

    concept_ids = [c.id for c in concepts]
    tracked_map: dict[str, tuple[int, float]] = {}
    tagged_map: dict[str, int] = {}
    mastery_map: dict[str, dict[str, int]] = {}

    if concept_ids:
        tracked_rows = await db.execute(
            select(
                UserConceptTheta.concept_id,
                func.count(UserConceptTheta.id).label("tracked_users"),
                func.avg(UserConceptTheta.theta).label("avg_theta"),
            )
            .where(UserConceptTheta.concept_id.in_(concept_ids))
            .group_by(UserConceptTheta.concept_id)
        )
        tracked_map = {
            str(row[0]): (int(row[1] or 0), float(row[2] or 0.0))
            for row in tracked_rows.all()
        }

        tagged_rows = await db.execute(
            select(
                QuestionConcept.concept_id,
                func.count(QuestionConcept.id).label("questions_tagged"),
            )
            .where(QuestionConcept.concept_id.in_(concept_ids))
            .group_by(QuestionConcept.concept_id)
        )
        tagged_map = {
            str(row[0]): int(row[1] or 0)
            for row in tagged_rows.all()
        }

        mastery_rows = await db.execute(
            select(
                UserConceptTheta.concept_id,
                UserConceptTheta.mastery_level,
                func.count(UserConceptTheta.id).label("count"),
            )
            .where(UserConceptTheta.concept_id.in_(concept_ids))
            .group_by(UserConceptTheta.concept_id, UserConceptTheta.mastery_level)
        )
        for concept_id, mastery_level, count in mastery_rows.all():
            cid = str(concept_id)
            bucket = mastery_map.setdefault(cid, {})
            bucket[str(mastery_level)] = int(count or 0)

    items = []
    for concept in concepts:
        cid = str(concept.id)
        tracked_users, avg_theta = tracked_map.get(cid, (0, 0.0))
        items.append({
            "concept_id": cid,
            "name": concept.name,
            "topic": concept.topic,
            "description": concept.description or "",
            "tracked_users": tracked_users,
            "avg_theta": round(float(avg_theta), 3),
            "questions_tagged": tagged_map.get(cid, 0),
            "mastery_distribution": mastery_map.get(cid, {}),
            "created_at": _as_iso(concept.created_at),
        })

    sort_key = (sort_by or "tracked_users").strip().lower()
    if sort_key == "name":
        items.sort(key=lambda item: str(item.get("name") or "").lower())
    elif sort_key == "topic":
        items.sort(key=lambda item: str(item.get("topic") or "").lower())
    elif sort_key == "avg_theta":
        items.sort(key=lambda item: float(item.get("avg_theta") or 0.0), reverse=True)
    elif sort_key == "questions_tagged":
        items.sort(key=lambda item: int(item.get("questions_tagged") or 0), reverse=True)
    else:
        items.sort(key=lambda item: int(item.get("tracked_users") or 0), reverse=True)

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@admin_router.get("/concepts/{concept_id}")
# Return one concept with mastery, question, and repeat-queue details.
async def admin_concept_detail(
    concept_id: str,
    current=Depends(get_admin_read_access),
    db: AsyncSession = Depends(get_db),
):
    """Detailed view of a single concept with all tracking data.

    Returns concept info, user mastery breakdown, tagged questions, repeat queue stats.
    """
    if current is not None:
        _require_admin(current)

    import uuid
    try:
        cid = uuid.UUID(concept_id)
    except ValueError:
        raise HTTPException(422, "Invalid concept ID")

    concept = await db.get(Concept, cid)
    if not concept:
        raise HTTPException(404, "Concept not found")

    # User mastery breakdown
    mastery_rows = await db.execute(
        select(
            UserConceptTheta.mastery_level,
            func.count(UserConceptTheta.id).label("count"),
            func.avg(UserConceptTheta.theta).label("avg_theta"),
            func.avg(UserConceptTheta.response_count).label("avg_responses"),
        )
        .where(UserConceptTheta.concept_id == cid)
        .group_by(UserConceptTheta.mastery_level)
        .order_by(UserConceptTheta.mastery_level.desc())
    )
    mastery_breakdown = [
        {
            "mastery_level": row[0],
            "user_count": int(row[1]),
            "avg_theta": round(float(row[2] or 0.0), 3),
            "avg_responses": int(row[3] or 0),
        }
        for row in mastery_rows.all()
    ]

    # Tagged questions sample
    question_rows = await db.execute(
        select(QuestionBank, QuestionConcept.is_primary)
        .join(QuestionConcept, QuestionBank.id == QuestionConcept.question_id)
        .where(QuestionConcept.concept_id == cid)
        .order_by(QuestionBank.created_at.desc())
        .limit(10)
    )
    questions = [
        {
            "question_id": str(q[0].id),
            "text": q[0].question_text[:100],
            "difficulty": round(float(q[0].difficulty_irt or 0.0), 2),
            "is_primary": bool(q[1]),
            "times_seen": q[0].times_seen or 0,
        }
        for q in question_rows.all()
    ]

    # Repeat queue stats
    repeat_count = await db.scalar(
        select(func.count()).select_from(UserConceptRepeatQueue)
        .where(UserConceptRepeatQueue.concept_id == cid)
    ) or 0

    repeat_users = await db.scalar(
        select(func.count(UserConceptRepeatQueue.user_id.distinct()))
        .select_from(UserConceptRepeatQueue)
        .where(UserConceptRepeatQueue.concept_id == cid)
    ) or 0

    # Stats
    tracked_users = await db.scalar(
        select(func.count()).select_from(UserConceptTheta)
        .where(UserConceptTheta.concept_id == cid)
    ) or 0

    questions_tagged = await db.scalar(
        select(func.count()).select_from(QuestionConcept)
        .where(QuestionConcept.concept_id == cid)
    ) or 0

    return {
        "concept": {
            "id": str(concept.id),
            "name": concept.name,
            "topic": concept.topic,
            "description": concept.description or "",
            "created_at": _as_iso(concept.created_at),
        },
        "stats": {
            "tracked_users": int(tracked_users),
            "questions_tagged": int(questions_tagged),
            "repeat_queue_count": int(repeat_count),
            "users_with_repeats": int(repeat_users),
        },
        "mastery_breakdown": mastery_breakdown,
        "sample_questions": questions,
    }


# ═══════════════════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════════════════


@admin_router.get("/users")
# Return paginated users for admin browsing.
async def admin_list_users(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None),
    current=Depends(get_admin_read_access),
    db: AsyncSession = Depends(get_db),
):
    """Paginated list of all users with search by email/username.

    Returns:
        {items: [...], total: int, page: int, per_page: int}
    """
    if current is not None:
        _require_admin(current)

    query = select(User)
    count_query = select(func.count()).select_from(User)

    if search:
        search_filter = (User.email.ilike(f"%{search}%")) | (User.username.ilike(f"%{search}%"))
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = await db.scalar(count_query) or 0
    offset = (page - 1) * per_page

    result = await db.execute(
        query.order_by(User.created_at.desc()).offset(offset).limit(per_page)
    )
    users = result.scalars().all()

    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "username": u.username,
                "points": u.points or 0,
                "level": u.level or "Novice",
                "is_active": bool(u.is_active),
                "is_admin": bool(getattr(u, "is_admin", False)),
                "created_at": _as_iso(u.created_at),
                "last_login": _as_iso(getattr(u, "last_login", None)),
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@admin_router.get("/users/{user_id}")
# Return one user profile with related learning/session detail.
async def admin_user_detail(
    user_id: str,
    current=Depends(get_admin_read_access),
    db: AsyncSession = Depends(get_db),
):
    """Detailed user profile with sessions and concept mastery.

    Returns user info, their recent sessions, and concept tracking data.
    """
    if current is not None:
        _require_admin(current)

    import uuid
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(422, "Invalid user ID")

    user = await db.get(User, uid)
    if not user:
        raise HTTPException(404, "User not found")

    # Get concept mastery
    mastery_rows = await db.execute(
        select(UserConceptTheta, Concept)
        .join(Concept, UserConceptTheta.concept_id == Concept.id)
        .where(UserConceptTheta.user_id == uid)
        .order_by(UserConceptTheta.theta.desc())
        .limit(20)
    )
    concepts = [
        {
            "concept": c.name,
            "topic": c.topic,
            "theta": round(float(t.theta), 3),
            "responses": t.response_count,
            "mastery": t.mastery_level,
        }
        for t, c in mastery_rows.all()
    ]

    # Get recent responses
    response_count = await db.scalar(
        select(func.count()).select_from(UserResponse).where(UserResponse.user_id == uid)
    ) or 0

    correct_count = await db.scalar(
        select(func.count()).select_from(UserResponse).where(
            UserResponse.user_id == uid,
            UserResponse.answered_correct == True,
        )
    ) or 0

    # Get challenge sessions
    challenge_count = await db.scalar(
        select(func.count()).select_from(ChallengeSession).where(ChallengeSession.user_id == uid)
    ) or 0

    # Get custom sessions
    custom_count = await db.scalar(
        select(func.count()).select_from(CustomSession).where(CustomSession.user_id == uid)
    ) or 0

    # Get classic sessions
    classic_count = await db.scalar(
        select(func.count()).select_from(ClassicSession).where(ClassicSession.user_id == uid)
    ) or 0

    # Usage by question source (llm/challenge_llm/custom_llm/etc.)
    source_usage_rows = await db.execute(
        select(
            QuestionBank.source,
            func.count(UserResponse.id).label("count"),
        )
        .select_from(UserResponse)
        .outerjoin(QuestionBank, QuestionBank.id == UserResponse.question_id)
        .where(UserResponse.user_id == uid)
        .group_by(QuestionBank.source)
        .order_by(func.count(UserResponse.id).desc())
        .limit(20)
    )
    source_usage = [
        {
            "source": source or "unknown",
            "count": int(count or 0),
        }
        for source, count in source_usage_rows.all()
    ]

    # Usage by topic from submitted responses.
    topic_usage_rows = await db.execute(
        select(
            UserResponse.topic,
            func.count(UserResponse.id).label("count"),
        )
        .where(UserResponse.user_id == uid)
        .group_by(UserResponse.topic)
        .order_by(func.count(UserResponse.id).desc())
        .limit(20)
    )
    topic_usage = [
        {
            "topic": topic or "unknown",
            "count": int(count or 0),
        }
        for topic, count in topic_usage_rows.all()
    ]

    # Recent question usage feed with question metadata when available.
    recent_usage_rows = await db.execute(
        select(
            UserResponse.id,
            UserResponse.question_id,
            UserResponse.topic,
            UserResponse.difficulty_sent,
            UserResponse.answered_correct,
            UserResponse.used_hint,
            UserResponse.time_taken,
            UserResponse.created_at,
            QuestionBank.question_text,
            QuestionBank.source,
        )
        .select_from(UserResponse)
        .outerjoin(QuestionBank, QuestionBank.id == UserResponse.question_id)
        .where(UserResponse.user_id == uid)
        .order_by(UserResponse.created_at.desc())
        .limit(50)
    )
    recent_usage = [
        {
            "response_id": str(response_id),
            "question_id": str(question_id),
            "topic": topic,
            "difficulty_sent": int(difficulty_sent or 0),
            "answered_correct": bool(answered_correct),
            "used_hint": bool(used_hint),
            "time_taken": int(time_taken or 0),
            "answered_at": _as_iso(created_at),
            "question_text": question_text or "",
            "source": source or "unknown",
        }
        for (
            response_id,
            question_id,
            topic,
            difficulty_sent,
            answered_correct,
            used_hint,
            time_taken,
            created_at,
            question_text,
            source,
        ) in recent_usage_rows.all()
    ]

    # Recent sessions across room types.
    recent_sessions: list[dict] = []

    classic_rows = await db.execute(
        select(ClassicSession)
        .where(ClassicSession.user_id == uid)
        .order_by(ClassicSession.created_at.desc())
        .limit(10)
    )
    for row in classic_rows.scalars().all():
        started_at = row.created_at
        recent_sessions.append(
            {
                "type": "classic",
                "session_id": str(row.id),
                "topic": row.topic,
                "questions": int(row.questions_answered or 0),
                "correct": int(row.correct_count or 0),
                "started_at": _as_iso(started_at),
                "is_completed": row.ended_at is not None,
                "_sort": started_at,
            }
        )

    challenge_rows = await db.execute(
        select(ChallengeSession)
        .where(ChallengeSession.user_id == uid)
        .order_by(ChallengeSession.started_at.desc())
        .limit(10)
    )
    for row in challenge_rows.scalars().all():
        started_at = row.started_at
        recent_sessions.append(
            {
                "type": "challenge",
                "session_id": str(row.id),
                "topic": row.topic,
                "questions": int(row.total_questions or 0),
                "correct": int(row.correct_answers or 0),
                "started_at": _as_iso(started_at),
                "is_completed": bool(row.is_completed),
                "_sort": started_at,
            }
        )

    custom_rows = await db.execute(
        select(CustomSession)
        .where(CustomSession.user_id == uid)
        .order_by(CustomSession.started_at.desc())
        .limit(10)
    )
    for row in custom_rows.scalars().all():
        started_at = row.started_at
        recent_sessions.append(
            {
                "type": "custom",
                "session_id": str(row.id),
                "topic": row.topic,
                "questions": int(row.total_questions or 0),
                "correct": int(row.correct_count or 0),
                "started_at": _as_iso(started_at),
                "is_completed": row.ended_at is not None,
                "_sort": started_at,
            }
        )

    pvp_stats = {
        "enabled": False,
        "matches": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "elo_rating": None,
    }

    try:
        from database.pvp_models import PvPMatch, PvPRating

        pvp_stats["enabled"] = True

        pvp_rating = (
            await db.execute(select(PvPRating).where(PvPRating.user_id == uid))
        ).scalar_one_or_none()
        if pvp_rating is not None:
            pvp_stats["elo_rating"] = float(pvp_rating.elo_rating or 0.0)

        pvp_matches = (
            await db.execute(
                select(PvPMatch)
                .where(or_(PvPMatch.user1_id == uid, PvPMatch.user2_id == uid))
                .order_by(PvPMatch.started_at.desc())
                .limit(10)
            )
        ).scalars().all()

        wins = 0
        losses = 0
        draws = 0

        for row in pvp_matches:
            started_at = row.started_at
            my_score = int(row.user1_score or 0) if row.user1_id == uid else int(row.user2_score or 0)
            opp_score = int(row.user2_score or 0) if row.user1_id == uid else int(row.user1_score or 0)

            if row.winner_id is None:
                draws += 1
            elif row.winner_id == uid:
                wins += 1
            else:
                losses += 1

            recent_sessions.append(
                {
                    "type": "pvp",
                    "session_id": str(row.id),
                    "topic": row.topic,
                    "questions": int(row.total_questions or 0),
                    "correct": my_score,
                    "opponent_score": opp_score,
                    "started_at": _as_iso(started_at),
                    "is_completed": row.status == "completed",
                    "status": row.status,
                    "_sort": started_at,
                }
            )

        pvp_stats["matches"] = int(len(pvp_matches))
        pvp_stats["wins"] = int(wins)
        pvp_stats["losses"] = int(losses)
        pvp_stats["draws"] = int(draws)
    except Exception as exc:
        logger.warning("PvP user detail unavailable: %s", exc)

    recent_sessions.sort(
        key=lambda item: item.get("_sort") or datetime.min,
        reverse=True,
    )
    recent_sessions = [
        {k: v for k, v in item.items() if k != "_sort"}
        for item in recent_sessions[:20]
    ]

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "points": user.points or 0,
            "level": user.level or "Novice",
            "is_active": bool(user.is_active),
            "is_admin": bool(getattr(user, "is_admin", False)),
            "created_at": _as_iso(user.created_at),
            "last_login": _as_iso(getattr(user, "last_login", None)),
        },
        "stats": {
            "total_responses": int(response_count),
            "correct_responses": int(correct_count),
            "accuracy": round(correct_count / max(response_count, 1) * 100, 1),
            "classic_sessions": int(classic_count),
            "challenge_sessions": int(challenge_count),
            "custom_sessions": int(custom_count),
        },
        "concept_mastery": concepts,
        "activity": {
            "source_usage": source_usage,
            "topic_usage": topic_usage,
            "recent_usage": recent_usage,
        },
        "sessions": {
            "recent": recent_sessions,
        },
        "pvp": pvp_stats,
    }


@admin_router.patch("/users/{user_id}")
# Update mutable admin-controlled user flags.
async def admin_update_user(
    user_id: str,
    is_active: Optional[bool] = Query(default=None),
    is_admin: Optional[bool] = Query(default=None),
    current=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle user active/admin status.

    Query params:
        is_active: Set user active status (true/false)
        is_admin: Set user admin status (true/false)
    """
    _require_admin(current)

    import uuid
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(422, "Invalid user ID")

    user = await db.get(User, uid)
    if not user:
        raise HTTPException(404, "User not found")

    if is_active is not None:
        user.is_active = is_active
        logger.info("Admin toggled user %s active=%s", user_id[:8], is_active)

    if is_admin is not None:
        user.is_admin = is_admin
        logger.info("Admin toggled user %s admin=%s", user_id[:8], is_admin)

    await db.commit()
    return {"success": True, "user_id": user_id}


# ═══════════════════════════════════════════════════════════════════════════
# QUESTIONS
# ═══════════════════════════════════════════════════════════════════════════


@admin_router.get("/questions")
# Return paginated question inventory for diagnostics and governance review.
async def admin_list_questions(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    topic: Optional[str] = Query(default=None),
    current=Depends(get_admin_read_access),
    db: AsyncSession = Depends(get_db),
):
    """Paginated list of all questions with optional topic filter.

    Returns question text, topic, difficulty, and usage stats.
    """
    if current is not None:
        _require_admin(current)

    query = select(
        QuestionBank.id,
        QuestionBank.question_text,
        QuestionBank.correct_answer,
        QuestionBank.options_json,
        QuestionBank.explanation,
        QuestionBank.topic,
        QuestionBank.difficulty_irt,
        QuestionBank.source,
        QuestionBank.usage_count,
        QuestionBank.times_seen,
        QuestionBank.last_served_at,
        QuestionBank.created_at,
        QuestionBank.gov_approved,
        QuestionBank.gov_safe,
        QuestionBank.gov_flags_json,
    )
    count_query = select(func.count()).select_from(QuestionBank)

    if topic:
        query = query.where(QuestionBank.topic.ilike(f"%{topic}%"))
        count_query = count_query.where(QuestionBank.topic.ilike(f"%{topic}%"))

    total = await db.scalar(count_query) or 0
    offset = (page - 1) * per_page

    result = await db.execute(
        query.order_by(QuestionBank.created_at.desc()).offset(offset).limit(per_page)
    )
    questions = result.all()

    return {
        "items": [
            {
                "id": str(row[0]),
                "question_text": row[1],
                "text": (row[1] or "")[:100],
                "correct_answer": row[2],
                "options_json": row[3],
                "explanation": row[4],
                "topic": row[5],
                "difficulty_irt": round(float(row[6] or 0.0), 2),
                "source": row[7],
                "usage_count": int(row[8] or 0),
                "times_seen": int(row[9] or 0),
                "last_served_at": _as_iso(row[10]),
                "created_at": _as_iso(row[11]),
                "gov_approved": bool(row[12]) if row[12] is not None else None,
                "gov_safe": bool(row[13]) if row[13] is not None else None,
                "gov_flags_json": row[14],
            }
            for row in questions
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SESSIONS
# ═══════════════════════════════════════════════════════════════════════════


@admin_router.get("/sessions")
# Return cross-room session activity feed with optional filters.
async def admin_list_sessions(
    session_type: Optional[str] = Query(default=None, description="classic, challenge, custom, or pvp"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current=Depends(get_admin_read_access),
    db: AsyncSession = Depends(get_db),
):
    """Combined session list across all room types.

    Filter by session_type (challenge, custom, pvp) or get all.
    """
    if current is not None:
        _require_admin(current)

    normalized_session_type = session_type.lower().strip() if session_type else None
    if normalized_session_type not in (None, "classic", "challenge", "custom", "pvp"):
        raise HTTPException(422, "session_type must be one of: classic, challenge, custom, pvp")

    items = []
    offset = (page - 1) * per_page

    if normalized_session_type in (None, "classic"):
        result = await db.execute(
            select(ClassicSession)
            .order_by(ClassicSession.created_at.desc())
        )
        for s in result.scalars().all():
            items.append({
                "type": "classic",
                "id": str(s.id),
                "user_id": str(s.user_id),
                "topic": s.topic,
                "questions": int(s.questions_answered or 0),
                "correct": int(s.correct_count or 0),
                "started_at": _as_iso(s.created_at),
                "is_completed": s.ended_at is not None,
            })

    if normalized_session_type in (None, "challenge"):
        result = await db.execute(
            select(ChallengeSession)
            .order_by(ChallengeSession.started_at.desc())
        )
        for s in result.scalars().all():
            items.append({
                "type": "challenge",
                "id": str(s.id),
                "user_id": str(s.user_id),
                "topic": s.topic,
                "questions": s.total_questions,
                "correct": s.correct_answers,
                "started_at": _as_iso(s.started_at),
                "is_completed": s.is_completed,
            })

    if normalized_session_type in (None, "custom"):
        result = await db.execute(
            select(CustomSession)
            .order_by(CustomSession.started_at.desc())
        )
        for s in result.scalars().all():
            items.append({
                "type": "custom",
                "id": str(s.id),
                "user_id": str(s.user_id),
                "topic": s.topic,
                "questions": s.total_questions,
                "correct": s.correct_count,
                "started_at": _as_iso(s.started_at),
                "is_completed": s.ended_at is not None,
            })

    if normalized_session_type in (None, "pvp"):
        try:
            from database.pvp_models import PvPMatch

            result = await db.execute(
                select(PvPMatch)
                .order_by(PvPMatch.started_at.desc())
            )
            for s in result.scalars().all():
                items.append({
                    "type": "pvp",
                    "id": str(s.id),
                    "user_id": str(s.user1_id),
                    "topic": s.topic,
                    "questions": s.total_questions,
                    "correct": max(int(s.user1_score or 0), int(s.user2_score or 0)),
                    "started_at": _as_iso(s.started_at),
                    "is_completed": s.status == "completed",
                    "user1_id": str(s.user1_id),
                    "user2_id": str(s.user2_id),
                    "user1_score": int(s.user1_score or 0),
                    "user2_score": int(s.user2_score or 0),
                    "winner_id": str(s.winner_id) if s.winner_id else None,
                    "status": s.status,
                })
        except Exception as exc:
            logger.warning("PvP sessions unavailable for admin sessions list: %s", exc)

    items.sort(key=lambda item: item.get("started_at") or "", reverse=True)
    total = len(items)
    paged_items = items[offset:offset + per_page]

    return {
        "items": paged_items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# ═══════════════════════════════════════════════════════════════════════════
# DB INSPECTOR
# ═══════════════════════════════════════════════════════════════════════════


@admin_router.get("/db/schema")
# Return read-only database schema and table counts for admin inspection.
async def admin_db_schema(
    current=Depends(get_admin_read_access),
    db: AsyncSession = Depends(get_db),
):
    if current is not None:
        _require_admin(current)

    async with db.bind.connect() as conn:
        tables = await conn.run_sync(_collect_db_schema)

    return {
        "tables": tables,
        "total_tables": len(tables),
    }


def _collect_db_schema(sync_conn):
    inspector = sa_inspect(sync_conn)
    metadata = MetaData()
    tables = []

    for table_name in sorted(inspector.get_table_names()):
        columns_info = inspector.get_columns(table_name)
        primary_keys = set(inspector.get_pk_constraint(table_name).get("constrained_columns") or [])
        reflected = Table(table_name, metadata, autoload_with=sync_conn)
        total_rows = sync_conn.execute(select(func.count()).select_from(reflected)).scalar() or 0

        tables.append(
            {
                "name": table_name,
                "row_count": int(total_rows),
                "columns": [
                    {
                        "name": str(col.get("name") or ""),
                        "type": str(col.get("type") or ""),
                        "nullable": bool(col.get("nullable", True)),
                        "primary_key": str(col.get("name") or "") in primary_keys,
                    }
                    for col in columns_info
                ],
            }
        )

    return tables


@admin_router.get("/db/table/{table_name}")
# Return paginated table rows and typed column metadata for one table.
async def admin_db_table_rows(
    table_name: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current=Depends(get_admin_read_access),
    db: AsyncSession = Depends(get_db),
):
    if current is not None:
        _require_admin(current)

    async with db.bind.connect() as conn:
        schema = await conn.run_sync(_collect_db_schema)

    table_map = {item["name"]: item for item in schema}
    selected = table_map.get(table_name)
    if selected is None:
        raise HTTPException(404, "Table not found")

    quoted = table_name.replace('"', '""')
    query = text(f'SELECT * FROM "{quoted}" LIMIT :limit OFFSET :offset')
    rows_result = await db.execute(query, {"limit": int(limit), "offset": int(offset)})
    rows = [
        {key: _to_jsonable(value) for key, value in row.items()}
        for row in rows_result.mappings().all()
    ]

    total_result = await db.execute(text(f'SELECT COUNT(*) AS total FROM "{quoted}"'))
    total = int(total_result.scalar() or 0)

    return {
        "table": table_name,
        "columns": selected["columns"],
        "rows": rows,
        "total": total,
        "limit": int(limit),
        "offset": int(offset),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════════════════════════════════════


@admin_router.get("/monitoring")
# Return operational monitoring snapshot for the admin dashboard.
async def admin_monitoring(current=Depends(get_admin_read_access)):
    """Get system monitoring stats — request counts, errors, rate limits.

    Uses the in-memory Monitoring singleton from services/monitoring.py.
    """
    if current is not None:
        _require_admin(current)
    monitoring = get_monitoring()
    return monitoring.get_stats()
