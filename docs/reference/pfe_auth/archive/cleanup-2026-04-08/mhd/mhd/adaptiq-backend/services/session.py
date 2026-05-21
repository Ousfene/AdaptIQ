"""
services/session.py — Redis-backed session management.

Stores per-session state:
  - current_difficulty (int 1-5, updated after each answer)
  - theta (float, IRT user ability estimate)
  - seen_question_ids (set, for deduplication)
  - session metadata (topic, start_time, score, etc.)

Falls back to in-memory dict if Redis is unavailable (dev mode).
"""

from __future__ import annotations
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── In-memory fallback (dev/test without Redis) ───────────────────────────
_memory_store: dict[str, str] = {}


class SessionService:
    """
    Manages quiz session data in Redis (or in-memory fallback).
    Keys are namespaced as: session:{session_id}
    """

    def __init__(self, redis=None):
        """
        redis: aioredis.Redis instance or None (falls back to in-memory).
        """
        self._redis = redis
        self._ttl = 3600  # 1 hour TTL per session

    async def get_session(self, session_id: str) -> Optional[dict]:
        key = f"session:{session_id}"
        try:
            if self._redis:
                raw = await self._redis.get(key)
            else:
                raw = _memory_store.get(key)

            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Session get failed: {e}")
            return None

    async def set_session(self, session_id: str, data: dict) -> bool:
        key = f"session:{session_id}"
        try:
            serialized = json.dumps(data)
            if self._redis:
                await self._redis.setex(key, self._ttl, serialized)
            else:
                _memory_store[key] = serialized
            return True
        except Exception as e:
            logger.warning(f"Session set failed: {e}")
            return False

    async def update_session(self, session_id: str, updates: dict) -> bool:
        """Merge updates into existing session data."""
        data = await self.get_session(session_id) or {}
        data.update(updates)
        return await self.set_session(session_id, data)

    async def get_difficulty(self, session_id: str) -> int:
        data = await self.get_session(session_id)
        if data is None:
            return 2  # React starts at difficulty=2
        return data.get("current_difficulty", 2)

    async def update_difficulty(self, session_id: str, new_difficulty: int) -> None:
        await self.update_session(session_id, {"current_difficulty": new_difficulty})

    async def get_theta(self, session_id: str) -> float:
        data = await self.get_session(session_id)
        if data is None:
            return 0.0
        return data.get("theta", 0.0)

    async def update_theta(self, session_id: str, theta: float) -> None:
        await self.update_session(session_id, {"theta": theta})

    async def get_seen_ids(self, session_id: str) -> set[str]:
        data = await self.get_session(session_id)
        if data is None:
            return set()
        return set(data.get("seen_question_ids", []))

    async def add_seen_id(self, session_id: str, question_id: str) -> None:
        seen = await self.get_seen_ids(session_id)
        seen.add(question_id)
        await self.update_session(
            session_id, {"seen_question_ids": list(seen)}
        )

    async def initialize_session(
        self,
        session_id: str,
        user_id: str,
        topic: str,
        difficulty: int = 2,
    ) -> None:
        """Create a fresh session record."""
        import time
        await self.set_session(session_id, {
            "session_id":        session_id,
            "user_id":           user_id,
            "topic":             topic,
            "current_difficulty": difficulty,
            "theta":             0.0,
            "seen_question_ids": [],
            "question_count":    0,
            "score":             0,
            "start_time":        int(time.time() * 1000),  # ms epoch (matches React)
        })

    async def increment_question_count(self, session_id: str) -> int:
        data = await self.get_session(session_id) or {}
        count = data.get("question_count", 0) + 1
        await self.update_session(session_id, {"question_count": count})
        return count

    async def delete_session(self, session_id: str) -> None:
        key = f"session:{session_id}"
        try:
            if self._redis:
                await self._redis.delete(key)
            else:
                _memory_store.pop(key, None)
        except Exception as e:
            logger.warning(f"Session delete failed: {e}")
