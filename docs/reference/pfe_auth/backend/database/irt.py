"""
database/irt.py — Item Response Theory calibration.

1-Parameter Logistic (1PL) IRT model:
    P(correct | θ, β) = 1 / (1 + exp(-(θ - β)))

where:
    θ (theta) = estimated user ability
    β (beta)  = question difficulty parameter

After each answer we:
    1. Estimate updated θ from user's response history
    2. Update β for the question via MLE approximation
    3. Map θ → difficulty scale (1-5) for next question selection
"""

from __future__ import annotations
import math
import logging
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────
THETA_INIT  = 0.0    # initial user ability (mid-scale)
BETA_INIT   = 0.0    # initial question difficulty (mid-scale)
LEARN_RATE  = 0.3    # gradient step size for online updates
THETA_RANGE = (-3.0, 3.0)   # clamp user ability to ±3 SD
BETA_RANGE  = (-3.0, 3.0)   # clamp question difficulty to ±3 SD

# Map IRT β → integer difficulty 1-5 for the React UI
_BETA_BREAKPOINTS = [-1.5, -0.5, 0.5, 1.5]   # thresholds between levels

# Zone of Proximal Development: target P(correct) ∈ [0.60, 0.75]
# Solved: β_low = θ - ln(1/0.75 - 1) ≈ θ - 1.10
#         β_high = θ - ln(1/0.60 - 1) ≈ θ - 0.41
ZPD_P_LOW = 0.60
ZPD_P_HIGH = 0.75


def irt_probability(theta: float, beta: float) -> float:
    """P(correct) under 1PL IRT model."""
    return 1.0 / (1.0 + math.exp(-(theta - beta)))


def update_theta(theta: float, beta: float, correct: bool) -> float:
    """
    Online MLE update for user ability θ using gradient ascent on log-likelihood.

    ∂ logL/∂θ = (correct - P(correct)) * P(correct) * (1 - P(correct)) / P(correct)
              = correct - P(correct)   [simplified for 1PL]
    """
    p = irt_probability(theta, beta)
    gradient = (1 if correct else 0) - p
    new_theta = theta + LEARN_RATE * gradient
    new_theta = float(max(THETA_RANGE[0], min(THETA_RANGE[1], new_theta)))

    # Log the theta update for testing audit trail
    logger.debug(
        f"theta_update: old_theta={theta:.3f} new_theta={new_theta:.3f} "
        f"change={new_theta - theta:.3f} p_correct={p:.3f} "
        f"answered_correct={correct} gradient={gradient:.3f}"
    )

    return new_theta


def update_beta(beta: float, theta: float, correct: bool) -> float:
    """
    Online MLE update for question difficulty β.
    If user got it right, question might be easier than estimated → lower β slightly.
    If user got it wrong, question might be harder → raise β slightly.
    """
    p = irt_probability(theta, beta)
    # Negative gradient (we want to maximise LL w.r.t. β, and
    # ∂ logL/∂β = -(correct - P) so we move β in the direction that
    # makes the observed outcome more likely)
    gradient = -(1 if correct else 0) + p
    new_beta = beta + LEARN_RATE * 0.5 * gradient   # slower beta updates
    return float(max(BETA_RANGE[0], min(BETA_RANGE[1], new_beta)))


def beta_to_difficulty(beta: float) -> int:
    """Map continuous IRT β ∈ [-3, 3] → integer difficulty 1-5."""
    for i, threshold in enumerate(_BETA_BREAKPOINTS):
        if beta < threshold:
            return i + 1
    return 5


def difficulty_to_beta(difficulty: int) -> float:
    """Map integer difficulty 1-5 → IRT β centre point."""
    mapping = {1: -2.0, 2: -1.0, 3: 0.0, 4: 1.0, 5: 2.0}
    return mapping.get(difficulty, 0.0)


def target_beta_range(theta: float) -> tuple[float, float]:
    """
    Given current θ, return target β range for Zone of Proximal Development.

    ZPD: P(correct) ∈ [0.60, 0.75] — challenging but achievable.

    Solving P = 1/(1+exp(-(θ-β))) for β:
        1/P - 1 = exp(-(θ-β))
        ln(1/P - 1) = -(θ-β)
        β = θ + ln(1/P - 1)
    
    Or equivalently: β = θ - ln(P/(1-P))

    For P=0.75 (easier): β = θ + ln(0.333) ≈ θ - 1.10
    For P=0.60 (harder): β = θ + ln(0.667) ≈ θ - 0.41

    Returns (beta_low, beta_high) where questions in this range are ideal.
    """
    # For higher P (easier), we need lower beta
    beta_low = theta + math.log(1.0/ZPD_P_HIGH - 1)   # ≈ θ - 1.10
    # For lower P (harder), we need higher beta
    beta_high = theta + math.log(1.0/ZPD_P_LOW - 1)   # ≈ θ - 0.41
    
    # Clamp to valid beta range
    beta_low = max(BETA_RANGE[0], min(BETA_RANGE[1], beta_low))
    beta_high = max(BETA_RANGE[0], min(BETA_RANGE[1], beta_high))

    # ═══════ IRT-4 FIX: Ensure range is valid (low <= high) ═══════
    # After clamping, beta_low could be greater than beta_high if theta
    # is near the boundaries. Swap if inverted to ensure valid range.
    if beta_low > beta_high:
        beta_low, beta_high = beta_high, beta_low
    # ═════════════════════════════════════════════════════════════

    # Log ZPD range for testing
    logger.debug(
        f"zpd_range: user_theta={theta:.3f} beta_low={beta_low:.3f} "
        f"beta_high={beta_high:.3f} target_p={ZPD_P_LOW:.2f}-{ZPD_P_HIGH:.2f}"
    )

    return (beta_low, beta_high)


def next_difficulty(
    current_difficulty: int,
    answered_correct: bool,
    theta: float,
    recent_betas: list[float] | None = None,  # Reserved for future adaptive features
) -> int:
    """
    Choose next question difficulty using IRT-informed rule.
    
    - Uses θ to pick the difficulty level that maximises Fisher information:
      I(θ) = P(θ,β) * (1 - P(θ,β))  — maximised when P = 0.5, i.e. β ≈ θ
    - Clamps change to ±1 from current so difficulty ramps gradually
      (matching the React handleAnswer logic: min(prev+1,5) / max(prev-1,1))
    
    Args:
        current_difficulty: Current difficulty level (1-5)
        answered_correct: Whether the user answered correctly
        theta: User's current ability estimate
        recent_betas: Reserved for future use (e.g., avoiding repeated difficulty levels)
    """
    # NOTE: recent_betas is reserved for future adaptive logic such as:
    # - Avoiding repeated difficulty levels
    # - Detecting user frustration patterns
    # - Adaptive pacing based on recent performance
    _ = recent_betas  # Mark as intentionally unused for now
    
    # Ideal β = θ (zone of proximal development)
    ideal_beta = theta
    ideal_diff = beta_to_difficulty(ideal_beta)

    # Clamp to ±1 from current (matches React UI behaviour exactly)
    if answered_correct:
        candidate = min(current_difficulty + 1, 5)
    else:
        candidate = max(current_difficulty - 1, 1)

    # Blend: prefer IRT ideal but respect the ±1 clamp
    # If IRT agrees with the clamp, use it; otherwise prefer clamp
    if abs(ideal_diff - current_difficulty) <= 1:
        return ideal_diff
    return candidate


class UserAbilityTracker:
    """
    In-memory per-session θ tracker.
    Persisted to Redis as JSON for cross-request access.
    """

    def __init__(self, theta: float = THETA_INIT):
        self.theta = theta
        self.response_count = 0

    def record(self, beta: float, correct: bool) -> float:
        """Update θ and return new value."""
        self.theta = update_theta(self.theta, beta, correct)
        self.response_count += 1
        return self.theta

    def to_dict(self) -> dict:
        return {"theta": self.theta, "response_count": self.response_count}

    @classmethod
    def from_dict(cls, d: dict) -> "UserAbilityTracker":
        obj = cls(theta=d.get("theta", THETA_INIT))
        obj.response_count = d.get("response_count", 0)
        return obj


def estimate_theta_from_history(
    responses: list[dict],  # list of {difficulty_sent, answered_correct}
) -> float:
    """
    Batch MLE estimate of θ from a list of past responses.
    Used by the IRT recalibration cron job.
    """
    theta = THETA_INIT
    for resp in responses:
        beta = difficulty_to_beta(resp["difficulty_sent"])
        correct = resp["answered_correct"]
        theta = update_theta(theta, beta, correct)
    return theta
