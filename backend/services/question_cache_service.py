"""
services/question_cache_service.py — Redis-backed per-user question difficulty caching.

Purpose:
  - Cache the computed per-user difficulty for a question+concept combination
  - Ensures idempotency: same (user, question, concept) tuple always returns same difficulty
  - TTL: 1 hour (configurable via CACHE_TTL)
  - Graceful fallback to in-memory dict if Redis is unavailable

Key Pattern: q_cache:{user_id}:{question_id}:{concept_id}
Value: {"difficulty": 3, "served_at": "2026-04-11T...", "version": 1}
"""

import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class QuestionCacheService:
    """Question difficulty caching with Redis + in-memory fallback.

    Each cached entry maps (user_id, question_id, concept_id) → difficulty (1-5).
    This allows the same question to be served at different difficulty levels
    to different users based on their concept mastery.
    """

    CACHE_TTL = 3600  # 1 hour

    def __init__(self, redis_client=None):
        """Initialize with optional Redis client.

        Args:
            redis_client: aioredis.Redis instance or None for in-memory fallback.
        """
        self.redis = redis_client
        self._fallback_cache: dict[str, tuple[dict, float]] = {}  # key → (value, expiry_timestamp)
        logger.info("QuestionCacheService initialized (redis=%s)", "yes" if redis_client else "fallback")

    @staticmethod
    def _cache_key(user_id: str, question_id: str, concept_id: str) -> str:
        """Generate a namespaced cache key.

        Args:
            user_id: UUID string of the user
            question_id: UUID string of the question
            concept_id: UUID string of the concept

        Returns:
            Redis-style key like "q_cache:abc-123:def-456:ghi-789"
        """
        return f"q_cache:{user_id}:{question_id}:{concept_id}"

    async def get_cached_difficulty(
        self, user_id: str, question_id: str, concept_id: str
    ) -> Optional[int]:
        """Get cached difficulty level (1-5) or None if not cached / expired.

        Args:
            user_id: User UUID string
            question_id: Question UUID string
            concept_id: Concept UUID string

        Returns:
            int (1-5) if cached and not expired, None otherwise
        """
        key = self._cache_key(user_id, question_id, concept_id)

        try:
            if self.redis:
                data = await self.redis.get(key)
                if data:
                    cache_entry = json.loads(data)
                    return cache_entry.get("difficulty")
            else:
                # Fallback: in-memory with timestamp-based TTL
                if key in self._fallback_cache:
                    cache_entry, expiry_ts = self._fallback_cache[key]
                    if time.time() < expiry_ts:
                        return cache_entry.get("difficulty")
                    else:
                        del self._fallback_cache[key]
        except Exception as exc:
            logger.warning("Cache get failed for key=%s: %s", key, exc)

        return None

    async def cache_difficulty(
        self, user_id: str, question_id: str, concept_id: str, difficulty: int
    ) -> None:
        """Store computed difficulty in cache with TTL.

        Args:
            user_id: User UUID string
            question_id: Question UUID string
            concept_id: Concept UUID string
            difficulty: Computed difficulty level (1-5)
        """
        key = self._cache_key(user_id, question_id, concept_id)

        cache_entry = {
            "difficulty": difficulty,
            "served_at": time.time(),
            "version": 1,
        }

        try:
            if self.redis:
                await self.redis.setex(key, self.CACHE_TTL, json.dumps(cache_entry))
            else:
                expiry_ts = time.time() + self.CACHE_TTL
                self._fallback_cache[key] = (cache_entry, expiry_ts)
        except Exception as exc:
            logger.warning("Cache set failed for key=%s: %s", key, exc)

    async def invalidate_difficulty(
        self, user_id: str, question_id: str, concept_id: str
    ) -> None:
        """Force invalidate a single cache entry.

        Called when a user's theta changes significantly (e.g. after a session).
        """
        key = self._cache_key(user_id, question_id, concept_id)

        try:
            if self.redis:
                await self.redis.delete(key)
            else:
                self._fallback_cache.pop(key, None)
        except Exception as exc:
            logger.warning("Cache invalidate failed for key=%s: %s", key, exc)

    async def invalidate_user_all(self, user_id: str) -> None:
        """Invalidate all cached questions for a user.

        Called when user completes a session or their overall theta shifts.
        """
        try:
            if self.redis:
                pattern = f"q_cache:{user_id}:*"
                cursor = "0"
                while cursor != 0:
                    cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        await self.redis.delete(*keys)
            else:
                prefix = f"q_cache:{user_id}:"
                keys_to_delete = [k for k in self._fallback_cache if k.startswith(prefix)]
                for k in keys_to_delete:
                    del self._fallback_cache[k]
        except Exception as exc:
            logger.warning("Cache invalidate_user_all failed for user=%s: %s", user_id[:8], exc)

    async def clear_all(self) -> None:
        """Clear entire cache (dev/testing only)."""
        try:
            if self.redis:
                await self.redis.flushdb()
            else:
                self._fallback_cache.clear()
            logger.info("Cache cleared entirely")
        except Exception as exc:
            logger.warning("Cache clear_all failed: %s", exc)
