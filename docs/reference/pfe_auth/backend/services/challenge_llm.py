"""
services/challenge_llm.py — Level-specific LLM prompts for Challenge Room.

Ported from MHD version with level-based question generation:
- Level 1: 2 options (easy entry)
- Level 2-4: 4 options with varying plausibility
- Level 5: Free-text (future implementation)
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from typing import Optional, Any

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════
# LEVEL-SPECIFIC PROMPT CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════

LEVEL_PROMPTS = {
    1: {
        "description": "VERY EASY — well-known fact. Famous capitals, major battles, common dates.",
        "options_rule": "Return ONLY 2 options: 'correct' and 'wrong1'. Leave 'wrong2' and 'wrong3' as empty strings.",
        "options_count": 2,
        "is_free_text": False,
    },
    2: {
        "description": "EASY — straightforward fact. The 2 wrong answers must be obviously incorrect (different category, wrong continent, wrong century).",
        "options_rule": "Return 4 options. 'wrong1' and 'wrong2' must be obviously wrong. 'wrong3' should be slightly plausible.",
        "options_count": 4,
        "is_free_text": False,
    },
    3: {
        "description": "MEDIUM — requires connecting two facts. The question itself should be harder than level 2.",
        "options_rule": "Return 4 options. 2 of the wrong answers must be plausible (same category, same region, similar era). 1 wrong answer can be obvious.",
        "options_count": 4,
        "is_free_text": False,
    },
    4: {
        "description": "HARD — multi-hop reasoning, lesser-known facts. Expert level.",
        "options_rule": "Return 4 options. ALL 4 options must be plausible and from the same category. The user should genuinely be unsure.",
        "options_count": 4,
        "is_free_text": False,
    },
    5: {
        "description": "VERY HARD — obscure expert knowledge. Pre-medieval events, minor capitals, rare treaties.",
        "options_rule": "This is a FREE TEXT question. Do NOT generate options. Set 'wrong1', 'wrong2', 'wrong3' all to empty strings. The user will type their answer.",
        "options_count": 0,
        "is_free_text": True,
    },
}

# System prompt for the challenge LLM — stricter than ClassicRoom
CHALLENGE_SYSTEM_PROMPT = """You are an expert educational MCQ generator for a competitive quiz platform.
Return ONLY a valid JSON object — no markdown, no backticks, no extra text.

STRICT JSON structure:
{
  "text": "the question",
  "correct": "the single correct answer",
  "wrong1": "wrong answer or empty string",
  "wrong2": "wrong answer or empty string",
  "wrong3": "wrong answer or empty string",
  "explanation": "1-2 sentences with an interesting fact or context — NOT just restating the answer"
}

RULES:
- Follow the options_rule exactly for this level
- The explanation must be genuinely interesting — a fun fact, historical context, or surprising detail
- Return ONLY the JSON, nothing else"""


def get_level_config(level: int) -> dict:
    """Get configuration for a specific level."""
    return LEVEL_PROMPTS.get(level, LEVEL_PROMPTS[3])  # Default to medium


def build_options_from_response(
    parsed: dict,
    level: int,
) -> tuple[list[str], str, bool]:
    """
    Build options list from LLM response based on level configuration.
    
    Returns (options, correct_answer, is_free_text).
    """
    cfg = LEVEL_PROMPTS.get(level, LEVEL_PROMPTS[3])
    correct = str(parsed["correct"]).strip()
    
    if cfg["is_free_text"]:
        # Level 5: no options, free text input
        return [], correct, True
    
    if cfg["options_count"] == 2:
        # Level 1: only 2 options
        wrong1 = str(parsed.get("wrong1", "")).strip()
        if not wrong1:
            wrong1 = "None of the above"
        options = [correct, wrong1]
        random.shuffle(options)
        return options, correct, False
    
    # Levels 2, 3, 4: 4 options
    wrongs = [
        str(parsed.get("wrong1", "")).strip(),
        str(parsed.get("wrong2", "")).strip(),
        str(parsed.get("wrong3", "")).strip(),
    ]
    # Filter out empty strings
    wrongs = [w for w in wrongs if w]
    
    # Pad if LLM returned fewer than 3 wrongs
    pads = ["None of the above", "Cannot be determined", "All of the above"]
    while len(wrongs) < 3:
        wrongs.append(pads.pop(0))
    
    options = [correct] + wrongs[:3]
    
    # Remove duplicates
    seen = set()
    unique = []
    for o in options:
        if o.lower() not in seen:
            seen.add(o.lower())
            unique.append(o)
    
    while len(unique) < 4:
        unique.append(pads.pop(0) if pads else "Unknown")
    
    options = unique[:4]
    random.shuffle(options)
    
    return options, correct, False


async def generate_challenge_question(
    llm: Any,
    topic: str,
    level: int,
    context: str = "",
) -> Optional[dict]:
    """
    Generate a challenge question using level-specific prompts.
    
    Args:
        llm: LLMClient instance with _chat_completion method
        topic: Question topic (History, Geography, etc.)
        level: Difficulty level 1-5
        context: Optional context from RAG pipeline
    
    Returns:
        Question dict with id, text, options, correctAnswer, explanation, is_free_text
        or None on failure.
    """
    cfg = LEVEL_PROMPTS.get(level, LEVEL_PROMPTS[3])
    
    user_prompt = f"""TOPIC: {topic}
LEVEL: {level}/5 — {cfg['description']}
OPTIONS RULE: {cfg['options_rule']}

{"CONTEXT (base your question on this):" + chr(10) + context[:600] if context else "Generate a unique question about " + topic + "."}

Generate ONE unique question following the level and options rule exactly.
Return ONLY the JSON."""

    try:
        response = await llm._chat_completion(
            system=CHALLENGE_SYSTEM_PROMPT,
            user=user_prompt,
            temperature=0.92,
            max_tokens=400,
        )
        if not response:
            logger.warning(f"Empty LLM response for level {level}")
            return None

        parsed = llm._parse_json_response(response)
        if not parsed:
            logger.warning(f"Failed to parse LLM response for level {level}")
            return None

        if not parsed.get("text") or not parsed.get("correct"):
            logger.warning(f"Missing required fields in LLM response for level {level}")
            return None

        options, correct, is_free_text = build_options_from_response(parsed, level)

        return {
            "id": str(uuid.uuid4()),
            "text": str(parsed["text"]).strip(),
            "options": options,
            "correctAnswer": correct,
            "explanation": str(parsed.get("explanation", "")).strip(),
            "is_free_text": is_free_text,
            "level": level,
        }

    except Exception as e:
        logger.error(f"Challenge LLM generation failed at level {level}: {e}")
        return None


async def generate_challenge_question_with_fallback(
    llm: Any,
    topic: str,
    level: int,
    context: str = "",
    max_retries: int = 2,
) -> Optional[dict]:
    """
    Generate a challenge question with retry logic.
    
    Falls back to lower levels if the target level fails.
    """
    # Try target level first
    for attempt in range(max_retries):
        question = await generate_challenge_question(llm, topic, level, context)
        if question:
            return question
        logger.info(f"Retry {attempt + 1}/{max_retries} for level {level}")
    
    # Fallback to simpler level
    if level > 1:
        logger.info(f"Falling back from level {level} to level {level - 1}")
        return await generate_challenge_question(llm, topic, level - 1, context)
    
    return None


def validate_answer_free_text(
    user_answer: str,
    correct_answer: str,
    llm: Any = None,
) -> bool:
    """
    Validate a free-text answer against the correct answer.
    
    For Level 5 questions. Uses fuzzy matching.
    Future: Could use LLM for semantic comparison.
    """
    # Normalize both answers
    user_norm = user_answer.strip().lower()
    correct_norm = correct_answer.strip().lower()
    
    # Exact match
    if user_norm == correct_norm:
        return True
    
    # Check if user answer contains correct answer or vice versa
    if user_norm in correct_norm or correct_norm in user_norm:
        return True
    
    # Simple Levenshtein-like check for typos
    # Allow up to 2 character difference for short answers
    if len(correct_norm) <= 10:
        diff_count = sum(1 for a, b in zip(user_norm, correct_norm) if a != b)
        diff_count += abs(len(user_norm) - len(correct_norm))
        if diff_count <= 2:
            return True
    
    return False
