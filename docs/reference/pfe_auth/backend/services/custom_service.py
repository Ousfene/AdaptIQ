"""
services/custom_service.py — Custom Room business logic.

Handles:
- Topic/fact discovery
- Intelligent fact picking (prefer unmastered facts)
- Mastery percentage updates
- Question generation from facts
- Session management
"""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, func, and_, not_
from sqlalchemy.ext.asyncio import AsyncSession

from config import CUSTOM_ROOM_FACTS_PER_TOPIC, CUSTOM_ROOM_SESSION_TTL, CUSTOM_ROOM_TOPICS, GROQ_API_KEY
from database.models import (
    User,
    Fact,
    UserTopicMastery,
    CustomSession,
    QuestionFact,
    QuestionBank,
    UserResponse,
)
from services.llm import LLMClient
from services.session import SessionService

logger = logging.getLogger(__name__)


def utc_now_naive() -> datetime:
    """Return current UTC time without timezone info."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CustomService:
    """Service layer for Custom Room features."""

    def __init__(self, db: AsyncSession, redis=None, llm_service: LLMClient = None):
        self.db = db
        self.session_service = SessionService(redis)
        self.llm_service = llm_service or LLMClient(api_key=GROQ_API_KEY)

    async def get_or_create_mastery(
        self,
        user_id: UUID,
        topic: str,
    ) -> UserTopicMastery:
        """
        Get existing UserTopicMastery record or create new one.

        Args:
            user_id: User's ID
            topic: Topic string (e.g., "History - World War II")

        Returns:
            UserTopicMastery record
        """
        # Query for existing record
        mastery = (
            await self.db.execute(
                select(UserTopicMastery).where(
                    (UserTopicMastery.user_id == user_id)
                    & (UserTopicMastery.topic == topic)
                )
            )
        ).scalar_one_or_none()

        if mastery:
            return mastery

        # Create new record
        total_facts = await self._count_facts_in_topic(topic)

        mastery = UserTopicMastery(
            user_id=user_id,
            topic=topic,
            mastered_facts_count=0,
            total_facts_count=total_facts,
            completion_percentage=0.0,
            created_at=utc_now_naive(),
        )
        self.db.add(mastery)
        await self.db.commit()
        await self.db.refresh(mastery)

        return mastery

    async def pick_fact_for_user(
        self,
        user_id: UUID,
        topic: str,
    ) -> Fact | None:
        """
        Intelligently pick a fact for the user.

        Strategy:
        1. Find facts the user has already mastered (answered correctly)
        2. If unmastered facts exist: pick random unmastered fact
        3. Else: pick random mastered fact (for review)

        Args:
            user_id: User's ID
            topic: Topic string

        Returns:
            Fact record or None if no facts available
        """
        # Get facts user has answered correctly
        mastered_fact_ids = set(
            (
                await self.db.execute(
                    select(Fact.id)
                    .join(QuestionFact, QuestionFact.fact_id == Fact.id)
                    .join(
                        UserResponse,
                        and_(
                            UserResponse.question_id == QuestionFact.question_id,
                            UserResponse.user_id == user_id,
                        ),
                    )
                    .where((Fact.topic == topic) & (UserResponse.answered_correct == True))
                    .distinct()
                )
            ).scalars().all()
        )

        # Try to pick unmastered fact
        unmastered = (
            await self.db.execute(
                select(Fact)
                .where((Fact.topic == topic) & (~Fact.id.in_(mastered_fact_ids)))
                .order_by(func.random())
                .limit(1)
            )
        ).scalar_one_or_none()

        if unmastered:
            return unmastered

        # All mastered; pick random for review
        return (
            await self.db.execute(
                select(Fact).where(Fact.topic == topic).order_by(func.random()).limit(1)
            )
        ).scalar_one_or_none()

    async def _count_facts_in_topic(self, topic: str) -> int:
        """Count total facts in a topic."""
        count = await self.db.scalar(
            select(func.count(Fact.id)).where(Fact.topic == topic)
        )
        return count or 0

    async def update_topic_mastery(
        self,
        user_id: UUID,
        topic: str,
        fact_id: UUID,
        is_correct: bool,
    ) -> UserTopicMastery:
        """
        Update user's mastery after answering a question.

        If user answered a question about a previously unmastered fact correctly,
        increment mastered_facts_count and recalculate completion percentage.

        Args:
            user_id: User's ID
            topic: Topic string
            fact_id: The fact that was just tested
            is_correct: Whether answer was correct

        Returns:
            Updated UserTopicMastery record
        """
        mastery = await self.get_or_create_mastery(user_id, topic)

        if is_correct:
            # Check if this fact was already mastered by this user
            was_mastered = (
                await self.db.scalar(
                    select(func.count(UserResponse.id))
                    .join(QuestionFact, QuestionFact.question_id == UserResponse.question_id)
                    .where(
                        (UserResponse.user_id == user_id)
                        & (QuestionFact.fact_id == fact_id)
                        & (UserResponse.answered_correct == True)
                    )
                )
            ) > 1  # More than 1 means was already mastered before this answer

            if not was_mastered:
                # First time mastering this fact
                mastery.mastered_facts_count = min(
                    mastery.mastered_facts_count + 1, mastery.total_facts_count
                )

        # Recalculate completion percentage
        if mastery.total_facts_count > 0:
            mastery.completion_percentage = (
                mastery.mastered_facts_count / mastery.total_facts_count * 100
            )
        else:
            mastery.completion_percentage = 0.0

        mastery.last_session_at = utc_now_naive()

        await self.db.commit()
        await self.db.refresh(mastery)

        return mastery

    async def generate_question_from_fact(
        self,
        fact: Fact,
        topic: str,
    ) -> dict | None:
        """
        Generate an MCQ from a fact.

        Strategy (cache-first):
        1. Try to find cached question for this topic
        2. If cache miss: call LLM to generate
        3. Save generated question + link to fact
        4. Return question dict (without correct answer)

        Args:
            fact: The fact to generate question from
            topic: Topic string (e.g., "History - World War II")

        Returns:
            Question dict with fields: id, text, options, explanation (null)
            Returns None if generation fails
        """
        # Try cache
        cached_q = (
            await self.db.execute(
                select(QuestionBank)
                .where(QuestionBank.topic == f"Custom - {topic}")
                .order_by(func.random())
                .limit(1)
            )
        ).scalar_one_or_none()

        if cached_q:
            logger.info(f"Cache hit for Custom Room question: {cached_q.id}")
            return {
                "id": str(cached_q.id),
                "text": cached_q.question_text,
                "options": json.loads(cached_q.options_json),
                "explanation": None,  # Don't reveal until submitted
            }

        # Cache miss: generate via LLM
        try:
            # Extract theme/country from topic (e.g., "World War II" from "History - World War II")
            theme = topic.split(" - ")[1] if " - " in topic else topic

            question_dict = await self.llm_service.generate_mcq(
                context=fact.content,
                topic=theme.lower(),
                difficulty=3,  # Default difficulty
                strategy="easy_recall",
            )

            if not question_dict:
                logger.warning(f"LLM failed to generate question for fact: {fact.id}")
                return None

            # Save to QuestionBank
            qb_id = UUID(question_dict.get("id", str(uuid4())))
            qb = QuestionBank(
                id=qb_id,
                question_text=question_dict["text"],
                correct_answer=question_dict["correctAnswer"],
                options_json=json.dumps(question_dict["options"]),
                explanation=question_dict.get("explanation", ""),
                topic=f"Custom - {topic}",
                difficulty_irt=2.0,
                source="custom_llm",
            )
            self.db.add(qb)
            await self.db.flush()

            # Link question to fact
            qf = QuestionFact(
                id=uuid4(),
                question_id=qb_id,
                fact_id=fact.id,
            )
            self.db.add(qf)
            await self.db.commit()

            logger.info(f"Generated question {qb_id} from fact {fact.id}")

            return {
                "id": str(qb_id),
                "text": question_dict["text"],
                "options": question_dict["options"],
                "explanation": None,
            }

        except Exception as e:
            logger.error(f"Error generating question: {e}")
            return None

    async def create_session(
        self,
        user_id: UUID,
        topic: str,
    ) -> dict:
        """
        Create a new Custom Room session.

        Initializes:
        - Redis session state
        - Database CustomSession record
        - UserTopicMastery if needed

        Args:
            user_id: User's ID
            topic: Topic string

        Returns:
            Dict with session_id, topic, progress_percentage, total_facts
        """
        session_id = str(uuid4())

        # Get or create mastery record
        mastery = await self.get_or_create_mastery(user_id, topic)

        # Create session in Redis
        session_state = {
            "session_id": session_id,
            "user_id": str(user_id),
            "topic": topic,
            "started_at": utc_now_naive().isoformat(),
            "correct_answer": None,  # Updated when question generated
            "current_fact_id": None,
            "question_id": None,
            "questions_answered": 0,
            "correct_count": 0,
        }
        await self.session_service.set_session(session_id, session_state, CUSTOM_ROOM_SESSION_TTL)

        # Create database record
        db_session = CustomSession(
            id=UUID(session_id),
            user_id=user_id,
            topic=topic,
            started_at=utc_now_naive(),
        )
        self.db.add(db_session)
        await self.db.commit()

        logger.info(f"Created Custom Room session {session_id} for user {user_id} on topic {topic}")

        return {
            "session_id": session_id,
            "topic": topic,
            "progress_percentage": round(mastery.completion_percentage, 2),
            "total_facts": mastery.total_facts_count,
        }

    async def end_session(self, session_id: str) -> dict:
        """
        Finalize a Custom Room session.

        Marks session as ended, calculates final completion percentage,
        returns summary.

        Args:
            session_id: The session ID (UUID as string)

        Returns:
            Summary dict with final stats
        """
        try:
            session_uuid = UUID(session_id)
        except ValueError:
            logger.error(f"Invalid session ID format: {session_id}")
            return {"error": "Invalid session ID"}

        # Get session from DB
        db_session = await self.db.get(CustomSession, session_uuid)
        if not db_session:
            logger.warning(f"Session not found: {session_id}")
            return {"error": "Session not found"}

        # Get final stats from Redis (in-flight answers)
        redis_session = await self.session_service.get_session(session_id)
        if redis_session:
            db_session.total_questions = redis_session.get("questions_answered", 0)
            db_session.correct_count = redis_session.get("correct_count", 0)

        # Get mastery % at end of session
        mastery = await self.get_or_create_mastery(db_session.user_id, db_session.topic)
        db_session.completion_percentage_after = mastery.completion_percentage
        db_session.ended_at = utc_now_naive()

        await self.db.commit()

        # Calculate duration
        duration = (db_session.ended_at - db_session.started_at).total_seconds()

        logger.info(f"Ended Custom Room session {session_id}: {db_session.correct_count}/{db_session.total_questions} correct")

        return {
            "session_id": session_id,
            "topic": db_session.topic,
            "questions_answered": db_session.total_questions,
            "correct_count": db_session.correct_count,
            "completion_percentage": round(mastery.completion_percentage, 2),
            "duration_seconds": int(duration),
        }

    @staticmethod
    def get_topics() -> dict[str, list[dict]]:
        """
        Get list of all available topics with metadata.

        Returns:
            Dict mapping topic type (e.g., "History") to list of topic dicts
        """
        result = {}

        for topic_type, themes in CUSTOM_ROOM_TOPICS.items():
            result[topic_type] = [
                {
                    "name": name,
                    "slug": name.lower().replace(" ", "_"),
                    "description": desc,
                    "total_facts": CUSTOM_ROOM_FACTS_PER_TOPIC,
                }
                for name, desc in themes.items()
            ]

        return result
