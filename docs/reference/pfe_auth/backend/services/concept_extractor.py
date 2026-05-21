"""services/concept_extractor.py — Extract and track concepts from generated questions."""

import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Concept
from services.llm import LLMClient

logger = logging.getLogger(__name__)


class ConceptExtractor:
    """Uses Groq LLM to identify primary and secondary concepts in questions."""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def extract_concepts(
        self,
        question_text: str,
        options: list[str],
        topic: str
    ) -> dict[str, str]:
        """
        Call Groq LLM to identify concepts tested by a question.

        Returns:
        {
            "primary": "Roman Empire",
            "secondary": ["Roman Military", "Ancient Rome"]
        }
        """
        # Use only first 4 options to avoid token explosion
        options_preview = ", ".join(options[:4])

        # Craft a focused prompt to extract concepts
        prompt = f"""Analyze this {topic} question and identify the knowledge concepts it tests.

Question: {question_text}
Options: {options_preview}

CRITICAL: In {topic}, concepts are specific, well-known domains within the topic.
Examples:
- For History: "Roman Empire", "Egyptian Dynasty", "Medieval Europe", "French Revolution"
- For Geography: "Alpine Mountains", "Amazon Rainforest", "Nile River", "Sahara Desert"
- For Mixed: Use appropriate domain concepts for each subject area

Identify EXACTLY TWO items:
1. PRIMARY concept (the main knowledge area this question tests)
2. SECONDARY concept (a related area that helps understand the primary)

Format your response EXACTLY like this:
PRIMARY: [single concept name]
SECONDARY: [single concept name]

Be specific and concise. Do not add explanations or extra text."""

        try:
            response = await self.llm_client.simple_completion(prompt)
            return self._parse_concept_response(response)
        except Exception as e:
            logger.error(
                "concept_extraction_failed",
                extra={"error": str(e), "question_snippet": question_text[:50]}
            )
            # Fallback: Return generic concept based on topic
            return {
                "primary": f"{topic} Fundamentals",
                "secondary": f"{topic} Knowledge"
            }

    async def ensure_concept_exists(
        self,
        db: AsyncSession,
        name: str,
        topic: str
    ) -> str:
        """Get or create a concept by name. Returns concept ID."""
        stmt = select(Concept).where(
            (Concept.name == name) & (Concept.topic == topic)
        )
        result = await db.execute(stmt)
        concept = result.scalar_one_or_none()

        if concept:
            return str(concept.id)

        # Create new concept
        concept = Concept(name=name, topic=topic, description="")
        db.add(concept)
        try:
            await db.flush()  # Get the ID without committing
            return str(concept.id)
        except Exception as e:
            logger.error(
                "concept_creation_failed",
                extra={"name": name, "topic": topic, "error": str(e)},
                exc_info=True,
            )
            raise  # Propagate error instead of silently masking with fallback UUID

    @staticmethod
    def _parse_concept_response(response: str) -> dict[str, str]:
        """
        Parse LLM response to extract PRIMARY and SECONDARY concepts.
        Format expected:
        PRIMARY: Roman Empire
        SECONDARY: Roman Military
        """
        primary = None
        secondary = None

        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("PRIMARY:"):
                primary = line.replace("PRIMARY:", "").strip()
            elif line.startswith("SECONDARY:"):
                secondary = line.replace("SECONDARY:", "").strip()

        # Fallback to generic if parsing fails
        if not primary:
            primary = "General Knowledge"
        if not secondary:
            secondary = "Related Topics"

        return {
            "primary": primary,
            "secondary": secondary
        }
