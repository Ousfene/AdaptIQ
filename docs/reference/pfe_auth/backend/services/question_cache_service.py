"""
services/question_cache_service.py — High-performance Redis caching for questions.

Purpose:
- Cache questions with computed per-user difficulty
- Idempotency: same user+question+concept always gets same difficulty
- TTL-based expiry to prevent stale cached difficulties

Key: question_cache:{user_id}:{question_id}:{concept_id}
Value: {difficulty, served_at, version}
TTL: 1 hour
"""

import json
import logging
from uuid import UUID
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

CACHE_TTL = 3600  # 1 hour


class QuestionCacheService:
    """Redis-backed question caching with per-user difficulty."""

    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self.redis = redis_client

    @staticmethod
    def question_cache_key(
        user_id: UUID,
        question_id: UUID,
        concept_id: UUID,
    ) -> str:
        """Generate Redis cache key for question."""
        return f"q_cache:{user_id}:{question_id}:{concept_id}"

    async def get_cached_difficulty(
        self,
        user_id: UUID,
        question_id: UUID,
        concept_id: UUID,
    ) -> Optional[int]:
        """
        Retrieve cached difficulty for a user-question-concept tuple.
        Returns difficulty (1-5) or None if not cached.
        """
        if not self.redis:
            return None

        key = self.question_cache_key(user_id, question_id, concept_id)
        try:
            data = await self.redis.get(key)
            if data:
                cache_entry = json.loads(data)
                return cache_entry.get("difficulty")
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")

        return None

    async def cache_difficulty(
        self,
        user_id: UUID,
        question_id: UUID,
        concept_id: UUID,
        difficulty: int,
    ) -> None:
        """
        Store computed difficulty in cache.
        Include metadata for debugging and analytics.
        """
        if not self.redis:
            return

        key = self.question_cache_key(user_id, question_id, concept_id)
        cache_entry = {
            "difficulty": difficulty,
            "served_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "version": 1,  # For future cache invalidation strategies
        }

        try:
            await self.redis.setex(
                key,
                CACHE_TTL,
                json.dumps(cache_entry),
            )
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")

    async def invalidate_difficulty(
        self,
        user_id: UUID,
        question_id: UUID,
        concept_id: UUID,
    ) -> None:
        """Force invalidate cache entry (used if IRT recalibration changes difficulty)."""
        if not self.redis:
            return

        key = self.question_cache_key(user_id, question_id, concept_id)
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

    async def invalidate_user_questions(
        self,
        user_id: UUID,
    ) -> None:
        """
        Invalidate all cached questions for a user.
        Called when user's concept thetas are significantly recalibrated.
        """
        if not self.redis:
            return

        pattern = f"q_cache:{user_id}:*"
        try:
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"User cache invalidation failed: {e}")

    async def get_cache_stats(self) -> dict:
        """Get cache hit/miss statistics (for monitoring)."""
        if not self.redis:
            return {}

        try:
            info = await self.redis.info()
            return {
                "used_memory": info.get("used_memory_human", "N/A"),
                "total_commands": info.get("total_commands_processed", 0),
            }
        except Exception as e:
            logger.warning(f"Cache stats retrieval failed: {e}")
            return {}
