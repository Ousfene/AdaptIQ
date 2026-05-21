"""
seeds/test_fixture.py — Test fixture helper with automatic cleanup.

Provides TestFixture context manager for creating test questions that are
automatically cleaned up when the test finishes.

Usage:
    async with TestFixture(db) as fixture:
        # Create test questions
        q = await fixture.create_question(
            text="Test question",
            topic="geography",
            options=["a", "b", "c", "d"]
        )
        # Run tests...
        # Auto-cleanup on context exit
"""

import uuid
import json
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

from database.models import QuestionBank, QuestionConcept, Concept

logger = logging.getLogger(__name__)


class TestFixture:
    """Context manager for test questions with automatic cleanup."""

    def __init__(self, db: AsyncSession, prefix: str = "test"):
        """Initialize fixture.

        Args:
            db: AsyncSession for database access
            prefix: Prefix for test data identification (default: 'test')
        """
        self.db = db
        self.prefix = prefix
        self.test_questions: list[uuid.UUID] = []
        self.session_id = str(uuid.uuid4())

    async def __aenter__(self):
        """Enter context manager."""
        logger.info(f"[TEST] Fixture session {self.session_id} started")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - cleanup test questions."""
        await self.cleanup()
        return False

    async def create_question(
        self,
        text: str,
        topic: str,
        options: list[str],
        correct_answer: Optional[str] = None,
        explanation: str = "Test explanation",
        difficulty: float = 1.0,
    ) -> dict:
        """Create a test question.

        Args:
            text: Question text
            topic: Topic (geography, history, mix)
            options: List of answer options
            correct_answer: Correct answer (default: first option)
            explanation: Explanation text (default: "Test explanation")
            difficulty: IRT difficulty parameter (default: 1.0)

        Returns:
            Dictionary with question data
        """
        if correct_answer is None:
            correct_answer = options[0]

        question_id = uuid.uuid4()

        # Create question in database
        question = QuestionBank(
            id=question_id,
            question_text=text,
            correct_answer=correct_answer,
            options_json=json.dumps(options),
            explanation=explanation,
            topic=topic,
            difficulty_irt=difficulty,
            source="test",  # Mark as test question
            primary_concept_id=None,
        )

        self.db.add(question)
        await self.db.flush()

        self.test_questions.append(question_id)

        logger.info(
            f"[TEST] Created test question {question_id}: {text[:50]}..."
        )

        return {
            "id": str(question_id),
            "text": text,
            "options": options,
            "correct_answer": correct_answer,
            "explanation": explanation,
            "topic": topic,
            "difficulty_irt": difficulty,
        }

    async def create_concept(
        self,
        name: str,
        topic: str,
        description: Optional[str] = None,
    ) -> dict:
        """Create a test concept.

        Args:
            name: Concept name (e.g., "Egyptian Empire")
            topic: Topic (geography, history)
            description: Optional description

        Returns:
            Dictionary with concept data
        """
        concept_id = uuid.uuid4()

        concept = Concept(
            id=concept_id,
            name=f"{self.prefix}_{name}",
            topic=topic,
            description=description,
        )

        self.db.add(concept)
        await self.db.flush()

        logger.info(f"[TEST] Created test concept {concept_id}: {name}")

        return {
            "id": str(concept_id),
            "name": name,
            "topic": topic,
            "description": description,
        }

    async def cleanup(self):
        """Delete all test questions and concepts created by this fixture."""
        if not self.test_questions:
            logger.info(f"[TEST] Fixture {self.session_id}: No cleanup needed")
            return

        try:
            # Delete question concepts (cascade)
            await self.db.execute(
                delete(QuestionConcept).where(
                    QuestionConcept.question_id.in_(self.test_questions)
                )
            )

            # Delete questions
            await self.db.execute(
                delete(QuestionBank).where(
                    QuestionBank.id.in_(self.test_questions)
                )
            )

            await self.db.commit()

            logger.info(
                f"[TEST] Fixture {self.session_id}: Cleaned up {len(self.test_questions)} test questions"
            )
        except Exception as e:
            logger.error(
                f"[TEST] Fixture cleanup failed: {type(e).__name__}: {e}"
            )
            await self.db.rollback()
            raise

    async def get_test_question_count(self) -> int:
        """Get count of test questions created by this fixture."""
        return len(self.test_questions)
