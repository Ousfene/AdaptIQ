"""
pydantic_pvp.py — Request/Response schemas for PvP Room.

Covers all endpoints:
  - Join queue, check queue status
  - Match details, submit answer, end match
  - Rating/leaderboard queries
"""

from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/pvp/join-queue
# ═══════════════════════════════════════════════════════════════════════════

class JoinQueueRequest(BaseModel):
    """Request to join the PvP matchmaking queue."""
    user_id: str
    topic: str = "Mixed"


class JoinQueueResponse(BaseModel):
    """Response after joining the queue — includes queue entry ID."""
    queue_id: str
    status: str = "waiting"
    message: str = "Searching for an opponent..."


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/pvp/queue-status?user_id=...
# ═══════════════════════════════════════════════════════════════════════════

class QueueStatusResponse(BaseModel):
    """Poll response for queue status — either still waiting or matched."""
    status: str  # "waiting", "matched", "expired"
    match_id: Optional[str] = None
    opponent_username: Optional[str] = None
    topic: Optional[str] = None
    message: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/pvp/match/{match_id}
# ═══════════════════════════════════════════════════════════════════════════

class PvPQuestionOut(BaseModel):
    """Single question in a PvP match quiz."""
    id: str
    text: str
    options: List[str]
    index: int  # 0-based position in the quiz


class PvPMatchOut(BaseModel):
    """Full match details returned to the frontend."""
    match_id: str
    user1_id: str
    user2_id: str
    topic: str
    status: str
    total_questions: int
    questions: List[PvPQuestionOut]
    user1_score: int = 0
    user2_score: int = 0
    user1_finished: bool = False
    user2_finished: bool = False


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/pvp/match/{match_id}/answer
# ═══════════════════════════════════════════════════════════════════════════

class PvPSubmitAnswerRequest(BaseModel):
    """Submit an answer for a question in an active PvP match."""
    user_id: str
    question_id: str
    question_index: int = Field(ge=0)
    answer: str
    time_taken: Optional[float] = None


class PvPSubmitAnswerResponse(BaseModel):
    """Response after submitting an answer — includes correctness and scores."""
    is_correct: bool
    correct_answer: str
    explanation: str = ""
    your_score: int
    opponent_score: int
    questions_answered: int
    match_finished: bool = False
    next_question: Optional[PvPQuestionOut] = None


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/pvp/match/{match_id}/end
# ═══════════════════════════════════════════════════════════════════════════

class PvPEndMatchResponse(BaseModel):
    """Match results after both players finish or timer expires."""
    match_id: str
    winner_id: Optional[str] = None
    result: str  # "win", "loss", "draw"
    your_score: int
    opponent_score: int
    elo_change: float
    new_elo: float
    opponent_username: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/pvp/user/{user_id}/rating
# ═══════════════════════════════════════════════════════════════════════════

class PvPRatingOut(BaseModel):
    """User's PvP rating and match history stats."""
    user_id: str
    elo_rating: float
    total_matches: int
    total_wins: int
    total_losses: int
    total_draws: int
    win_streak: int
    best_streak: int
    win_rate: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/pvp/leaderboard
# ═══════════════════════════════════════════════════════════════════════════

class LeaderboardEntry(BaseModel):
    """Single entry in the PvP leaderboard."""
    rank: int
    user_id: str
    username: str
    elo_rating: float
    total_wins: int
    total_matches: int
    win_rate: float


class LeaderboardResponse(BaseModel):
    """Paginated leaderboard response."""
    entries: List[LeaderboardEntry]
    total_players: int


# ═══════════════════════════════════════════════════════════════════════════
# DELETE /api/pvp/leave-queue
# ═══════════════════════════════════════════════════════════════════════════

class LeaveQueueRequest(BaseModel):
    """Request to leave the matchmaking queue."""
    user_id: str


class LeaveQueueResponse(BaseModel):
    """Confirmation of leaving the queue."""
    success: bool
    message: str = "Left the queue"
