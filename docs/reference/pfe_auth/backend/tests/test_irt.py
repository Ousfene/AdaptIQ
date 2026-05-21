"""
tests/test_irt.py — Unit tests for IRT functions.

Tests:
- p_correct returns 0.5 when theta == beta
- update_theta increases theta on correct answer
- update_theta decreases theta on wrong answer
- theta is clamped to [-3, 3]
- target_beta_range returns values where P(correct) ∈ [0.60, 0.75]
"""
import pytest
import math
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.irt import (
    irt_probability,
    update_theta,
    update_beta,
    target_beta_range,
    beta_to_difficulty,
    difficulty_to_beta,
    THETA_RANGE,
    BETA_RANGE,
    ZPD_P_LOW,
    ZPD_P_HIGH,
)


class TestIrtProbability:
    """Test irt_probability function."""

    def test_p_correct_equals_half_when_theta_equals_beta(self):
        """P(correct) should be 0.5 when theta == beta."""
        assert irt_probability(0.0, 0.0) == pytest.approx(0.5)
        assert irt_probability(1.5, 1.5) == pytest.approx(0.5)
        assert irt_probability(-2.0, -2.0) == pytest.approx(0.5)

    def test_p_correct_higher_when_theta_greater_than_beta(self):
        """P(correct) should be > 0.5 when theta > beta (easier question)."""
        p = irt_probability(2.0, 0.0)
        assert p > 0.5
        assert p == pytest.approx(0.88, abs=0.01)

    def test_p_correct_lower_when_theta_less_than_beta(self):
        """P(correct) should be < 0.5 when theta < beta (harder question)."""
        p = irt_probability(0.0, 2.0)
        assert p < 0.5
        assert p == pytest.approx(0.12, abs=0.01)

    def test_p_correct_range(self):
        """P(correct) should always be in (0, 1)."""
        for theta in [-3, -1, 0, 1, 3]:
            for beta in [-3, -1, 0, 1, 3]:
                p = irt_probability(theta, beta)
                assert 0 < p < 1


class TestUpdateTheta:
    """Test update_theta function."""

    def test_theta_increases_on_correct_answer(self):
        """Theta should increase when answer is correct."""
        old_theta = 0.0
        new_theta = update_theta(old_theta, beta=0.0, correct=True)
        assert new_theta > old_theta

    def test_theta_decreases_on_wrong_answer(self):
        """Theta should decrease when answer is wrong."""
        old_theta = 0.0
        new_theta = update_theta(old_theta, beta=0.0, correct=False)
        assert new_theta < old_theta

    def test_theta_clamped_at_upper_bound(self):
        """Theta should not exceed THETA_RANGE[1]."""
        theta = THETA_RANGE[1]  # Already at max
        new_theta = update_theta(theta, beta=-3.0, correct=True)
        assert new_theta <= THETA_RANGE[1]

    def test_theta_clamped_at_lower_bound(self):
        """Theta should not go below THETA_RANGE[0]."""
        theta = THETA_RANGE[0]  # Already at min
        new_theta = update_theta(theta, beta=3.0, correct=False)
        assert new_theta >= THETA_RANGE[0]

    def test_update_magnitude_depends_on_surprise(self):
        """
        Update should be larger when outcome is surprising.
        Easy question (low beta) answered wrong = big decrease.
        Hard question (high beta) answered correct = big increase.
        """
        # Easy question answered wrong (surprising)
        theta1 = update_theta(0.0, beta=-2.0, correct=False)
        # Hard question answered wrong (expected)
        theta2 = update_theta(0.0, beta=2.0, correct=False)
        # Surprising outcome should cause bigger change
        assert abs(theta1 - 0.0) > abs(theta2 - 0.0)


class TestUpdateBeta:
    """Test update_beta function."""

    def test_beta_decreases_on_correct_answer(self):
        """Beta should decrease when question is answered correctly (question is easier than thought)."""
        old_beta = 0.0
        new_beta = update_beta(old_beta, theta=0.0, correct=True)
        assert new_beta < old_beta

    def test_beta_increases_on_wrong_answer(self):
        """Beta should increase when question is answered wrong (question is harder than thought)."""
        old_beta = 0.0
        new_beta = update_beta(old_beta, theta=0.0, correct=False)
        assert new_beta > old_beta

    def test_beta_clamped_at_upper_bound(self):
        """Beta should not exceed BETA_RANGE[1]."""
        beta = BETA_RANGE[1]
        new_beta = update_beta(beta, theta=-3.0, correct=False)
        assert new_beta <= BETA_RANGE[1]

    def test_beta_clamped_at_lower_bound(self):
        """Beta should not go below BETA_RANGE[0]."""
        beta = BETA_RANGE[0]
        new_beta = update_beta(beta, theta=3.0, correct=True)
        assert new_beta >= BETA_RANGE[0]


class TestTargetBetaRange:
    """Test target_beta_range function (ZPD calculation)."""

    def test_beta_range_gives_zpd_probability(self):
        """
        Questions with beta in the returned range should have
        P(correct) between 0.60 and 0.75 (ZPD).
        """
        for theta in [-2, -1, 0, 1, 2]:
            beta_low, beta_high = target_beta_range(theta)
            
            # P(correct) at beta_low should be ~0.75 (easier end of ZPD)
            p_low = irt_probability(theta, beta_low)
            assert p_low == pytest.approx(ZPD_P_HIGH, abs=0.02)
            
            # P(correct) at beta_high should be ~0.60 (harder end of ZPD)
            p_high = irt_probability(theta, beta_high)
            assert p_high == pytest.approx(ZPD_P_LOW, abs=0.02)

    def test_beta_range_ordering(self):
        """beta_low should be less than beta_high."""
        for theta in [-2, 0, 2]:
            beta_low, beta_high = target_beta_range(theta)
            assert beta_low < beta_high

    def test_beta_range_clamped(self):
        """Beta range values should be clamped to BETA_RANGE."""
        # Extreme theta values
        beta_low, beta_high = target_beta_range(-3.0)
        assert beta_low >= BETA_RANGE[0]
        assert beta_high <= BETA_RANGE[1]

        beta_low, beta_high = target_beta_range(3.0)
        assert beta_low >= BETA_RANGE[0]
        assert beta_high <= BETA_RANGE[1]


class TestDifficultyConversion:
    """Test beta_to_difficulty and difficulty_to_beta conversions."""

    def test_beta_to_difficulty_mapping(self):
        """Test that beta values map to correct difficulty levels."""
        assert beta_to_difficulty(-2.5) == 1
        assert beta_to_difficulty(-1.0) == 2
        assert beta_to_difficulty(0.0) == 3
        assert beta_to_difficulty(1.0) == 4
        assert beta_to_difficulty(2.0) == 5

    def test_difficulty_to_beta_mapping(self):
        """Test that difficulty levels map to expected beta values."""
        assert difficulty_to_beta(1) == -2.0
        assert difficulty_to_beta(2) == -1.0
        assert difficulty_to_beta(3) == 0.0
        assert difficulty_to_beta(4) == 1.0
        assert difficulty_to_beta(5) == 2.0

    def test_roundtrip_conversion(self):
        """Converting difficulty → beta → difficulty should be close to original."""
        for diff in [1, 2, 3, 4, 5]:
            beta = difficulty_to_beta(diff)
            # Note: Not exact roundtrip due to breakpoints
            recovered = beta_to_difficulty(beta)
            assert abs(recovered - diff) <= 1
