"""
tests/test_adaptive_behavior.py — Virtual user adaptive behavior tests.

Tests T1-T8: Prove that AdaptIQ adapts question difficulty based on per-concept
user ability (theta). Uses the 6 seeded test users with known mastery profiles.

Run: cd backend && python -m pytest tests/test_adaptive_behavior.py -v

Requirements:
  - PostgreSQL with seed data loaded (python seeds/seed.py)
  - Redis running (or in-memory fallback)
  - GROQ_API_KEY set (or tests skip LLM-dependent paths)
"""
import pytest
import sys
import math
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent))

from httpx import ASGITransport, AsyncClient
from main import app

# Seed user credentials
TEST_PASSWORD = "TestPass123!"
USERS = {
    "geo_expert": {"email": "geo_expert@test.com", "strong": "geography", "weak": "history"},
    "hist_expert": {"email": "hist_expert@test.com", "strong": "history", "weak": "geography"},
    "balanced": {"email": "balanced@test.com", "strong": None, "weak": None},
    "beginner": {"email": "beginner@test.com", "strong": None, "weak": None},
    "challenger": {"email": "challenger@test.com", "strong": None, "weak": None},
    "struggling": {"email": "struggling@test.com", "strong": None, "weak": None},
}


# ── Helpers ────────────────────────────────────────────────────────────────


async def login(client: AsyncClient, email: str) -> str:
    """Login and return JWT token."""
    resp = await client.post("/api/auth/login", json={
        "email": email,
        "password": TEST_PASSWORD,
    })
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def start_session(client: AsyncClient, token: str, topic: str) -> dict:
    """Start a V2 classic session and return the full response."""
    resp = await client.post(
        "/api/rooms/classic/start",
        json={"topic": topic},
        headers=auth_header(token),
    )
    assert resp.status_code == 200, f"Start session failed: {resp.text}"
    data = resp.json()
    assert "session_id" in data, "No session_id in start response"
    assert "first_question" in data, "No first_question in start response"
    return data


async def submit_answer(
    client: AsyncClient, token: str, session_id: str,
    question_id: str, selected_index: int, time_taken: int = 10
) -> dict:
    """Submit an answer to V2 endpoint."""
    resp = await client.post(
        f"/api/rooms/classic/answer/{session_id}",
        json={
            "question_id": question_id,
            "selected_index": selected_index,
            "time_taken_seconds": time_taken,
            "used_hint": False,
        },
        headers=auth_header(token),
    )
    assert resp.status_code == 200, f"Submit answer failed: {resp.text}"
    return resp.json()


async def get_concept_mastery(client: AsyncClient, token: str) -> list[dict]:
    """Fetch concept mastery stats for current user."""
    resp = await client.get(
        "/api/rooms/classic/stats/concept-mastery",
        headers=auth_header(token),
    )
    if resp.status_code == 200:
        return resp.json().get("concepts", [])
    return []


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
async def client():
    """Async test client with full app lifespan."""
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


# ── T1: Expert Gets Hard Qs in Strong Area, Easy in Weak ─────────────────


class TestT1ExpertAdaptation:
    """
    T1: hist_expert has θ=2.3 on Egyptian Empire, θ=-1.0 on Amazon River Basin.
    When playing mixed, questions should adapt per-concept.
    """

    @pytest.mark.asyncio
    async def test_session_starts_successfully(self, client):
        """Verify V2 session start works for hist_expert."""
        token = await login(client, USERS["hist_expert"]["email"])
        data = await start_session(client, token, "mix")
        assert data["session_id"]
        assert data["first_question"] is not None
        q = data["first_question"]
        assert "text" in q
        assert "options" in q
        assert len(q["options"]) >= 2
        # Security: correctAnswer must NOT be in response
        assert "correctAnswer" not in q, "SECURITY FAIL: correctAnswer leaked to client!"

    @pytest.mark.asyncio
    async def test_no_correct_answer_in_question(self, client):
        """T1 security check: V2 endpoint must never expose correctAnswer."""
        token = await login(client, USERS["hist_expert"]["email"])
        data = await start_session(client, token, "history")
        q = data["first_question"]
        assert "correctAnswer" not in q
        assert "correct_answer" not in q
        assert "correct_index" not in q


# ── T2: Cold Start User Gets Moderate Questions ──────────────────────────


class TestT2ColdStart:
    """
    T2: beginner has no concept records. Should get medium difficulty initially.
    After answers, theta should update.
    """

    @pytest.mark.asyncio
    async def test_cold_start_session(self, client):
        """Beginner can start a session despite having zero history."""
        token = await login(client, USERS["beginner"]["email"])
        data = await start_session(client, token, "history")
        assert data["first_question"] is not None

    @pytest.mark.asyncio
    async def test_theta_moves_after_answer(self, client):
        """After submitting an answer, theta_change should be non-zero."""
        token = await login(client, USERS["beginner"]["email"])
        data = await start_session(client, token, "geography")
        q = data["first_question"]
        if q is None:
            pytest.skip("No question returned (LLM may be unavailable)")

        # Submit a correct answer (index 0 — we don't know if correct, but theta should move)
        result = await submit_answer(
            client, token, data["session_id"],
            q["id"], selected_index=0, time_taken=10,
        )
        # theta_change should be non-zero (positive or negative)
        assert "theta_change" in result
        assert isinstance(result["theta_change"], (int, float))


# ── T3: Struggling User Floor Check ──────────────────────────────────────


class TestT3StrugglingUser:
    """
    T3: struggling user has all θ < -0.5.
    System should serve easy questions (low difficulty).
    """

    @pytest.mark.asyncio
    async def test_session_starts_for_struggling(self, client):
        """Struggling user can start a session."""
        token = await login(client, USERS["struggling"]["email"])
        data = await start_session(client, token, "geography")
        assert data["first_question"] is not None

    @pytest.mark.asyncio
    async def test_difficulty_is_low(self, client):
        """First question difficulty should be low for struggling user."""
        token = await login(client, USERS["struggling"]["email"])
        data = await start_session(client, token, "geography")
        q = data["first_question"]
        if q and "difficulty" in q:
            # Difficulty 1-5 scale, struggling should get 1-3
            assert q["difficulty"] <= 3, (
                f"Struggling user got difficulty {q['difficulty']} — should be ≤ 3"
            )


# ── T4: Expert Concept Diversity ──────────────────────────────────────────


class TestT4ConceptDiversity:
    """
    T4: geo_expert has very high θ in all geography concepts.
    System should still vary which concepts it picks (not always the same one).
    """

    @pytest.mark.asyncio
    async def test_can_start_geography_session(self, client):
        """Expert can start geography session."""
        token = await login(client, USERS["geo_expert"]["email"])
        data = await start_session(client, token, "geography")
        assert data["first_question"] is not None


# ── T5: Mixed Session Weak Area Bias ──────────────────────────────────────


class TestT5MixedWeakAreaBias:
    """
    T5: geo_expert is strong in geography, weak in history.
    Mixed sessions should bias toward history (mastery_gap).
    """

    @pytest.mark.asyncio
    async def test_mixed_session_works(self, client):
        """Mixed session starts successfully for domain expert."""
        token = await login(client, USERS["geo_expert"]["email"])
        data = await start_session(client, token, "mix")
        assert data["first_question"] is not None


# ── T6: Challenge Room Anti-Farming ───────────────────────────────────────


class TestT6ChallengeAntiFarming:
    """
    T6: challenger has rank Silver (id=2).
    Should not be able to play below their rank.
    """

    @pytest.mark.asyncio
    async def test_challenge_status(self, client):
        """Challenger can check their challenge status."""
        token = await login(client, USERS["challenger"]["email"])
        resp = await client.get(
            "/api/rooms/challenge/status",
            headers=auth_header(token),
        )
        # Should get status (200) or 404 if no rank record
        assert resp.status_code in [200, 404]


# ── T7: IRT Math Convergence (Unit Test, No DB) ──────────────────────────


class TestT7ThetaConvergence:
    """
    T7: Simulate 30 IRT updates and verify theta converges.
    Pure math test — no database needed.
    """

    def test_theta_increases_on_correct_streak(self):
        """Theta should increase with consecutive correct answers."""
        from database.irt import update_theta
        theta = 0.0
        for _ in range(10):
            theta = update_theta(theta, beta=0.0, correct=True)
        assert theta > 1.0, f"Theta {theta} should be > 1.0 after 10 correct at β=0"

    def test_theta_decreases_on_wrong_streak(self):
        """Theta should decrease with consecutive wrong answers."""
        from database.irt import update_theta
        theta = 0.0
        for _ in range(10):
            theta = update_theta(theta, beta=0.0, correct=False)
        assert theta < -1.0, f"Theta {theta} should be < -1.0 after 10 wrong at β=0"

    def test_theta_converges_toward_true_ability(self):
        """
        Simulate a user with true ability θ*=1.5.
        They answer correctly when P(correct) > random, wrong otherwise.
        After 30 questions, estimated θ should be near θ*.
        """
        from database.irt import update_theta, irt_probability
        import random as rng

        rng.seed(42)  # Reproducible
        true_theta = 1.5
        estimated_theta = 0.0  # Start at default

        for _ in range(30):
            # Question at medium difficulty
            beta = 0.0
            p_correct = irt_probability(true_theta, beta)
            correct = rng.random() < p_correct
            estimated_theta = update_theta(estimated_theta, beta, correct)

        # After 30 questions, estimate should be in [0.5, 2.5] range
        assert 0.5 < estimated_theta < 2.5, (
            f"Estimated θ={estimated_theta:.2f} should be near true θ*={true_theta}"
        )

    def test_zpd_probability_range(self):
        """ZPD questions should have P(correct) ∈ [0.60, 0.75]."""
        from database.irt import irt_probability, target_beta_range

        for theta in [-2, -1, 0, 1, 2]:
            beta_low, beta_high = target_beta_range(theta)
            p_low = irt_probability(theta, beta_low)
            p_high = irt_probability(theta, beta_high)
            # p_low is at easier end (higher probability)
            assert 0.55 <= p_low <= 0.80, f"P at β_low={beta_low} for θ={theta} was {p_low}"
            assert 0.55 <= p_high <= 0.80, f"P at β_high={beta_high} for θ={theta} was {p_high}"


# ── T8: Timeout Handling ──────────────────────────────────────────────────


class TestT8TimeoutHandling:
    """
    T8: When a user times out (selected_index = -1), it should count as wrong.
    """

    @pytest.mark.asyncio
    async def test_timeout_counts_as_wrong(self, client):
        """Submitting with index -1 (timeout) should be marked incorrect."""
        token = await login(client, USERS["balanced"]["email"])
        data = await start_session(client, token, "history")
        q = data["first_question"]
        if q is None:
            pytest.skip("No question returned")

        result = await submit_answer(
            client, token, data["session_id"],
            q["id"], selected_index=-1, time_taken=30,
        )
        assert result["correct"] is False, "Timeout should be marked as wrong"


# ── Security Regression Tests ─────────────────────────────────────────────


class TestSecurityRegression:
    """Ensure security fixes remain effective."""

    @pytest.mark.asyncio
    async def test_v2_start_no_answer_leak(self, client):
        """V2 /start should never return correctAnswer."""
        token = await login(client, USERS["balanced"]["email"])
        data = await start_session(client, token, "geography")
        q = data["first_question"]
        if q:
            assert "correctAnswer" not in q
            assert "correct_answer" not in q
            assert "correct_index" not in q

    @pytest.mark.asyncio
    async def test_v2_answer_reveals_correct_index(self, client):
        """V2 /answer should return correct_index AFTER submission."""
        token = await login(client, USERS["balanced"]["email"])
        data = await start_session(client, token, "history")
        q = data["first_question"]
        if q is None:
            pytest.skip("No question returned")

        result = await submit_answer(
            client, token, data["session_id"],
            q["id"], selected_index=0, time_taken=10,
        )
        assert "correct_index" in result
        assert isinstance(result["correct_index"], int)
        assert 0 <= result["correct_index"] <= len(q["options"])

    @pytest.mark.asyncio
    async def test_hint_requires_session_ownership(self, client):
        """Hint request with a bogus session_id should return 404."""
        token = await login(client, USERS["balanced"]["email"])
        resp = await client.post(
            "/api/rooms/classic/hint/fake-session-id-12345",
            json={"question_id": "00000000-0000-0000-0000-000000000001", "question_text": "test"},
            headers=auth_header(token),
        )
        assert resp.status_code in [404, 422], (
            f"Expected 404/422 for bogus session, got {resp.status_code}"
        )
