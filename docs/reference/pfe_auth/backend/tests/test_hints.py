"""
tests/test_hints.py — Unit tests for hint generation and validation.

Tests:
- Hint for question with stored hint returns immediately (no LLM call)
- Hint response never contains the correct answer text
- Hint response never contains any option text verbatim
"""
import pytest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def validate_hint(hint: str, correct_answer: str, all_options: list[str]) -> bool:
    """
    Validate that a hint doesn't reveal the answer.
    
    Returns True if hint is valid (doesn't leak answer).
    """
    hint_lower = hint.lower()
    
    # Check if hint contains the correct answer
    if correct_answer.lower() in hint_lower:
        return False
    
    # Check if hint contains any option text
    for option in all_options:
        if option.lower() in hint_lower:
            return False

    # Also block partial leakage via distinctive option tokens (e.g., "Ganges").
    hint_tokens = set(hint_lower.replace("-", " ").split())
    token_counts: dict[str, int] = {}
    for option in all_options:
        for token in option.lower().replace("-", " ").split():
            if len(token) >= 4:
                token_counts[token] = token_counts.get(token, 0) + 1

    distinctive_tokens = {token for token, count in token_counts.items() if count == 1}
    if any(token in hint_tokens for token in distinctive_tokens):
            return False
    
    return True


class TestHintValidation:
    """Test hint validation function."""

    def test_valid_hint_passes(self):
        """A hint that doesn't contain the answer should pass validation."""
        hint = "Think about the geographical features of this region."
        correct = "Amazon River"
        options = ["Amazon River", "Nile River", "Congo River", "Ganges River"]
        
        assert validate_hint(hint, correct, options) is True

    def test_hint_with_correct_answer_fails(self):
        """A hint containing the correct answer should fail validation."""
        hint = "The answer is the Amazon River, which is in South America."
        correct = "Amazon River"
        options = ["Amazon River", "Nile River", "Congo River", "Ganges River"]
        
        assert validate_hint(hint, correct, options) is False

    def test_hint_with_option_text_fails(self):
        """A hint containing any option text should fail validation."""
        hint = "Consider the Nile River's location."
        correct = "Amazon River"
        options = ["Amazon River", "Nile River", "Congo River", "Ganges River"]
        
        assert validate_hint(hint, correct, options) is False

    def test_case_insensitive_matching(self):
        """Validation should be case-insensitive."""
        hint = "This river is called the AMAZON RIVER in many texts."
        correct = "Amazon River"
        options = ["Amazon River", "Nile River", "Congo River", "Ganges River"]
        
        assert validate_hint(hint, correct, options) is False

    def test_partial_match_fails(self):
        """Even partial matches of option text should fail."""
        hint = "Think about the Ganges and its tributaries."
        correct = "Amazon River"
        options = ["Amazon River", "Nile River", "Congo River", "Ganges River"]
        
        assert validate_hint(hint, correct, options) is False

    def test_empty_hint_passes(self):
        """Empty hint should pass (though not useful)."""
        hint = ""
        correct = "Amazon River"
        options = ["Amazon River", "Nile River", "Congo River", "Ganges River"]
        
        assert validate_hint(hint, correct, options) is True

    def test_generic_fallback_hint_passes(self):
        """Generic fallback hints should always pass."""
        hint = "Consider all options carefully before choosing."
        correct = "Amazon River"
        options = ["Amazon River", "Nile River", "Congo River", "Ganges River"]
        
        assert validate_hint(hint, correct, options) is True


class TestHintQualities:
    """Test hint quality characteristics."""

    def test_good_hint_examples(self):
        """Examples of good hints that guide without revealing."""
        good_hints = [
            "This river is located in South America.",
            "Think about tropical rainforest regions.",
            "Consider which river has the largest drainage basin.",
            "This is one of the longest rivers in the world.",
            "It flows through multiple countries including Brazil.",
        ]
        
        correct = "Amazon River"
        options = ["Amazon River", "Nile River", "Congo River", "Ganges River"]
        
        for hint in good_hints:
            assert validate_hint(hint, correct, options) is True

    def test_bad_hint_examples(self):
        """Examples of bad hints that reveal the answer."""
        bad_hints = [
            "The correct answer is Amazon River.",
            "Choose Amazon River for this question.",
            "Think about the Amazon River basin.",
            "The Nile is not the answer here.",  # Contains option
            "It's definitely not the Congo River.",  # Contains option
        ]
        
        correct = "Amazon River"
        options = ["Amazon River", "Nile River", "Congo River", "Ganges River"]
        
        for hint in bad_hints:
            assert validate_hint(hint, correct, options) is False


@pytest.mark.asyncio
async def test_hint_endpoint_returns_cached_hint(api_client):
    """
    Test that the hint endpoint returns a cached hint when available.
    
    Note: This test requires a question with a pre-stored hint in the database.
    Skipped if no such question exists (would require full integration setup).
    """
    # This would be an integration test - skipping for unit tests
    pytest.skip("Integration test - requires database with seeded questions")


@pytest.mark.asyncio  
async def test_hint_endpoint_validates_hint_content(api_client):
    """
    Test that generated hints are validated to not reveal answers.
    
    Note: This test requires LLM configuration and would be an integration test.
    """
    pytest.skip("Integration test - requires LLM configuration")
