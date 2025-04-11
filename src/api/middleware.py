from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.models import User
from ..db.db import get_db
from sqlalchemy.future import select
from ..services.rate_limiter import rate_limiter, RateLimiter
from importlib import reload
from redis import asyncio as aioredis
from fastapi import Response, status, Depends
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.base import RequestResponseEndpoint
from ..services.user_service import UserService
from .api_status import api_status, StatusResponse
from ..db.schemas import MessageResponse
import logging

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class APIMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        print("============= MIDDLEWARE ВЫЗВАН =============")

        # Пути, для которых нужна точная проверка
        exact_public_paths = ["/api/register", "/api/openapi.json"]

        # Пути, для которых проверяем только начало
        prefix_public_paths = ["/docs", "/redoc", "/register", "/static", "/status"]

        # Сначала проверяем точное соответствие
        if request.url.path in exact_public_paths:
            print(
                f"============= ПРОПУСКАЕМ ТОЧНЫЙ ПУБЛИЧНЫЙ ПУТЬ: {request.url.path} ============="
            )
            return await call_next(request)

        # Затем проверяем по префиксу
        if any(
            request.url.path == "/" or request.url.path.startswith(prefix + "/")
            for prefix in prefix_public_paths
        ):
            print(
                f"============= ПРОПУСКАЕМ ПУТЬ ПО ПРЕФИКСУ: {request.url.path} ============="
            )
            return await call_next(request)

        # Проверяем API ключ только для остальных API запросов
        if request.url.path.startswith("/api"):
            print("============= ОБРАБАТЫВАЕМ API ЗАПРОС =============")
            api_key = await api_key_header(request)
            print(f"============= API КЛЮЧ: {api_key} =============")

            if not api_key:
                print("============= API КЛЮЧ ОТСУТСТВУЕТ =============")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=MessageResponse(
                        message="Отсутствует ключ API"
                    ).model_dump(),
                )

            # Получаем сессию БД для проверки существования пользователя
            print("============= ПОЛУЧАЕМ СЕССИЮ БД =============")
            db_generator = get_db()
            try:
                db = await db_generator.__anext__()
            except StopAsyncIteration:
                raise HTTPException(
                    status_code=500,
                    detail="Не удалось получить соединение с базой данных",
                )
            except Exception as e_db:
                logger.error(f"Ошибка при получении сессии БД в middleware: {e_db}")
                raise HTTPException(status_code=500, detail="Database connection error")

            try:
                # Проверяем существование пользователя с таким API ключом
                print(
                    f"============= ИЩЕМ ПОЛЬЗОВАТЕЛЯ ПО КЛЮЧУ: {api_key} ============="
                )
                result = await db.execute(select(User).where(User.api_key == api_key))
                user = result.scalar_one_or_none()

                if not user:
                    print("============= ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН =============")
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content=MessageResponse(
                            message="Неверный ключ API"
                        ).model_dump(),
                    )

                print(
                    f"============= ПОЛЬЗОВАТЕЛЬ НАЙДЕН: {user.username}, ЛИМИТ: {user.daily_request_limit} ============="
                )

                # Проверяем лимит запросов через Redis
                print(f"============= ВЫЗЫВАЕМ RATE_LIMITER =============")
                can_proceed, remaining, total_limit, reset_time = (
                    await rate_limiter.check_and_update_limit(
                        api_key, user.daily_request_limit
                    )
                )
                print(
                    f"============= РЕЗУЛЬТАТ ПРОВЕРКИ: can_proceed={can_proceed}, remaining={remaining} ============="
                )

                if not can_proceed:
                    print("============= ЛИМИТ ПРЕВЫШЕН =============")
                    reset_date = datetime.fromtimestamp(reset_time).strftime(
                        "%Y-%m-%d %H:%M:%S UTC"
                    )
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content=MessageResponse(
                            message=f"Request limit exceeded. Limit will be reset on {reset_date}."
                        ).model_dump(),
                    )

                # Сохраняем для использования в заголовках ответа
                request.state.user = user
                request.state.rate_limit_remaining = remaining
                request.state.rate_limit_limit = total_limit
                request.state.rate_limit_reset = reset_time
                request.state.api_key = api_key

                print("============= ПЕРЕДАЕМ ЗАПРОС ДАЛЬШЕ =============")
                response = await call_next(request)
                print("============= ЗАПРОС ОБРАБОТАН =============")

                # Добавляем заголовки с информацией о лимитах
                response.headers["X-RateLimit-Remaining"] = str(
                    request.state.rate_limit_remaining
                )
                response.headers["X-RateLimit-Limit"] = str(
                    request.state.rate_limit_limit
                )
                response.headers["X-RateLimit-Reset"] = str(
                    request.state.rate_limit_reset
                )
                response.headers["X-RateLimit-Reset-Human"] = datetime.fromtimestamp(
                    request.state.rate_limit_reset
                ).strftime("%Y-%m-%d %H:%M:%S UTC")

                return response

            except Exception as e:
                print(f"============= ОШИБКА В MIDDLEWARE: {str(e)} =============")
                await db.close()
                if isinstance(e, HTTPException):
                    raise e
                raise HTTPException(
                    status_code=500,
                    detail="Internal server error during API request processing",
                )
            finally:
                print("============= ЗАКРЫВАЕМ СЕССИЮ БД =============")
                if "db" in locals() and db is not None:
                    await db.close()

        # Для не-API запросов просто пропускаем
        print("============= НЕ API ЗАПРОС, ПРОПУСКАЕМ =============")
        return await call_next(request)


class RequestCounterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_client: aioredis.Redis):
        super().__init__(app)
        self.redis = redis_client

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        try:
            # Вызываем метод для увеличения счетчика и СОХРАНЯЕМ РЕЗУЛЬТАТ
            current_count = api_status.increment_request_count()
            response = await call_next(request)
            # Используем полученное значение счетчика
            response.headers["X-Request-Count"] = str(current_count)
            return response
        except Exception as e:
            logger.error(f"Error in RequestCounterMiddleware: {e}", exc_info=True)
            # Важно: вернуть стандартный ответ об ошибке, а не падать
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=MessageResponse(
                    message="Internal server error in request counter"
                ).model_dump(),
            )


# --- Добавляем RateLimitMiddleware ---
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: RateLimiter):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Получаем API ключ из APIMiddleware (если он был добавлен в state)
        # Или из заголовка, если APIMiddleware не используется перед ним
        api_key = (
            request.state.api_key
            if hasattr(request.state, "api_key")
            else request.headers.get("x-api-key")
        )

        if not api_key:
            # Если ключ не найден (например, для публичных эндпоинтов, которые не должны сюда попадать)
            # Или если RateLimiter должен работать даже без ключа (например, по IP) - нужна другая логика
            logger.warning(
                "RateLimitMiddleware: API key not found in request state or headers."
            )
            # Можно пропустить лимитер или вернуть ошибку, в зависимости от логики
            # return JSONResponse(...)
            return await call_next(request)  # Пока пропускаем

        # Получаем лимит пользователя (если APIMiddleware добавил пользователя в state)
        user_limit = None
        if hasattr(request.state, "user") and request.state.user:
            # Убедись, что у модели User есть поле daily_request_limit
            user_limit = getattr(request.state.user, "daily_request_limit", None)

        # Проверяем лимит с помощью экземпляра RateLimiter
        can_proceed, remaining, total_limit, reset_time = (
            await self.limiter.check_and_update_limit(
                identifier=api_key,  # Можно явно указать имя первого аргумента для ясности
                limit_override=user_limit,  # <--- ИЗМЕНЕНО ЗДЕСЬ
            )
        )

        # Добавляем заголовки с информацией о лимите в ответ
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(total_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)  # Timestamp UTC

        if not can_proceed:
            reset_date = datetime.fromtimestamp(reset_time).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
            # Возвращаем ошибку 429, но уже после того как заголовки добавлены к потенциальному ответу
            # Правильнее вернуть JSONResponse до вызова call_next
            logger.warning(
                f"Rate limit exceeded for key {api_key}. Limit: {total_limit}, Remaining: {remaining}"
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=MessageResponse(
                    message=f"Request limit exceeded ({total_limit} requests). Limit resets at {reset_date}."
                ).model_dump(),
                headers=response.headers,  # Добавляем рассчитанные заголовки к ответу об ошибке
            )

        return response
