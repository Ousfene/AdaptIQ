"""
services/llm.py — Groq Llama 3.1-8B-instant client.
Fixed:
  1. correctAnswer always first → now shuffled AFTER generation
  2. Hint reveals answer → stricter prompt that forbids naming the answer
  3. Repeated questions → higher temperature + explicit "do not repeat" instruction
"""

import json
import re
import uuid
import random
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.1-8b-instant"

DIFFICULTY_INSTRUCTIONS = {
    1: "VERY EASY — single well-known fact. Major capitals, famous battles, common dates.",
    2: "EASY — known fact with minor context. Identify a country from its capital, cause of a war.",
    3: "MEDIUM — connect two facts. Which country bordered X and was involved in Y.",
    4: "HARD — multi-hop reasoning, less-famous facts. Lesser-known treaties, small capitals.",
    5: "VERY HARD — expert-level, obscure. Pre-medieval events, smallest capitals by population.",
}

MCQ_SYSTEM_PROMPT = """You are an expert educational MCQ generator.
Return ONLY a valid JSON object — no markdown, no backticks, no extra text.

STRICT JSON structure:
{
  "text": "the question",
  "correct": "the single correct answer",
  "wrong1": "plausible wrong answer",
  "wrong2": "plausible wrong answer",
  "wrong3": "plausible wrong answer",
  "explanation": "1-2 sentences explaining WHY the correct answer is right, without restating the question",
  "concept": "the specific concept being tested (e.g., 'Roman Empire', 'Nile River', 'World War I')",
  "concept_description": "brief 1-sentence description of this concept"
}

RULES:
- correct and wrong1/2/3 must all be different
- wrong answers must be plausible (same category as correct — e.g. all capitals, all dates)
- explanation must NOT just repeat the question — add a new fact or context
- concept must be the SPECIFIC topic tested (e.g., 'Aztec Empire', not just 'History')
- concept_description should briefly describe what this concept is about
- Return ONLY the JSON, nothing else"""


class LLMClient:

    def __init__(self, api_key: str, timeout: float = 20.0):
        self.api_key = api_key
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def generate_mcq(
        self,
        context: str,
        topic: str,
        difficulty: int,
        strategy: str = "easy_recall",
        user_accuracy: float = 0.5,
    ) -> Optional[dict]:
        difficulty = max(1, min(5, difficulty))
        diff_instruction = DIFFICULTY_INSTRUCTIONS[difficulty]

        user_prompt = f"""TOPIC: {topic}
DIFFICULTY: {difficulty}/5 — {diff_instruction}

CONTEXT (base your question on this — do not hallucinate beyond it):
\"\"\"{context[:800]}\"\"\"

Generate ONE unique MCQ. Make it different from common textbook questions.
Return ONLY the JSON."""

        try:
            # Higher temperature = more variety, fewer repeats
            response = await self._chat_completion(
                system=MCQ_SYSTEM_PROMPT,
                user=user_prompt,
                temperature=0.92,
                max_tokens=500,
            )
            if not response:
                return None

            parsed = self._parse_json_response(response)
            if not parsed:
                return None

            # Validate all required fields present
            required = ["text", "correct", "wrong1", "wrong2", "wrong3", "explanation"]
            if not all(k in parsed for k in required):
                logger.warning(f"LLM missing fields: {list(parsed.keys())}")
                return None

            # ── FIX 1: Build options and SHUFFLE so correct is never always first ──
            correct = str(parsed["correct"]).strip()
            options = [
                correct,
                str(parsed["wrong1"]).strip(),
                str(parsed["wrong2"]).strip(),
                str(parsed["wrong3"]).strip(),
            ]
            # Remove duplicates
            seen = set()
            unique_options = []
            for opt in options:
                if opt.lower() not in seen:
                    seen.add(opt.lower())
                    unique_options.append(opt)

            # Pad if duplicates removed
            pads = ["None of the above", "Cannot be determined", "All of the above", "Insufficient data"]
            while len(unique_options) < 4:
                unique_options.append(pads.pop(0))

            # SHUFFLE — correct answer ends up in random position
            random.shuffle(unique_options)

            return {
                "id": str(uuid.uuid4()),
                "text": str(parsed["text"]).strip(),
                "options": unique_options,
                "correctAnswer": correct,   # still points to the right answer after shuffle
                "explanation": str(parsed["explanation"]).strip(),
                # Concept discovery fields (optional)
                "concept": parsed.get("concept", "").strip() if parsed.get("concept") else None,
                "concept_description": parsed.get("concept_description", "").strip() if parsed.get("concept_description") else None,
            }

        except Exception as e:
            logger.error(f"LLM generate_mcq failed: {e}")
            return None

    async def generate_hint(
        self,
        question_text: str,
        correct_answer: str,
    ) -> Optional[str]:
        # ── FIX 2: Strict hint prompt — must NOT reveal the answer ──
        prompt = f"""You are giving a hint for a quiz question. 

Question: "{question_text}"
Correct Answer (DO NOT reveal this): "{correct_answer}"

Write ONE short hint (max 20 words) that:
- Helps the student think in the right direction
- Does NOT say the answer or any part of it
- Points to a category, time period, or geographic region
- Is cryptic enough to still be a challenge

Examples of GOOD hints:
- "Think about events in the early 20th century in Eastern Europe."
- "This is a landlocked country in Central Asia."
- "Consider which empire dominated the Mediterranean before Rome."

Examples of BAD hints (too direct):
- "The answer involves Napoleon." (names the subject)
- "It starts with the letter F." (too obvious)

Return ONLY the hint text, nothing else."""

        try:
            response = await self._chat_completion(
                system="You are a quiz hint generator. Give short cryptic hints. Never reveal the answer. Max 20 words.",
                user=prompt,
                temperature=0.8,
                max_tokens=60,   # Force short response
            )
            if not response:
                logger.warning("hint_generation_empty", extra={"question": question_text[:50]})
                return None
            hint = response.strip()
            # Safety: if hint contains the answer, return generic fallback
            if correct_answer.lower()[:8] in hint.lower():
                logger.warning("hint_contained_answer", extra={
                    "question": question_text[:50],
                    "answer_prefix": correct_answer[:8],
                })
                return "Think about the broader historical and geographical context of this topic."
            logger.info("hint_generated", extra={
                "question": question_text[:50],
                "hint_length": len(hint),
            })
            return hint
        except Exception as e:
            logger.error("hint_generation_failed", extra={"error": str(e)})
            return None

    async def simple_completion(self, prompt: str) -> str:
        resp = await self._chat_completion(
            system="Answer concisely.",
            user=prompt,
            temperature=0.1,
            max_tokens=100,
        )
        return resp or ""

    async def _chat_completion(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> Optional[str]:
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.95,
            "frequency_penalty": 0.4,   # Penalise repeated tokens → more variety
        }
        try:
            resp = await self._client.post(
                GROQ_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                logger.error(f"Groq API error {resp.status_code}: {resp.text[:200]}")
                return None
            return resp.json()["choices"][0]["message"]["content"]
        except (httpx.RequestError, KeyError) as e:
            logger.error(f"Groq request failed: {e}")
            return None

    @staticmethod
    def _parse_json_response(raw: str) -> Optional[dict]:
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        logger.warning(f"Could not parse LLM JSON: {raw[:200]}")
        return None

    async def close(self):
        await self._client.aclose()