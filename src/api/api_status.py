from datetime import datetime
import psutil
from typing import Dict, Any, Optional
from pydantic import BaseModel
import redis
import os
import json


class StatusResponse(BaseModel):
    status: str
    request_count: Dict[str, int]
    uptime: str
    version: str
    limits: Dict[str, int]
    message: Optional[str] = None


class APIStatus:
    def __init__(self):
        self.start_time = datetime.utcnow()
        self.version = "1.0.0"
        self.monthly_limit = 1000

        # Подключение к Redis
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis = redis.from_url(self.redis_url)

        # Инициализация счетчиков, если их нет
        if not self.redis.exists("api:total_requests"):
            self.redis.set("api:total_requests", 0)
        if not self.redis.exists("api:requests_today"):
            self.redis.set("api:requests_today", 0)

        # Установка времени запуска
        self.redis.set("api:start_time", self.start_time.isoformat())

        # Последний сброс
        today = self.start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        if not self.redis.exists("api:last_reset"):
            self.redis.set("api:last_reset", today.isoformat())

    def increment_request_count(self):
        # Увеличиваем общий счетчик
        self.redis.incr("api:total_requests")

        # Проверяем, наступил ли новый день
        now = datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        last_reset_str = self.redis.get("api:last_reset").decode("utf-8")
        last_reset = datetime.fromisoformat(last_reset_str)

        if today > last_reset:
            self.redis.set("api:requests_today", 0)
            self.redis.set("api:last_reset", today.isoformat())

        # Увеличиваем дневной счетчик
        self.redis.incr("api:requests_today")

    def get_status(self):
        # Получаем данные из Redis
        start_time_str = self.redis.get("api:start_time").decode("utf-8")
        start_time = datetime.fromisoformat(start_time_str)
        uptime = str(datetime.utcnow() - start_time).split(".")[0]  # без микросекунд

        total_requests = int(self.redis.get("api:total_requests"))
        requests_today = int(self.redis.get("api:requests_today"))

        # Получаем информацию о количестве пользователей
        active_users = 0
        api_keys = self.redis.keys("ratelimit:*:count")
        if api_keys:
            active_users = len(
                set([key.decode("utf-8").split(":")[1] for key in api_keys])
            )

        return StatusResponse(
            status="online",
            request_count={
                "total": total_requests,
                "today": requests_today,
                "active_users": active_users,
            },
            uptime=uptime,
            version=self.version,
            limits={"monthly_limit": self.monthly_limit},
            message="API работает нормально. Лимит на каждый API ключ: 1000 запросов в месяц.",
        )


# Создаем глобальный трекер статуса
api_status = APIStatus()
