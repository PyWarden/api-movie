import redis
import os
from datetime import datetime
import logging
import traceback
import time
from redis import asyncio as aioredis
from fastapi import Depends
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.default_limit = 1000
        self.default_period = 86400

    async def check_and_update_limit(
        self, identifier: str, limit_override: Optional[int] = None
    ) -> Tuple[bool, int, int, int]:
        """
        Проверяет и обновляет лимит запросов для идентификатора (например, API ключа).

        Args:
            identifier: Уникальный идентификатор (API ключ).
            limit_override: Максимальное количество запросов за период. Если None, используется лимит по умолчанию.

        Returns:
            tuple: (
                can_proceed: bool - можно ли выполнить запрос,
                remaining: int - сколько запросов осталось,
                total_limit: int - общий лимит на период,
                reset_time: int - timestamp UTC, когда лимит сбросится
            )
        """
        current_limit, current_period = await self.get_user_limit_and_period(identifier)
        limit_to_check = limit_override if limit_override is not None else current_limit

        key = f"rate_limit:{identifier}"
        now = int(time.time())

        if limit_to_check <= 0:
            reset_ts = (now // current_period + 1) * current_period
            return False, 0, 0, reset_ts

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, now - current_period)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, current_period)
            pipe.ttl(key)
            results = await pipe.execute()

        current_count = results[2]
        ttl = results[4]

        remaining = limit_to_check - current_count
        can_proceed = remaining >= 0

        reset_time = (
            now + ttl if ttl > 0 else (now // current_period + 1) * current_period
        )

        if not can_proceed:
            remaining = 0

        reset_dt = datetime.fromtimestamp(reset_time).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(
            f"Rate limit check for {identifier}: Count={current_count}, Limit={limit_to_check}, Remaining={remaining}, CanProceed={can_proceed}, ResetAt={reset_dt}"
        )

        return can_proceed, remaining, limit_to_check, reset_time

    async def get_usage_info(self, identifier: str) -> Tuple[int, int, int]:
        """Получаем информацию о текущем использовании без увеличения счетчика"""
        key = f"rate_limit:{identifier}"
        now = int(time.time())
        limit, period = await self.get_user_limit_and_period(identifier)

        async with self.redis.pipeline(transaction=False) as pipe:
            pipe.zcard(key)
            pipe.ttl(key)
            results = await pipe.execute()

        current_count = results[0] if results[0] is not None else 0
        ttl = results[1]

        reset_time = now + ttl if ttl > 0 else (now // period + 1) * period

        return current_count, limit, reset_time

    async def set_user_limit(self, identifier: str, limit: int, period: int = 86400):
        """Устанавливает или обновляет лимит для пользователя."""
        limit_key = f"rate_limit_config:{identifier}:limit"
        period_key = f"rate_limit_config:{identifier}:period"
        config_ttl = 365 * 86400

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.setex(limit_key, config_ttl, limit)
            pipe.setex(period_key, config_ttl, period)
            await pipe.execute()
        print(f"Установлен лимит для {identifier}: {limit} запросов / {period} сек")

    async def get_user_limit_and_period(self, identifier: str) -> Tuple[int, int]:
        """Получает настроенный лимит и период для пользователя."""
        limit_key = f"rate_limit_config:{identifier}:limit"
        period_key = f"rate_limit_config:{identifier}:period"

        async with self.redis.pipeline(transaction=False) as pipe:
            pipe.get(limit_key)
            pipe.get(period_key)
            results = await pipe.execute()

        limit_str = results[0]
        period_str = results[1]

        limit = int(limit_str) if limit_str else self.default_limit
        period = int(period_str) if period_str else self.default_period

        return limit, period


# Создаем экземпляр для использования в других модулях
redis_pool_limiter = aioredis.ConnectionPool.from_url(
    os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
)
rate_limiter = RateLimiter(aioredis.Redis.from_pool(redis_pool_limiter))
