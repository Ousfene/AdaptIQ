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
import asyncio
import json
import logging
from typing import Optional, Literal
from contextlib import asynccontextmanager
import hashlib

from config import (
    SESSION_TTL_SECONDS,
    IDEMPOTENCY_TTL_SECONDS,
    SESSION_LOCK_TTL_SECONDS,
    SESSION_LOCK_TIMEOUT_SECONDS,
)

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
        # ═══════ REDIS-1 FIX: Use config TTLs ═══════
        self._ttl = SESSION_TTL_SECONDS
        self._idempotency_ttl = IDEMPOTENCY_TTL_SECONDS
        self.LOCK_TTL = SESSION_LOCK_TTL_SECONDS

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

    # ── Idempotency & Submission State Machine ──────────────────────────────

    async def is_submission_duplicate(self, user_id: str, question_id: str, answer_hash: str) -> dict | None:
        """Check if this exact submission was already processed. Returns cached result or None."""
        idempotency_key = f"idempotency:{user_id}:{question_id}:{answer_hash}"
        try:
            if self._redis:
                raw = await self._redis.get(idempotency_key)
            else:
                raw = _memory_store.get(idempotency_key)

            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Idempotency check failed: {e}")
            return None

    async def record_submission(self, user_id: str, question_id: str, answer_hash: str, result: dict) -> bool:
        """Cache submission result for exact-once semantics."""
        idempotency_key = f"idempotency:{user_id}:{question_id}:{answer_hash}"
        try:
            serialized = json.dumps(result)
            if self._redis:
                await self._redis.setex(idempotency_key, self._idempotency_ttl, serialized)
            else:
                _memory_store[idempotency_key] = serialized
            return True
        except Exception as e:
            logger.warning(f"Idempotency recording failed: {e}")
            return False

    async def set_submission_state(self, session_id: str, state: str) -> bool:
        """Track session submission state machine (processing/ready)."""
        try:
            session_data = await self.get_session(session_id)
            if session_data is None:
                logger.warning(f"Cannot set submission state: session {session_id} not found")
                return False
            session_data["submission_state"] = state
            return await self.set_session(session_id, session_data)
        except Exception as e:
            logger.warning(f"Submission state update failed: {e}")
            return False

    async def get_submission_state(self, session_id: str) -> str:
        """Get current submission state (ready = can accept new answers, processing = locked)."""
        try:
            session_data = await self.get_session(session_id)
            if session_data is None:
                return "ready"  # Default: ready if session doesn't exist
            return session_data.get("submission_state", "ready")
        except Exception as e:
            logger.warning(f"Submission state retrieval failed: {e}")
            return "ready"  # Fail open: allow submission if state check fails

    # ── Generic Session State Storage (for Classic V2 and Challenge) ─────────

    async def store_session_state(self, key: str, data: dict) -> bool:
        """Store arbitrary session state with a custom key.

        Note: TTL is refreshed (reset) on each update, preventing mid-session expiry.
        """
        full_key = f"state:{key}"
        try:
            serialized = json.dumps(data)
            if self._redis:
                ttl_seconds = int(self._ttl)
                await self._redis.setex(full_key, ttl_seconds, serialized)
                logger.debug(f"Session state {full_key} stored with TTL {ttl_seconds}s (TTL refreshed on update)")
            else:
                _memory_store[full_key] = serialized
            return True
        except Exception as e:
            logger.warning(f"Session state store failed: {e}")
            return False

    async def get_session_state(self, key: str) -> Optional[dict]:
        """Retrieve arbitrary session state by key."""
        full_key = f"state:{key}"
        try:
            if self._redis:
                raw = await self._redis.get(full_key)
            else:
                raw = _memory_store.get(full_key)

            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Session state get failed: {e}")
            return None

    async def delete_session_state(self, key: str) -> None:
        """Delete session state by key."""
        full_key = f"state:{key}"
        try:
            if self._redis:
                await self._redis.delete(full_key)
            else:
                _memory_store.pop(full_key, None)
        except Exception as e:
            logger.warning(f"Session state delete failed: {e}")

    # ── Current Question Tracking (for answer verification fix) ──────────────────

    async def get_current_question(self, session_id: str) -> Optional[dict]:
        """
        Get current question with shuffled options for answer verification.
        Stores: id, correct_answer, shuffled_options, correct_index_shuffled
        """
        data = await self.get_session_state(f"current_question:{session_id}")
        return data

    async def set_current_question(self, session_id: str, question_data: dict) -> bool:
        """
        Store current question with shuffled options.
        question_data: {
            "id": str,
            "correct_answer": str,
            "shuffled_options": list,
            "correct_index_shuffled": int,
        }
        """
        return await self.store_session_state(f"current_question:{session_id}", question_data)

    async def clear_current_question(self, session_id: str) -> None:
        """Clear current question from session."""
        await self.delete_session_state(f"current_question:{session_id}")

    # ── Session Locking (for Fix 1.2: Prevent race conditions) ─────────────────

    # Now configured via config.py
    LOCK_TIMEOUT = SESSION_LOCK_TIMEOUT_SECONDS  # seconds to wait for lock
    # LOCK_TTL is now set in __init__ from config

    def _lock_key(self, session_id: str) -> str:
        """Get the Redis key for a session lock."""
        return f"lock:{session_id}"

    async def acquire_session_lock(self, session_id: str) -> bool:
        """
        Acquire exclusive lock for session. Waits up to LOCK_TIMEOUT seconds.
        Returns True if lock acquired, False if timeout.
        """
        lock_key = self._lock_key(session_id)
        end_time = asyncio.get_running_loop().time() + self.LOCK_TIMEOUT

        while asyncio.get_running_loop().time() < end_time:
            try:
                if self._redis:
                    # Try SETNX: only succeeds if key doesn't exist
                    acquired = await self._redis.set(
                        lock_key,
                        "1",
                        ex=self.LOCK_TTL,
                        nx=True,  # Only set if not exists
                    )
                    if acquired:
                        return True
                else:
                    # In-memory: simulate with asyncio.Lock
                    if not hasattr(self, '_locks'):
                        self._locks = {}
                    lock = self._locks.setdefault(session_id, asyncio.Lock())
                    try:
                        await asyncio.wait_for(lock.acquire(), timeout=1.0)
                        return True
                    except asyncio.TimeoutError:
                        await asyncio.sleep(0.1)
                        continue

                await asyncio.sleep(0.05)  # Back off 50ms before retrying
            except Exception as e:
                logger.warning(f"Lock acquisition error: {e}")
                await asyncio.sleep(0.1)

        logger.warning(f"Failed to acquire lock for session {session_id} after {self.LOCK_TIMEOUT}s")
        return False

    async def release_session_lock(self, session_id: str) -> None:
        """Release session lock."""
        lock_key = self._lock_key(session_id)
        try:
            if self._redis:
                await self._redis.delete(lock_key)
            else:
                if hasattr(self, '_locks'):
                    lock = self._locks.get(session_id)
                    if lock and lock.locked():
                        lock.release()
        except Exception as e:
            logger.warning(f"Lock release error: {e}")

    @asynccontextmanager
    async def session_lock(self, session_id: str):
        """
        Context manager for session lock.
        Usage: async with session_service.session_lock(session_id):
                   # Do critical work here
        """
        acquired = await self.acquire_session_lock(session_id)
        if not acquired:
            raise TimeoutError(f"Could not acquire lock for session {session_id} within {self.LOCK_TIMEOUT}s")
        try:
            yield
        finally:
            await self.release_session_lock(session_id)
