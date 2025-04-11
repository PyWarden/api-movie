import os
from fastapi import FastAPI, Depends, Security, Request
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from .api.routes import status_router, api_router, web_router, movies_router
from .api.middleware import APIMiddleware, RequestCounterMiddleware, RateLimitMiddleware
from .db.schemas import UserResponse
from fastapi import APIRouter
from fastapi.middleware.cors import CORSMiddleware
from redis import asyncio as aioredis
import uvicorn
from .db.db import database, SQLALCHEMY_DATABASE_URL, connect_db, disconnect_db
from .services.rate_limiter import RateLimiter, rate_limiter
import logging
from contextlib import asynccontextmanager
from .utils.caching import close_cache_connection

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Глобальные ресурсы (пулы) ---
# Создаем пулы здесь, чтобы они были доступны при инициализации middleware
# и могли быть отключены в lifespan
redis_pool_counter = aioredis.ConnectionPool.from_url(
    os.getenv("REDIS_URL", "redis://redis:6379/1"), decode_responses=True
)
redis_pool_limiter = aioredis.ConnectionPool.from_url(
    os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
)


# --- Определение Lifespan ---
# Перемещаем определение lifespan ПЕРЕД использованием в FastAPI
@asynccontextmanager
async def lifespan(
    app_instance: FastAPI,
):  # Переименовал параметр, чтобы не конфликтовал с именем функции
    logger.info("Starting up...")
    # Подключаемся к базам данных
    await connect_db()  # Подключаем 'databases'
    logger.info("Database connection established.")
    # Здесь можно инициализировать другие ресурсы, если нужно
    # Например, создать Redis клиенты из пулов и положить в app.state, если они нужны в эндпоинтах
    # app_instance.state.redis_counter_client = aioredis.Redis.from_pool(redis_pool_counter)
    # app_instance.state.redis_limiter_client = aioredis.Redis.from_pool(redis_pool_limiter)
    yield
    # Отключаемся при завершении работы
    logger.info("Shutting down...")
    # Закрываем соединения редис при остановке
    # if hasattr(app_instance.state, 'redis_counter_client'):
    #    await app_instance.state.redis_counter_client.close()
    # if hasattr(app_instance.state, 'redis_limiter_client'):
    #    await app_instance.state.redis_limiter_client.close()
    # Отключаем пулы
    await redis_pool_counter.disconnect()
    await redis_pool_limiter.disconnect()
    await close_cache_connection()
    logger.info("Redis connections closed.")
    await disconnect_db()  # Отключаем 'databases'
    logger.info("Database connection closed.")


# --- Создание приложения FastAPI ---
# Теперь определение lifespan находится выше
app = FastAPI(
    title="Онлайн-кинотеатр API",
    description="""
    Добро пожаловать в API сервиса 'MovieApi'!
    
    Этот API предоставляет доступ к базе данных фильмов, включая поиск, фильтрацию и рекомендации. Для использования API необходим ключ доступа.
    
    Функции API:
    - Поиск фильмов по различным параметрам
    - Просмотр детальной информации о фильмах
    - Получение рекомендаций похожих фильмов
    - Статистика по жанрам и рейтингам
    
    **ВАЖНОЕ ОГРАНИЧЕНИЕ**: Максимальное количество запросов - 1000 в месяц на один API ключ.
    Лимит обновляется в первый день каждого месяца.
    
    Контакты: movie-api@yandex.ru
    
    """,
    version="1.0.0",
    openapi_tags=[
        {
            "name": "Фильмы",
            "description": "🎬 Управление коллекцией фильмов, получение детальной информации",
        },
        {
            "name": "Поиск",
            "description": "🔍 Интеллектуальный поиск и фильтрация фильмов по различным параметрам",
        },
        {
            "name": "Аналитика",
            "description": "📊 Статистика, рейтинги и аналитические данные по коллекции",
        },
        {
            "name": "Безопасность",
            "description": "🔐 Регистрация, авторизация и управление доступом",
        },
    ],
    swagger_ui_parameters={
        "syntaxHighlight.theme": "monokai",
        "docExpansion": "list",
        "defaultModelsExpandDepth": 3,
        "defaultModelExpandDepth": 3,
        "displayRequestDuration": True,
        "filter": True,
        "deepLinking": True,
        "showExtensions": True,
        "showCommonExtensions": True,
        "tryItOutEnabled": True,
        "persistAuthorization": True,
    },
    lifespan=lifespan,  # Теперь lifespan известен
)


# --- Монтирование статики и шаблонов ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Middleware ---
# Настройка CORS
origins = [
    "http://localhost",
    "http://localhost:8080",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# APIMiddleware (должен идти первым, если он проверяет ключ и лимиты)
# Убедись, что он не зависит от ресурсов, создаваемых в lifespan, если это так
app.add_middleware(APIMiddleware)
logger.info("APIMiddleware added.")

# Request Counter Middleware
# Используем глобальный пул для создания клиента
app.add_middleware(
    RequestCounterMiddleware, redis_client=aioredis.Redis.from_pool(redis_pool_counter)
)
logger.info("RequestCounterMiddleware added.")

# Rate Limiter Middleware
# Используем глобальный экземпляр rate_limiter, который сам использует глобальный пул
app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)
logger.info("RateLimitMiddleware added.")


# --- Роутеры ---
# Создаем схему API ключа
api_key_header = APIKeyHeader(
    name="X-API-Key", auto_error=False
)  # Auto_error=False, т.к. APIMiddleware проверяет

# Подключаем роутеры

# Веб-интерфейс (без префикса, если пути в web_router уже /register и т.д.)
# Если в web_router пути просто "/", то нужен префикс "/web"
app.include_router(web_router, tags=["Веб-интерфейс"])

# Статус API
app.include_router(status_router, prefix="/status", tags=["Статус"])

# API роутер (регистрация, проверка ключа и т.д.)
# УБИРАЕМ prefix="/api", так как он уже задан в самом роутере
app.include_router(api_router, tags=["API Основное"])

# Роутер для фильмов (защищенный)
# УБИРАЕМ prefix="/api", так как он уже задан в самом роутере
# Если movies_router тоже имеет свой префикс /movies, то путь будет /api/movies
app.include_router(
    movies_router, dependencies=[Security(api_key_header)], tags=["Фильмы"]
)


# --- Корневой эндпоинт и тестовый эндпоинт ---
@app.get("/", include_in_schema=False)
async def read_root(request: Request):
    # Проверяем, существует ли файл index.html
    if not os.path.exists("templates/index.html"):
        logger.error("Template file 'index.html' not found.")
        raise HTTPException(status_code=500, detail="Index template not found.")
    return templates.TemplateResponse("index.html", {"request": request})


# Тестовый эндпоинт без защиты ключом (если нужен)
# @app.get("/api/test-rate-limit")
# async def test_rate_limit():
#    return {"message": "Тестовый эндпоинт для проверки ограничения запросов"}


# --- Удаляем старые обработчики startup/shutdown ---
# @app.on_event("startup") ...
# @app.on_event("shutdown") ...

# --- Запуск Uvicorn ---
if __name__ == "__main__":
    logger.info("Starting Uvicorn server...")
    # Обрати внимание на команду запуска uvicorn:
    # Правильно: uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 (запуск из корневой папки проекта)
    # Неправильно: uvicorn main:app ... (запуск из папки src)
    # Команда в __main__ обычно используется для локальной отладки вне Docker.
    # Если ты запускаешь через `docker-compose up`, эта часть кода не выполняется.
    # Если запускаешь локально: python src/main.py, то этот uvicorn.run сработает.
    uvicorn.run(
        "main:app", host="0.0.0.0", port=8000, reload=True
    )  # Оставляем 'main:app' для запуска `python src/main.py`
