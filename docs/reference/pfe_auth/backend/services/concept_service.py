"""
services/concept_service.py — Concept Discovery Service.

Handles dynamic concept creation when RAG generates questions about
topics not in the seed data. Uses fuzzy matching to avoid duplicates.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from difflib import SequenceMatcher

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Concept

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def similarity_ratio(a: str, b: str) -> float:
    """Calculate string similarity ratio (0.0 to 1.0)."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


class ConceptDiscoveryService:
    """
    Service for discovering and creating new concepts dynamically.
    
    When RAG generates a question about a new topic (e.g., "Aztec Empire"),
    this service checks if a similar concept exists and creates one if not.
    """
    
    # Minimum similarity to consider concepts as duplicates
    SIMILARITY_THRESHOLD = 0.85
    
    @staticmethod
    async def find_similar_concept(
        db: AsyncSession,
        concept_name: str,
        topic: str,
    ) -> Optional[Concept]:
        """
        Find an existing concept that's similar to the given name.
        
        Uses fuzzy matching to handle variations like:
        - "Roman Empire" vs "The Roman Empire"
        - "Nile River" vs "Nile River Basin"
        """
        # First try exact match (case-insensitive)
        exact_stmt = select(Concept).where(
            func.lower(Concept.name) == concept_name.lower().strip()
        )
        result = await db.execute(exact_stmt)
        exact_match = result.scalar_one_or_none()
        if exact_match:
            return exact_match
        
        # Try fuzzy matching within the same topic
        topic_stmt = select(Concept).where(Concept.topic == topic)
        result = await db.execute(topic_stmt)
        topic_concepts = result.scalars().all()
        
        best_match = None
        best_ratio = 0.0
        
        for concept in topic_concepts:
            ratio = similarity_ratio(concept_name, concept.name)
            if ratio > best_ratio and ratio >= ConceptDiscoveryService.SIMILARITY_THRESHOLD:
                best_ratio = ratio
                best_match = concept
        
        if best_match:
            logger.info(f"Fuzzy matched '{concept_name}' to existing '{best_match.name}' (similarity: {best_ratio:.2f})")
        
        return best_match
    
    @staticmethod
    async def get_or_create_concept(
        db: AsyncSession,
        concept_name: str,
        topic: str,
        description: Optional[str] = None,
    ) -> Concept:
        """
        Find an existing concept or create a new one.
        
        Args:
            db: Database session
            concept_name: Name of the concept (e.g., "Aztec Empire")
            topic: Topic category ("geography" or "history")
            description: Optional description of the concept
        
        Returns:
            Existing or newly created Concept
        """
        # Normalize inputs
        concept_name = concept_name.strip()
        topic = topic.lower().strip()
        
        # Validate topic
        if topic not in ("geography", "history", "mix"):
            topic = "history" if any(w in concept_name.lower() for w in ["empire", "dynasty", "war", "battle", "kingdom"]) else "geography"
        
        # For "mix", determine the more likely topic
        if topic == "mix":
            topic = "history" if any(w in concept_name.lower() for w in ["empire", "dynasty", "war", "battle", "kingdom", "civilization"]) else "geography"
        
        # Check for existing similar concept
        existing = await ConceptDiscoveryService.find_similar_concept(db, concept_name, topic)
        if existing:
            return existing
        
        # Create new concept
        new_concept = Concept(
            id=uuid.uuid4(),
            name=concept_name,
            topic=topic,
            description=description or f"Dynamically discovered concept: {concept_name}",
            created_at=utc_now(),
        )
        db.add(new_concept)
        await db.flush()
        
        logger.info(f"Created new concept: '{concept_name}' (topic: {topic})")
        
        return new_concept
    
    @staticmethod
    async def extract_concept_from_question(
        question_text: str,
        correct_answer: str,
        topic: str,
    ) -> tuple[str, str]:
        """
        Extract concept name and description from question context.
        
        This is a fallback when LLM doesn't provide concept info.
        Uses simple heuristics to guess the concept.
        
        Returns:
            (concept_name, concept_description)
        """
        # Common patterns for concept extraction
        text_lower = question_text.lower()
        
        # History patterns
        history_keywords = {
            "empire": ["roman", "persian", "ottoman", "mongol", "byzantine", "egyptian", "aztec", "inca", "british", "spanish"],
            "war": ["world war", "civil war", "revolutionary", "napoleonic"],
            "dynasty": ["ming", "qing", "han", "tang", "song"],
            "civilization": ["greek", "roman", "egyptian", "mesopotamian", "mayan"],
        }
        
        for category, keywords in history_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    concept_name = f"{keyword.title()} {category.title()}"
                    return concept_name, f"Historical {category} related to {keyword.title()}"
        
        # Geography patterns
        geo_keywords = {
            "river": ["nile", "amazon", "mississippi", "yangtze", "ganges", "danube", "rhine"],
            "mountain": ["everest", "himalaya", "alps", "andes", "rockies", "kilimanjaro"],
            "desert": ["sahara", "gobi", "arabian", "kalahari", "mojave"],
            "ocean": ["pacific", "atlantic", "indian", "arctic", "southern"],
            "sea": ["mediterranean", "caribbean", "red sea", "baltic", "black sea"],
        }
        
        for category, keywords in geo_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    concept_name = f"{keyword.title()} {category.title()}"
                    return concept_name, f"Geographic feature: {keyword.title()} {category.title()}"
        
        # Fallback: use the correct answer as concept hint
        if len(correct_answer) > 3:
            return correct_answer, f"Concept related to: {correct_answer}"
        
        # Ultimate fallback
        return f"General {topic.title()}", f"General {topic} knowledge"
    
    @staticmethod
    async def ensure_question_has_concept(
        db: AsyncSession,
        question_text: str,
        correct_answer: str,
        topic: str,
        llm_concept_name: Optional[str] = None,
        llm_concept_description: Optional[str] = None,
    ) -> Concept:
        """
        Ensure a question is linked to a concept, creating one if needed.
        
        Priority:
        1. Use LLM-provided concept name/description if available
        2. Extract concept from question text using heuristics
        3. Create generic concept as fallback
        
        Returns:
            The Concept to link the question to
        """
        # Use LLM-provided concept if available
        if llm_concept_name and len(llm_concept_name.strip()) > 2:
            return await ConceptDiscoveryService.get_or_create_concept(
                db, llm_concept_name, topic, llm_concept_description
            )
        
        # Extract concept from question
        extracted_name, extracted_desc = await ConceptDiscoveryService.extract_concept_from_question(
            question_text, correct_answer, topic
        )
        
        return await ConceptDiscoveryService.get_or_create_concept(
            db, extracted_name, topic, extracted_desc
        )
