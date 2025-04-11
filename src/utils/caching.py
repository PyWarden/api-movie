import json
import functools
import inspect
from typing import Callable, Any
from redis import asyncio as aioredis
import os
import logging

logger = logging.getLogger(__name__)

# Используем тот же URL Redis, что и в main.py (для rate limiter, DB 0)
# Лучше всего вынести URL в переменные окружения
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
# Используем try-except на случай, если Redis недоступен при импорте (например, при сборке)
try:
    redis_pool_cache = aioredis.ConnectionPool.from_url(
        REDIS_URL, decode_responses=False
    )  # False, т.к. будем хранить JSON (байты)
    redis_client_cache = aioredis.Redis.from_pool(redis_pool_cache)
    # Пробный пинг для проверки доступности при старте
    # asyncio.run(redis_client_cache.ping()) # Нельзя использовать asyncio.run на верхнем уровне модуля
    logger.info(f"Successfully connected to Redis cache at {REDIS_URL}")
except Exception as e:
    logger.error(f"Failed to connect to Redis cache at {REDIS_URL}: {e}")
    # Устанавливаем в None, чтобы декоратор мог проверить и пропустить кэширование
    redis_pool_cache = None
    redis_client_cache = None


# Время жизни кэша по умолчанию (в секундах)
DEFAULT_CACHE_TTL = 300  # 5 минут


def generate_cache_key(func: Callable, *args: Any, **kwargs: Any) -> str:
    """Генерирует ключ кэша на основе имени функции и её аргументов."""
    # Получаем информацию об аргументах функции
    sig = inspect.signature(func)
    bound_args = sig.bind(*args, **kwargs)
    bound_args.apply_defaults()

    # Убираем зависимости FastAPI (вроде db: AsyncSession) из ключа
    args_dict = {
        name: value
        for name, value in bound_args.arguments.items()
        # Проверяем, есть ли у аргумента аннотация и не является ли она зависимостью (грубая проверка)
        # Исключаем стандартные зависимости и Redis клиент
        if name not in ("db", "request", "background_tasks", "db_session", "api_key")
        and not isinstance(value, (aioredis.Redis))
    }

    # Создаем стабильное представление аргументов
    try:
        key_part = json.dumps(
            args_dict, sort_keys=True, default=str
        )  # default=str для несериализуемых объектов
    except TypeError as e:
        logger.warning(
            f"Could not serialize arguments for cache key generation in {func.__name__}: {e}. Args: {args_dict}"
        )
        # Используем пустой словарь, если сериализация не удалась
        key_part = json.dumps({}, sort_keys=True)

    # Префикс ключа - имя модуля и функции
    key_prefix = f"cache:{func.__module__}:{func.__name__}"

    return f"{key_prefix}:{key_part}"


def cache(ttl: int = DEFAULT_CACHE_TTL) -> Callable:
    """
    Декоратор для кэширования результатов асинхронных функций в Redis.

    Args:
        ttl: Время жизни кэша в секундах.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Проверяем, инициализирован ли клиент Redis
            if redis_client_cache is None:
                logger.warning(
                    f"Redis client not available, skipping cache for {func.__name__}"
                )
                return await func(*args, **kwargs)

            key = generate_cache_key(func, *args, **kwargs)
            logger.debug(f"Generated cache key: {key}")

            try:
                # Проверяем наличие в кэше
                cached_data = await redis_client_cache.get(key)
                if cached_data:
                    logger.info(f"Cache HIT for key: {key}")
                    # Десериализуем из JSON (храним как байты)
                    try:
                        return json.loads(cached_data.decode("utf-8"))
                    except json.JSONDecodeError as decode_err:
                        logger.error(
                            f"Failed to decode cached JSON for key {key}: {decode_err}. Data: {cached_data[:100]}..."
                        )
                        # Если данные в кэше повреждены, удаляем их и выполняем функцию
                        await redis_client_cache.delete(key)
                        logger.warning(f"Deleted corrupted cache entry for key: {key}")

                else:
                    logger.info(f"Cache MISS for key: {key}")

            except aioredis.RedisError as e:
                logger.error(f"Redis GET error for key {key}: {e}")
                # При ошибке чтения из кэша выполняем функцию, чтобы не сломать приложение
                return await func(*args, **kwargs)
            except Exception as e:  # Ловим другие возможные ошибки
                logger.error(f"Unexpected error during cache GET for key {key}: {e}")
                return await func(*args, **kwargs)

            # Если в кэше нет или он был поврежден, выполняем функцию
            result = await func(*args, **kwargs)

            try:
                # Сериализуем в JSON и сохраняем в кэш
                data_to_cache = result
                # Проверяем, является ли результат FastAPI Response
                if (
                    hasattr(result, "body")
                    and hasattr(result, "media_type")
                    and isinstance(getattr(result, "media_type", None), str)
                    and "json" in result.media_type
                ):
                    # Попытка декодировать тело JSONResponse
                    try:
                        data_to_cache = json.loads(result.body.decode("utf-8"))
                    except Exception as decode_err:
                        logger.error(
                            f"Failed to decode JSONResponse body for caching key {key}: {decode_err}"
                        )
                        # Не кэшируем, если не смогли декодировать, просто возвращаем результат
                        return result
                elif hasattr(
                    result, "body"
                ):  # Если это другой тип Response, не кэшируем его тело
                    logger.warning(
                        f"Result for key {key} is a non-JSON Response, not caching."
                    )
                    return result

                # Сериализуем результат (или извлеченные данные) в JSON строку (байты)
                try:
                    serialized_result = json.dumps(data_to_cache).encode("utf-8")
                except TypeError as e:
                    logger.error(
                        f"Failed to serialize result to JSON for key {key}: {e}. Data: {data_to_cache}"
                    )
                    return result  # Возвращаем результат, если не можем сериализовать

                await redis_client_cache.setex(key, ttl, serialized_result)
                logger.info(f"Cached result for key: {key} with TTL: {ttl}s")

            except aioredis.RedisError as e:
                logger.error(f"Redis SETEX error for key {key}: {e}")
                # Возвращаем результат даже если не удалось сохранить в кэш
            except Exception as e:  # Ловим другие возможные ошибки
                logger.error(f"Unexpected error during cache SETEX for key {key}: {e}")

            return result  # Возвращаем оригинальный результат

        return wrapper

    return decorator


async def close_cache_connection():
    """Закрывает пул соединений Redis для кэша."""
    if redis_pool_cache:
        await redis_pool_cache.disconnect()
        logger.info("Redis cache connection pool closed.")
