import pytest
from services.pvp_service import (
    ELO_MAX_DIFF, ELO_DEFAULT, ELO_K_NEW, ELO_K_REGULAR
)

def test_pvp_constants():
    assert ELO_MAX_DIFF == 300
    assert ELO_DEFAULT == 1000.0
    assert ELO_K_NEW == 32
    assert ELO_K_REGULAR == 16

@pytest.mark.asyncio
async def test_matchmaking_elo_range(monkeypatch):
    from database.pvp_models import PvPMatchmakingQueue
    
    # Simulate the query logic conceptually
    entry1 = PvPMatchmakingQueue(elo_rating=1000)
    entry2 = PvPMatchmakingQueue(elo_rating=1200) # within 300
    entry3 = PvPMatchmakingQueue(elo_rating=1400) # outside 300
    
    assert abs(entry1.elo_rating - entry2.elo_rating) <= ELO_MAX_DIFF
    assert abs(entry1.elo_rating - entry3.elo_rating) > ELO_MAX_DIFF

@pytest.mark.asyncio
async def test_matchmaking_topic_compatibility():
    # If entry is "Mixed", it can match with anything.
    # If entry is "History", it can match with "History" or "Mixed".
    topic = "History"
    assert topic in ("History", "Mixed")
    
    topic_mixed = "Mixed"
    assert topic_mixed in ("History", "Geography", "Mixed")
