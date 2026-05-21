"""
services/concept_service.py
Concept discovery and normalization for concept-aware quiz tracking.

Covers:
    - Topic family/detail normalization and concept-name cleaning helpers
    - Similarity-based concept matching and creation logic
    - Topic seeding for reusable concept clusters
    - Question-text cue extraction for automatic concept inference
"""

import re
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.concept_models import Concept


# Compute normalized string similarity for concept de-duplication.
def similarity_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


# Normalize free-form topic labels into stable topic families.
def _normalize_topic_family(topic: str) -> str:
    normalized_topic = (topic or "").lower().strip()
    if normalized_topic in ("history", "geography", "mixed", "mix"):
        return "mixed" if normalized_topic == "mix" else normalized_topic
    if normalized_topic.startswith("history"):
        return "history"
    if normalized_topic.startswith("geography"):
        return "geography"
    return "mixed"


# Extract the specific topic detail segment from a topic label.
def _topic_detail(topic_label: Optional[str], fallback_topic: str) -> str:
    if topic_label and " - " in topic_label:
        return topic_label.split(" - ", 1)[-1].strip()
    if topic_label:
        return topic_label.strip()
    return fallback_topic.title().strip()


# Clean concept names for safe storage and display.
def _clean_concept_name(name: str, max_len: int = 120) -> str:
    cleaned = re.sub(r"\s+", " ", (name or "").strip())
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(" ,;:-")
    return cleaned


# Check whether text contains any cue tokens as full words.
def _contains_any(text: str, words: list[str]) -> bool:
    blob = f" {text.lower()} "
    return any(f" {w.lower()} " in blob for w in words)


class ConceptDiscoveryService:
    SIMILARITY_THRESHOLD = 0.85

    HISTORY_BUCKETS = {
        "Timeline and Turning Points": ["when", "year", "date", "timeline", "period", "era", "before", "after"],
        "Causes and Triggers": ["cause", "why", "trigger", "spark", "led to", "because"],
        "Key Figures and Leadership": ["who", "leader", "ruler", "president", "emperor", "commander", "figure"],
        "Battles, Wars, and Diplomacy": ["battle", "war", "treaty", "alliance", "armistice", "front", "campaign"],
        "Institutions and Reforms": ["constitution", "parliament", "assembly", "government", "law", "reform", "policy"],
        "Society, Economy, and Ideas": ["economy", "trade", "labor", "class", "society", "ideology", "movement"],
    }

    GEOGRAPHY_BUCKETS = {
        "Physical Geography": ["river", "mountain", "desert", "climate", "plateau", "valley", "coast", "ocean", "sea"],
        "Cities and Administrative Centers": ["capital", "city", "province", "state", "district", "territory"],
        "Population and Culture": ["population", "language", "culture", "ethnic", "religion", "migration", "demography"],
        "Economy and Resources": ["resource", "industry", "agriculture", "export", "import", "gdp", "economy"],
        "Infrastructure and Transport": ["port", "rail", "road", "airport", "transport", "infrastructure"],
        "Borders and Geopolitics": ["border", "neighbor", "region", "geopolit", "territorial", "union"],
    }

    @staticmethod
    # Build seed concept clusters for a strict topic label.
    def _seed_concept_names(topic_label: str) -> list[tuple[str, str, str]]:
        topic_family = _normalize_topic_family(topic_label)
        detail = _topic_detail(topic_label, topic_family)
        if topic_family == "history":
            return [
                (
                    _clean_concept_name(f"{detail} - Timeline and Turning Points"),
                    "history",
                    f"Auto-discovered concept cluster for {detail}: timeline and major transitions.",
                ),
                (
                    _clean_concept_name(f"{detail} - Causes and Triggers"),
                    "history",
                    f"Auto-discovered concept cluster for {detail}: causes, catalysts, and root drivers.",
                ),
                (
                    _clean_concept_name(f"{detail} - Consequences and Legacy"),
                    "history",
                    f"Auto-discovered concept cluster for {detail}: long-term outcomes and impact.",
                ),
                (
                    _clean_concept_name(f"{detail} - Key Figures and Decisions"),
                    "history",
                    f"Auto-discovered concept cluster for {detail}: major actors and decision points.",
                ),
            ]
        if topic_family == "geography":
            return [
                (
                    _clean_concept_name(f"{detail} - Physical Geography"),
                    "geography",
                    f"Auto-discovered concept cluster for {detail}: terrain, climate, and natural systems.",
                ),
                (
                    _clean_concept_name(f"{detail} - Cities and Population"),
                    "geography",
                    f"Auto-discovered concept cluster for {detail}: cities, demographics, and settlement patterns.",
                ),
                (
                    _clean_concept_name(f"{detail} - Economy and Resources"),
                    "geography",
                    f"Auto-discovered concept cluster for {detail}: resources, trade, and economic geography.",
                ),
                (
                    _clean_concept_name(f"{detail} - Regional and Geopolitical Context"),
                    "geography",
                    f"Auto-discovered concept cluster for {detail}: regional relations and geopolitical positioning.",
                ),
            ]
        return [
            (
                _clean_concept_name(f"{detail} - Core Concepts"),
                "mixed",
                f"Auto-discovered mixed-topic concept cluster for {detail}.",
            )
        ]

    @staticmethod
    # Find best matching concept by exact or similarity search.
    async def find_similar_concept(db: AsyncSession, concept_name: str, topic: str) -> Optional[Concept]:
        exact_stmt = select(Concept).where(func.lower(Concept.name) == concept_name.lower().strip())
        exact = (await db.execute(exact_stmt)).scalar_one_or_none()
        if exact:
            return exact

        candidates = (
            await db.execute(select(Concept).where(Concept.topic == topic.lower().strip()))
        ).scalars().all()

        best = None
        score = 0.0
        for c in candidates:
            ratio = similarity_ratio(concept_name, c.name)
            if ratio >= ConceptDiscoveryService.SIMILARITY_THRESHOLD and ratio > score:
                best = c
                score = ratio
        return best

    @staticmethod
    # Return an existing concept or create a new normalized concept row.
    async def get_or_create_concept(
        db: AsyncSession,
        concept_name: str,
        topic: str,
        description: Optional[str] = None,
    ) -> Concept:
        normalized_topic = _normalize_topic_family(topic)
        normalized_name = _clean_concept_name(concept_name)
        if not normalized_name:
            normalized_name = f"{normalized_topic.title()} Core Concept"

        existing = await ConceptDiscoveryService.find_similar_concept(db, normalized_name, normalized_topic)
        if existing:
            return existing

        concept = Concept(
            name=normalized_name,
            topic=normalized_topic,
            description=description or f"Auto-discovered concept: {normalized_name}",
        )
        db.add(concept)
        await db.flush()
        return concept

    @staticmethod
    # Ensure a topic has baseline seed concepts for rotation/reuse.
    async def ensure_topic_seed_concepts(
        db: AsyncSession,
        topic_label: str,
        max_new: int = 4,
    ) -> list[Concept]:
        """Ensure each strict topic has a small rotating concept pool.

        This avoids getting stuck in a tiny repeated concept set by creating
        reusable concept clusters per topic detail (for example: "France - Physical Geography").
        """
        seed_rows = ConceptDiscoveryService._seed_concept_names(topic_label)
        out: list[Concept] = []
        for idx, (name, topic, description) in enumerate(seed_rows):
            if idx >= max_new:
                break
            concept = await ConceptDiscoveryService.get_or_create_concept(
                db=db,
                concept_name=name,
                topic=topic,
                description=description,
            )
            out.append(concept)
        return out

    @staticmethod
    # Infer concept name/description from question cues and topic context.
    async def extract_concept_from_question(
        question_text: str,
        correct_answer: str,
        topic: str,
        explanation: str = "",
        topic_label: Optional[str] = None,
    ) -> tuple[str, str]:
        topic_family = _normalize_topic_family(topic)
        anchor = _topic_detail(topic_label, topic_family)
        text_blob = " ".join(
            [
                (question_text or "").strip(),
                (explanation or "").strip(),
            ]
        ).lower()

        if topic_family == "history":
            for bucket_name, cues in ConceptDiscoveryService.HISTORY_BUCKETS.items():
                if _contains_any(text_blob, cues):
                    concept_name = _clean_concept_name(f"{anchor} - {bucket_name}")
                    return (
                        concept_name,
                        f"Historical concept inferred from question cues in the {bucket_name.lower()} bucket.",
                    )
            return (
                _clean_concept_name(f"{anchor} - Core Historical Concepts"),
                "Historical concept inferred from broader context.",
            )

        if topic_family == "geography":
            for bucket_name, cues in ConceptDiscoveryService.GEOGRAPHY_BUCKETS.items():
                if _contains_any(text_blob, cues):
                    concept_name = _clean_concept_name(f"{anchor} - {bucket_name}")
                    return (
                        concept_name,
                        f"Geographic concept inferred from question cues in the {bucket_name.lower()} bucket.",
                    )
            return (
                _clean_concept_name(f"{anchor} - Core Geographic Concepts"),
                "Geographic concept inferred from broader context.",
            )

        if len((correct_answer or "").strip()) > 2:
            return (
                _clean_concept_name(f"{anchor} - {(correct_answer or '').strip()} Context"),
                "Mixed-topic concept inferred from answer context.",
            )
        return (
            _clean_concept_name(f"{anchor} - Core Concepts"),
            "Mixed-topic concept inferred from generated question context.",
        )

    @staticmethod
    # Resolve final concept assignment for a question payload.
    async def ensure_question_has_concept(
        db: AsyncSession,
        question_text: str,
        correct_answer: str,
        topic: str,
        explanation: str = "",
        topic_label: Optional[str] = None,
        llm_concept_name: Optional[str] = None,
        llm_concept_description: Optional[str] = None,
    ) -> Concept:
        if llm_concept_name and len(llm_concept_name.strip()) > 2:
            return await ConceptDiscoveryService.get_or_create_concept(
                db,
                llm_concept_name,
                topic,
                llm_concept_description,
            )

        name, desc = await ConceptDiscoveryService.extract_concept_from_question(
            question_text,
            correct_answer,
            topic,
            explanation=explanation,
            topic_label=topic_label,
        )
        return await ConceptDiscoveryService.get_or_create_concept(db, name, topic, desc)
