"""
rag/agentic.py — 3-Agent RAG pipeline.

AGENT 1 — ROUTER:
    Takes topic + difficulty + user_history → decides source weights
    and builds a targeted retrieval plan.

AGENT 2 — RETRIEVER:
    Executes the plan:  70% Wikipedia | 20% HF dataset | 10% Wikidata
    Cascades on failure (never returns empty-handed if any source works).

AGENT 3 — VALIDATOR:
    LLM self-check: "Is this question at difficulty {target}?"
    Regenerates once if the answer is NO.
"""

from __future__ import annotations
import asyncio
import random
import logging
import httpx
from typing import Optional

from rag.wikipedia import fetch_wikipedia_context, fetch_related_titles
from rag.wikidata import fetch_wikidata_facts, format_wikidata_as_context
from rag.hf_dataset import async_get_hf_question

logger = logging.getLogger(__name__)


# ── Agent 1: ROUTER ────────────────────────────────────────────────────────

class RouterAgent:
    """
    Analyses user history and topic to select RAG source weights.

    Rules:
    - History easy (diff 1-2):  Wikipedia "major battles" queries
    - Geography hard (diff 4-5): Wikidata "capitals pop<1M"
    - Mixed: 60% weak topic + 40% strong
    - Default: 70% Wikipedia | 20% HF | 10% Wikidata
    """

    def route(
        self,
        topic: str,
        difficulty: int,
        user_accuracy: float,
        weak_topic: Optional[str] = None,
    ) -> dict:
        """
        Returns source weights and retrieval strategy metadata.
        weights = {wikipedia: int, huggingface: int, wikidata: int} (sum=100)
        """
        weights = {"wikipedia": 70, "huggingface": 20, "wikidata": 10}

        # Hard Geography → lean on Wikidata structured facts
        if topic == "geography" and difficulty >= 4:
            weights = {"wikipedia": 40, "huggingface": 20, "wikidata": 40}
            logger.info("Router: Geography hard → Wikidata boost")

        # Hard History → more Wikipedia for narrative context
        elif topic == "history" and difficulty >= 4:
            weights = {"wikipedia": 70, "huggingface": 10, "wikidata": 20}

        # Easy → lean on HF pre-validated pairs (most reliable recall Qs)
        elif difficulty <= 2:
            weights = {"wikipedia": 60, "huggingface": 35, "wikidata": 5}

        # Mixed + identified weak topic → bias toward weak topic
        elif topic == "mix" and weak_topic:
            # This is handled at a higher level; just note it in metadata
            pass

        # User struggling (low accuracy) → easier sources for confidence
        if user_accuracy < 0.4 and difficulty > 2:
            weights["huggingface"] = min(40, weights["huggingface"] + 15)
            weights["wikipedia"] = max(40, weights["wikipedia"] - 10)
            weights["wikidata"] = max(5, weights["wikidata"] - 5)

        return {
            "weights": weights,
            "topic": topic,
            "difficulty": difficulty,
            "strategy": self._describe_strategy(topic, difficulty, user_accuracy),
        }

    @staticmethod
    def _describe_strategy(topic: str, difficulty: int, accuracy: float) -> str:
        if difficulty <= 2:
            return "easy_recall"
        elif difficulty == 3:
            return "conceptual_connections"
        else:
            return "multi_hop_inference"


# ── Agent 2: RETRIEVER ────────────────────────────────────────────────────

class RetrieverAgent:
    """
    Executes the Router's plan using weighted random source selection.
    Cascades across sources on failure.
    """

    async def retrieve(
        self,
        plan: dict,
        client: httpx.AsyncClient,
    ) -> dict | None:
        """
        Returns a context bundle:
        {source, context_text, title, raw_hf_question (if HF source)}
        """
        weights = plan["weights"]
        topic   = plan["topic"]
        diff    = plan["difficulty"]

        # Build weighted source list
        source_order = self._weighted_order(weights)

        for source in source_order:
            result = await self._fetch_from(source, topic, diff, client)
            if result:
                result["source"] = source
                logger.info(f"Retriever: got context from {source}")
                return result

        logger.warning("Retriever: all sources failed")
        return None

    @staticmethod
    def _weighted_order(weights: dict) -> list[str]:
        """Convert weights dict → ordered list using weighted random draw."""
        total = sum(weights.values())
        roll = random.randint(1, total)
        cum = 0
        chosen = "wikipedia"
        for src, w in weights.items():
            cum += w
            if roll <= cum:
                chosen = src
                break
        # Remaining sources as fallbacks
        rest = [s for s in weights if s != chosen]
        random.shuffle(rest)
        return [chosen] + rest

    async def _fetch_from(
        self,
        source: str,
        topic: str,
        difficulty: int,
        client: httpx.AsyncClient,
    ) -> dict | None:
        if source == "wikipedia":
            ctx = await fetch_wikipedia_context(topic, difficulty, client)
            if ctx:
                return {"context_text": ctx["context"], "title": ctx["title"]}

        elif source == "huggingface":
            hf = await async_get_hf_question(topic, difficulty)
            if hf:
                return {
                    "context_text": hf.get("explanation", ""),
                    "title": "HF Dataset",
                    "raw_hf_question": hf,
                }

        elif source == "wikidata":
            facts = await fetch_wikidata_facts(topic, difficulty, client)
            if facts:
                ctx = format_wikidata_as_context(facts)
                return {"context_text": ctx, "title": "Wikidata Facts"}

        return None


# ── Agent 3: VALIDATOR ────────────────────────────────────────────────────

class ValidatorAgent:
    """
    Self-check: after LLM generates a question, send a lightweight
    validation prompt to confirm the difficulty matches the target.
    Regenerates once if it doesn't pass.
    """

    @staticmethod
    def _sanitize_for_prompt(text: str) -> str:
        """
        Sanitize text to prevent prompt injection in validation prompts.
        
        ═══════ RAG-3 FIX: Prompt injection defense ═══════
        """
        if not text:
            return ""
        # Remove newlines that could break prompt structure
        sanitized = text.replace("\n", " ").replace("\r", " ")
        # Remove common injection patterns
        sanitized = sanitized.replace("Answer:", "").replace("ANSWER:", "")
        sanitized = sanitized.replace("YES", "yes").replace("NO", "no")
        # Escape quotes
        sanitized = sanitized.replace('"', '\\"')
        # Limit length to prevent context flooding
        return sanitized[:500]

    def build_validation_prompt(self, question: dict, target_difficulty: int) -> str:
        difficulty_descriptions = {
            1: "very easy direct recall (major capitals, famous battles)",
            2: "easy recall (well-known facts)",
            3: "medium (requires connecting two facts)",
            4: "hard (multi-hop reasoning, less-known facts)",
            5: "very hard (obscure, requires expert knowledge)",
        }
        desc = difficulty_descriptions.get(target_difficulty, "medium")
        
        # ═══════ RAG-3 FIX: Sanitize question content ═══════
        question_text = self._sanitize_for_prompt(question.get('text', ''))
        correct_answer = self._sanitize_for_prompt(question.get('correctAnswer', ''))
        
        return f"""You are a difficulty validator for educational MCQs.

Target difficulty: {target_difficulty}/5 ({desc})

Question to validate:
"{question_text}"

Correct Answer: "{correct_answer}"

Does this question match difficulty {target_difficulty}/5?
Answer with ONLY: YES or NO"""

    def is_valid(self, validation_response: str, target_difficulty: int) -> bool:
        """Parse validator response."""
        text = validation_response.strip().upper()
        return text.startswith("YES")


# ── Orchestrator ──────────────────────────────────────────────────────────

class AgenticRAGPipeline:
    """
    Coordinates all 3 agents to produce a validated question.
    
    1. Router decides source weights from context
    2. Retriever fetches relevant facts from chosen source(s)
    3. LLM generates the MCQ from retrieved facts
    4. Validator checks difficulty alignment (1 regeneration allowed)
    """

    def __init__(self):
        self.router    = RouterAgent()
        self.retriever = RetrieverAgent()
        self.validator = ValidatorAgent()

    def _get_fallback_context(self, topic: str, difficulty: int) -> dict | None:
        """
        Provide generic fallback contexts when external APIs fail.
        This ensures questions can still be generated via LLM.
        """
        fallback_contexts = {
            "geography": {
                1: "Paris is the capital of France, located in Western Europe. France is bordered by Spain, Italy, Germany, and other countries. The capital city has major landmarks including the Eiffel Tower.",
                2: "Egypt is a country in North Africa with Cairo as its capital. The Nile River is the longest river in the world and flows through Egypt. Ancient Egypt had pharaohs and built the pyramids.",
                3: "The Democratic Republic of Congo is a large country in Central Africa. Its capital is Kinshasa. It borders many other African countries and has significant mineral resources.",
                4: "Djibouti is a small country in the Horn of Africa, located at the entrance to the Red Sea. It has strategic importance for shipping and has been home to various colonial powers.",
                5: "Mauritius is an island nation in the Indian Ocean east of Africa. It has a diverse multicultural population and was a British colony before independence.",
            },
            "history": {
                1: "World War II (1939-1945) was a major global conflict. Adolf Hitler led Germany during this war. The war involved many countries including the United States, Soviet Union, and United Kingdom.",
                2: "The French Revolution (1789-1799) was a period of social and political upheaval in France. It led to the end of absolute monarchy and the rise of modern democracy.",
                3: "The Ottoman Empire was a major historical power that lasted for over 600 years. It had its capital in Constantinople (modern-day Istanbul) and controlled large parts of Europe, Asia, and Africa.",
                4: "The Mongol Empire under Genghis Khan became one of the largest contiguous land empires. It expanded rapidly in the 13th century and connected Eastern and Western civilizations.",
                5: "The Sassanid Persian Empire was a major power in ancient and medieval times, lasting from 224 to 651 AD. It was a rival to the Roman and Byzantine empires.",
            },
            "mix": {
                1: "Geography and history are interconnected. Paris in France is famous for both its historical significance and geographic location in Europe.",
                2: "The Mediterranean Sea has been central to both geography and history, connecting Europe, Africa, and Asia.",
                3: "The Silk Road was a historic trade route that connected different civilizations and geography across Asia and Europe.",
                4: "The Suez Canal connects the Mediterranean Sea to the Red Sea, making it one of the most important geographic and historic waterways.",
                5: "Historic empires often expanded along geographic features like rivers and coastlines, shaping trade routes and cultural connections.",
            },
        }

        topic_key = "history" if "history" in topic.lower() else ("geography" if "geography" in topic.lower() else "mix")
        contexts = fallback_contexts.get(topic_key, fallback_contexts["mix"])
        context = contexts.get(difficulty, contexts.get(3))  # Default to difficulty 3

        if context:
            logger.info(f"Using fallback context for {topic_key} difficulty {difficulty}")
            return {
                "context_text": context,
                "title": f"Fallback Context - {topic_key}",
                "source": "fallback"
            }

        return None

    async def run(
        self,
        topic: str,
        difficulty: int,
        user_accuracy: float,
        llm_client,  # LLMClient instance
        http_client: httpx.AsyncClient,
        weak_topic: Optional[str] = None,
    ) -> dict | None:
        """
        Full pipeline. Returns a question dict matching QuestionOut fields,
        or None if all sources + LLM failed.
        """
        # Agent 1: Route
        plan = self.router.route(topic, difficulty, user_accuracy, weak_topic)
        logger.info(f"RAG plan: {plan['strategy']} | weights: {plan['weights']}")

        # Agent 2: Retrieve
        context_bundle = await self.retriever.retrieve(plan, http_client)
        if not context_bundle:
            logger.warning("AgenticRAG: no context retrieved - using fallback generic context")
            # Fallback: provide generic context for LLM to work with
            context_bundle = self._get_fallback_context(topic, difficulty)
            if not context_bundle:
                return None

        # If HF source returned a complete question, use it directly (skip LLM)
        if "raw_hf_question" in context_bundle:
            hf_q = context_bundle["raw_hf_question"]
            import uuid
            return {
                "id": str(uuid.uuid4()),
                "text": hf_q["question"],
                "options": hf_q["options"],
                "correctAnswer": hf_q["correct_answer"],  # FIX: Use camelCase to match rest of codebase
                "explanation": hf_q.get("explanation", ""),
                "source": "huggingface",
            }

        # Agent 3: LLM generates + Validator checks
        question = await self._generate_with_validation(
            context_bundle, topic, difficulty, llm_client, plan["strategy"]
        )
        return question

    async def _generate_with_validation(
        self,
        context_bundle: dict,
        topic: str,
        difficulty: int,
        llm_client,
        strategy: str,
        max_retries: int = 2,
    ) -> dict | None:
        """Generate MCQ and validate difficulty. Retry once if failed."""
        context_text = context_bundle.get("context_text", "")
        source       = context_bundle.get("source", "wikipedia")

        for attempt in range(max_retries):
            question = await llm_client.generate_mcq(
                context=context_text,
                topic=topic,
                difficulty=difficulty,
                strategy=strategy,
            )
            if not question:
                continue

            # Validate difficulty (Agent 3)
            if attempt < max_retries - 1:   # skip on last attempt to avoid loops
                validation_prompt = self.validator.build_validation_prompt(
                    question, difficulty
                )
                try:
                    val_response = await llm_client.simple_completion(validation_prompt)
                    if not self.validator.is_valid(val_response, difficulty):
                        logger.info(f"Validator rejected question at attempt {attempt}, regenerating...")
                        # ═══════ RAG-7 FIX: Actually bump difficulty for regeneration ═══════
                        # Was: difficulty = max(1, min(5, difficulty)) - did nothing!
                        # Now: increment difficulty to get a harder question on retry
                        difficulty = max(1, min(5, difficulty + 1))
                        continue
                except Exception as e:
                    logger.error(f"RAG validation error (difficulty={difficulty}): {type(e).__name__}: {e}")
                    # Fallback: accept question without validation

            question["source"] = source
            return question

        return None
