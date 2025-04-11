from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    BackgroundTasks,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.future import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..db.db import get_db
from fastapi.templating import Jinja2Templates
from ..db.models import (
    Movie,
    Genre,
    movie_genres,
    Actor,
    movie_actors,
    Director,
    movie_directors,
    Country,
    movie_countries,
)
from ..db.schemas import (
    MovieCreate,
    Movie as MovieSchema,
    UserCreate,
    UserResponse,
    MessageResponse,
)
from ..services.user_service import UserService
import httpx
import logging
import json
import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from fastapi.security.api_key import APIKeyHeader
from fastapi import Security
from fastapi.templating import Jinja2Templates
from .api_status import api_status, StatusResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
from sqlalchemy.sql import or_
from sqlalchemy.sql import func
from sqlalchemy import desc
import random
from datetime import datetime
from ..services.rate_limiter import rate_limiter
from ..utils.caching import cache

logger = logging.getLogger(__name__)

# Создаем отдельные роутеры для API и веб-страниц
web_router = APIRouter()
status_router = APIRouter()
api_router = APIRouter(prefix="/api")
movies_router = APIRouter()
api_key_header = APIKeyHeader(
    name="X-API-Key",
    description="API ключ для аутентификации. Получите его при регистрации.",
    auto_error=False,
)


class RequestCounterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_status.increment_request_count()
        response = await call_next(request)
        return response


templates = Jinja2Templates(directory="templates")


@status_router.get("/status", response_class=HTMLResponse, include_in_schema=False)
async def status_page(request: Request):
    return templates.TemplateResponse("status.html", {"request": request})


@movies_router.get(
    "/genre/{genre}",
    tags=["Фильмы"],
    summary="Получить фильмы по жанру",
    description="Возвращает список фильмов определенного жанра. Можно указать количество возвращаемых фильмов (не более 25).",
    dependencies=[Security(api_key_header)],
)
async def get_movies_by_genre(
    genre: str, limit: int = 5, db: AsyncSession = Depends(get_db)
):
    try:
        # Проверяем и ограничиваем количество возвращаемых фильмов
        if limit <= 0:
            limit = 5  # Значение по умолчанию
        elif limit > 25:
            limit = 25  # Максимальное значение

        # Выполняем запрос к базе данных для поиска фильмов по жанру
        # Поскольку жанры хранятся в отдельной таблице и связаны через movie_genres

        # Ищем фильмы, у которых есть связь с указанным жанром
        result = await db.execute(
            select(Movie)
            .join(movie_genres, Movie.id == movie_genres.c.movie_id)
            .join(Genre, movie_genres.c.genre_id == Genre.id)
            .where(Genre.name.ilike(f"%{genre}%"))
            .limit(limit)
        )

        movies = result.scalars().all()

        if not movies:
            return JSONResponse(
                status_code=404,
                content={"message": f"Фильмы жанра '{genre}' не найдены"},
            )

        formatted_movies = []
        for movie in movies:
            # Получаем жанры для каждого фильма
            genres_result = await db.execute(
                select(Genre.name)
                .join(movie_genres, Genre.id == movie_genres.c.genre_id)
                .where(movie_genres.c.movie_id == movie.id)
            )
            genres = [genre[0] for genre in genres_result.fetchall()]

            movie_data = {
                "id": movie.id,
                "title": movie.title,
                "year": movie.year,
                "genres": genres,
                "rating": movie.rating,
                "created_at": (
                    movie.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if movie.created_at
                    else None
                ),
            }

            # Добавляем необязательные поля только если они не пустые
            if movie.original_title:
                movie_data["original_title"] = movie.original_title

            if movie.description and movie.description.strip():
                movie_data["description"] = movie.description

            formatted_movies.append(movie_data)

        return JSONResponse(
            content={
                "genre": genre,
                "count": len(formatted_movies),
                "limit": limit,
                "movies": formatted_movies,
            }
        )
    except Exception as e:
        logger.error(f"Ошибка при получении фильмов по жанру: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Ошибка при получении фильмов жанра '{genre}'"},
        )


@status_router.get("/api/status", response_model=StatusResponse, tags=["Аналитика"])
async def get_api_status():
    return api_status.get_status()


@movies_router.get(
    "/movies",
    tags=["Фильмы"],
    summary="Получить список всех фильмов",
    description="Возвращает список всех фильмов из базы данных",
    dependencies=[Security(api_key_header)],
)
@cache(ttl=180)
async def get_movies(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Movie))
        movies = result.scalars().all()
        formatted_movies = []
        for movie in movies:
            movie_data = {
                "id": movie.id,
                "title": movie.title,
                "year": movie.year,
                "rating": movie.rating,
                "created_at": (
                    movie.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if movie.created_at
                    else None
                ),
            }

            # Добавляем необязательные поля только если они не пустые
            if movie.original_title:
                movie_data["original_title"] = movie.original_title

            if movie.description and movie.description.strip():
                movie_data["description"] = movie.description

            formatted_movies.append(movie_data)

        return JSONResponse(content=formatted_movies)
    except Exception as e:
        print(f"Error: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": "Ошибка при получении списка фильмов"}
        )


@movies_router.get(
    "/movies/{movie_id}",
    tags=["Фильмы"],
    summary="Получить фильм по ID",
    description="Возвращает информацию о конкретном фильме по его ID",
    dependencies=[Security(api_key_header)],
)
async def get_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Movie).where(Movie.id == movie_id))
    movie = result.scalars().first()
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    # Получаем все жанры для фильма
    genres_result = await db.execute(
        select(Genre.name)
        .join(movie_genres, Genre.id == movie_genres.c.genre_id)
        .where(movie_genres.c.movie_id == movie.id)
    )
    genres = [genre[0] for genre in genres_result.fetchall()]

    # Формируем ответ с проверкой пустых полей
    movie_data = {
        "id": movie.id,
        "title": movie.title,
        "year": movie.year,
        "genres": genres,
        "rating": movie.rating,
        "created_at": (
            movie.created_at.strftime("%Y-%m-%d %H:%M:%S") if movie.created_at else None
        ),
    }

    # Добавляем необязательные поля только если они не пустые
    if movie.original_title:
        movie_data["original_title"] = movie.original_title

    if movie.description and movie.description.strip():
        movie_data["description"] = movie.description

    return JSONResponse(content=movie_data)


# Маршруты для веб-страниц
@web_router.get("/register", response_class=HTMLResponse, include_in_schema=False)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


# --- Загрузка конфигурации ---
def load_config():
    # Путь к config.json относительно текущего файла (routes.py)
    # src/api/routes.py -> src/ -> ../ -> config.json
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.json"
    )
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found at {config_path}")
        return None
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {config_path}")
        return None


config = load_config()
cloudflare_config = config.get("cloudflare_turnstile") if config else None
CLOUDFLARE_SECRET_KEY = (
    cloudflare_config.get("secret_key") if cloudflare_config else None
)
# -----------------------------


@api_router.post("/register", response_model=UserResponse, include_in_schema=False)
async def register_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    if (
        not CLOUDFLARE_SECRET_KEY
        or CLOUDFLARE_SECRET_KEY == "YOUR_CLOUDFLARE_TURNSTILE_SECRET_KEY"
    ):
        logger.error(
            "Cloudflare Turnstile secret key is not configured or is a placeholder in config.json. Registration disabled."
        )
        return JSONResponse(
            status_code=503,  # Service Unavailable
            content={
                "error_code": "config_error",
                "detail": "Сервис временно недоступен из-за ошибки конфигурации.",
            },
        )

    try:
        # Проверка Turnstile
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={
                    "secret": CLOUDFLARE_SECRET_KEY,  # <--- Используем ключ из конфига
                    "response": user_data.turnstileToken,
                },
            )

            result = response.json()
            if not result.get("success"):
                logger.error(f"Captcha verification failed: {result}")
                return JSONResponse(
                    status_code=400,
                    content={
                        "error_code": "captcha_failed",
                        "detail": "Ошибка проверки капчи",
                    },
                )

        # Проверка существующего пользователя
        existing_user = await UserService.get_user_by_username(db, user_data.username)
        if existing_user:
            return JSONResponse(
                status_code=400,
                content={
                    "error_code": "username_exists",
                    "detail": "Пользователь с таким именем уже существует",
                },
            )

        # Проверка существующего email
        existing_email = await UserService.get_user_by_email(db, user_data.email)
        if existing_email:
            return JSONResponse(
                status_code=400,
                content={
                    "error_code": "email_exists",
                    "detail": "Этот email уже зарегистрирован",
                },
            )

        # Создание пользователя
        try:
            user = await UserService.create_user(db, user_data)

            # Инициализируем лимит в Redis
            await rate_limiter.set_user_limit(user.api_key, user.daily_request_limit)

            # Получаем текущую информацию о лимите
            _, _, reset_time = await rate_limiter.get_usage_info(user.api_key)
            reset_date = datetime.fromtimestamp(reset_time).strftime("%Y-%m-%d")

            # --- Добавить вызов отправки email ---
            try:
                logger.info(f"Пытаемся отправить API ключ на {user.email}...")
                await UserService.send_api_key_email(
                    user_email=user.email, username=user.username, api_key=user.api_key
                )
                logger.info(
                    f"Email с API ключом для {user.username} отправлен (или попытка отправки завершена)."
                )
            except Exception as email_error:
                # Логируем ошибку отправки, но не прерываем процесс регистрации
                logger.error(
                    f"Не удалось отправить email с API ключом для {user.username} на {user.email}: {email_error}",
                    exc_info=True,
                )
            # -------------------------------------

            logger.info(f"Пользователь {user_data.username} успешно создан.")
            return UserResponse(
                username=user.username,
                email=user.email,
                api_key=user.api_key,
                monthly_request_limit=user.daily_request_limit,
                monthly_requests_remaining=user.daily_request_limit,  # Все доступны при регистрации
                next_reset_date=reset_date,
            )

        except ValueError as ve:
            logger.error(f"Validation error during user creation: {str(ve)}")
            return JSONResponse(
                status_code=400,
                content={"error_code": "validation_error", "detail": str(ve)},
            )

    except IntegrityError as ie:
        logger.error(f"Database integrity error: {str(ie)}")
        return JSONResponse(
            status_code=400,
            content={
                "error_code": "database_error",
                "detail": "Ошибка при создании пользователя",
            },
        )
    except Exception as e:
        logger.error(f"Unexpected error during registration: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "server_error",
                "detail": "Внутренняя ошибка сервера",
            },
        )


@api_router.get(
    "/verify", tags=["Безопасность"], dependencies=[Security(api_key_header)]
)
async def verify_api_key(api_key: str, db: AsyncSession = Depends(get_db)):
    user = await UserService.get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Недействительный API ключ")
    return {"valid": True, "username": user.username}


@movies_router.get(
    "/genres",
    tags=["Фильмы"],
    summary="Получить список доступных жанров",
    description="Возвращает список всех жанров фильмов в базе данных",
    dependencies=[Security(api_key_header)],
)
@cache(ttl=3600)
async def get_genres(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Genre))
        genres = result.scalars().all()

        formatted_genres = [{"id": genre.id, "name": genre.name} for genre in genres]

        return JSONResponse(
            content={"count": len(formatted_genres), "genres": formatted_genres}
        )
    except Exception as e:
        logger.error(f"Ошибка при получении списка жанров: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": "Ошибка при получении списка жанров"}
        )


@movies_router.get(
    "/search",
    tags=["Поиск"],
    summary="Поиск фильмов",
    description="Поиск фильмов по названию, году выпуска и другим параметрам",
    dependencies=[Security(api_key_header)],
)
async def search_movies(
    query: Optional[str] = None,
    year: Optional[int] = None,
    min_rating: Optional[int] = None,
    genre: Optional[str] = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    try:
        # Ограничиваем лимит до 25
        if limit <= 0:
            limit = 10
        elif limit > 25:
            limit = 25

        # Начинаем строить запрос
        movie_query = select(Movie)

        # Применяем фильтры, если они указаны
        if query:
            movie_query = movie_query.filter(
                or_(
                    Movie.title.ilike(f"%{query}%"),
                    Movie.original_title.ilike(f"%{query}%"),
                )
            )

        if year:
            movie_query = movie_query.filter(Movie.year == year)

        if min_rating:
            movie_query = movie_query.filter(Movie.rating >= min_rating)

        # Если указан жанр, применяем фильтр по жанру
        if genre:
            movie_query = (
                movie_query.join(movie_genres, Movie.id == movie_genres.c.movie_id)
                .join(Genre, movie_genres.c.genre_id == Genre.id)
                .filter(Genre.name.ilike(f"%{genre}%"))
            )

        # Применяем лимит и выполняем запрос
        movie_query = movie_query.limit(limit)
        result = await db.execute(movie_query)
        movies = result.scalars().all()

        # Формируем ответ
        formatted_movies = []
        for movie in movies:
            # Получаем жанры для фильма
            genres_result = await db.execute(
                select(Genre.name)
                .join(movie_genres, Genre.id == movie_genres.c.genre_id)
                .where(movie_genres.c.movie_id == movie.id)
            )
            genres = [genre[0] for genre in genres_result.fetchall()]

            movie_data = {
                "id": movie.id,
                "title": movie.title,
                "year": movie.year,
                "genres": genres,
                "rating": movie.rating,
                "created_at": (
                    movie.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if movie.created_at
                    else None
                ),
            }

            # Добавляем необязательные поля только если они не пустые
            if movie.original_title:
                movie_data["original_title"] = movie.original_title

            if movie.description and movie.description.strip():
                movie_data["description"] = movie.description

            formatted_movies.append(movie_data)

        return JSONResponse(
            content={
                "count": len(formatted_movies),
                "filters": {
                    "query": query,
                    "year": year,
                    "min_rating": min_rating,
                    "genre": genre,
                    "limit": limit,
                },
                "movies": formatted_movies,
            }
        )
    except Exception as e:
        logger.error(f"Ошибка при поиске фильмов: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": "Ошибка при поиске фильмов"}
        )


@movies_router.get(
    "/random",
    tags=["Поиск"],
    summary="Случайный фильм",
    description="Получить случайный фильм с возможностью фильтрации по жанру",
    dependencies=[Security(api_key_header)],
)
async def get_random_movie(
    genre: Optional[str] = None, db: AsyncSession = Depends(get_db)
):
    try:
        # Начинаем строить запрос
        movie_query = select(Movie)

        # Если указан жанр, фильтруем по нему
        if genre:
            movie_query = (
                movie_query.join(movie_genres, Movie.id == movie_genres.c.movie_id)
                .join(Genre, movie_genres.c.genre_id == Genre.id)
                .filter(Genre.name.ilike(f"%{genre}%"))
            )

        # Получаем количество фильмов для этого запроса
        count_query = select(func.count()).select_from(movie_query.subquery())
        result = await db.execute(count_query)
        total_count = result.scalar()

        if total_count == 0:
            return JSONResponse(
                status_code=404, content={"message": "Фильмы не найдены"}
            )

        # Выбираем случайный индекс
        random_index = random.randint(0, total_count - 1)

        # Получаем случайный фильм
        movie_query = movie_query.offset(random_index).limit(1)
        result = await db.execute(movie_query)
        movie = result.scalars().first()

        # Получаем жанры для фильма
        genres_result = await db.execute(
            select(Genre.name)
            .join(movie_genres, Genre.id == movie_genres.c.genre_id)
            .where(movie_genres.c.movie_id == movie.id)
        )
        genres = [genre[0] for genre in genres_result.fetchall()]

        # Формируем ответ
        movie_data = {
            "id": movie.id,
            "title": movie.title,
            "year": movie.year,
            "genres": genres,
            "rating": movie.rating,
            "created_at": (
                movie.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if movie.created_at
                else None
            ),
        }

        # Добавляем необязательные поля только если они не пустые
        if movie.original_title:
            movie_data["original_title"] = movie.original_title

        if movie.description and movie.description.strip():
            movie_data["description"] = movie.description

        return JSONResponse(content=movie_data)
    except Exception as e:
        logger.error(f"Ошибка при получении случайного фильма: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": "Ошибка при получении случайного фильма"}
        )


@movies_router.get(
    "/{movie_id}/similar",
    tags=["Поиск"],
    summary="Похожие фильмы",
    description="Получить фильмы, похожие на указанный (на основе жанров)",
    dependencies=[Security(api_key_header)],
)
async def get_similar_movies(
    movie_id: int, limit: int = 5, db: AsyncSession = Depends(get_db)
):
    try:
        # Ограничиваем лимит до 25
        if limit <= 0:
            limit = 5
        elif limit > 25:
            limit = 25

        # Проверяем существование фильма
        movie_result = await db.execute(select(Movie).where(Movie.id == movie_id))
        movie = movie_result.scalars().first()

        if not movie:
            return JSONResponse(status_code=404, content={"message": "Фильм не найден"})

        # Получаем жанры фильма
        genres_result = await db.execute(
            select(Genre.id)
            .join(movie_genres, Genre.id == movie_genres.c.genre_id)
            .where(movie_genres.c.movie_id == movie_id)
        )
        genre_ids = [genre[0] for genre in genres_result.fetchall()]

        if not genre_ids:
            return JSONResponse(
                status_code=404,
                content={"message": "У фильма нет жанров для поиска похожих"},
            )

        # Ищем фильмы с такими же жанрами, исключая исходный фильм
        similar_movies_query = (
            select(Movie, func.count(Genre.id).label("matching_genres"))
            .join(movie_genres, Movie.id == movie_genres.c.movie_id)
            .join(Genre, movie_genres.c.genre_id == Genre.id)
            .where(Genre.id.in_(genre_ids))
            .where(Movie.id != movie_id)
            .group_by(Movie.id)
            .order_by(desc("matching_genres"), desc(Movie.rating))
            .limit(limit)
        )

        result = await db.execute(similar_movies_query)
        similar_movies = result.fetchall()

        # Формируем ответ
        formatted_movies = []
        for movie_info in similar_movies:
            movie = movie_info[0]  # Первый элемент - это объект Movie
            matching_count = movie_info[
                1
            ]  # Второй элемент - количество совпадающих жанров

            # Получаем все жанры фильма
            movie_genres_result = await db.execute(
                select(Genre.name)
                .join(movie_genres, Genre.id == movie_genres.c.genre_id)
                .where(movie_genres.c.movie_id == movie.id)
            )
            genres = [genre[0] for genre in movie_genres_result.fetchall()]

            movie_data = {
                "id": movie.id,
                "title": movie.title,
                "year": movie.year,
                "genres": genres,
                "rating": movie.rating,
                "matching_genres": matching_count,
                "created_at": (
                    movie.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if movie.created_at
                    else None
                ),
            }

            # Добавляем необязательные поля только если они не пустые
            if movie.original_title:
                movie_data["original_title"] = movie.original_title

            if movie.description and movie.description.strip():
                movie_data["description"] = movie.description

            formatted_movies.append(movie_data)

        return JSONResponse(
            content={
                "movie_id": movie_id,
                "count": len(formatted_movies),
                "similar_movies": formatted_movies,
            }
        )
    except Exception as e:
        logger.error(f"Ошибка при получении похожих фильмов: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": "Ошибка при получении похожих фильмов"}
        )


@movies_router.get(
    "/stats/top",
    tags=["Аналитика"],
    summary="Топ фильмов",
    description="Получить топ фильмов по рейтингу с возможностью фильтрации по году и жанру",
    dependencies=[Security(api_key_header)],
)
@cache(ttl=900)
async def get_top_movies(
    year: Optional[int] = None,
    genre: Optional[str] = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    try:
        # Ограничиваем лимит до 50
        if limit <= 0:
            limit = 10
        elif limit > 50:
            limit = 50

        # Строим базовый запрос
        query = select(Movie).order_by(desc(Movie.rating))

        # Применяем фильтры
        if year:
            query = query.filter(Movie.year == year)

        if genre:
            query = (
                query.join(movie_genres, Movie.id == movie_genres.c.movie_id)
                .join(Genre, movie_genres.c.genre_id == Genre.id)
                .filter(Genre.name.ilike(f"%{genre}%"))
            )

        # Применяем лимит и выполняем запрос
        query = query.limit(limit)
        result = await db.execute(query)
        movies = result.scalars().all()

        # Формируем ответ
        formatted_movies = []
        for movie in movies:
            # Получаем жанры для фильма
            genres_result = await db.execute(
                select(Genre.name)
                .join(movie_genres, Genre.id == movie_genres.c.genre_id)
                .where(movie_genres.c.movie_id == movie.id)
            )
            genres = [genre[0] for genre in genres_result.fetchall()]

            movie_data = {
                "id": movie.id,
                "title": movie.title,
                "year": movie.year,
                "genres": genres,
                "rating": movie.rating,
                "created_at": (
                    movie.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if movie.created_at
                    else None
                ),
            }

            # Добавляем необязательные поля только если они не пустые
            if movie.original_title:
                movie_data["original_title"] = movie.original_title

            if movie.description and movie.description.strip():
                movie_data["description"] = movie.description

            formatted_movies.append(movie_data)

        return JSONResponse(
            content={
                "count": len(formatted_movies),
                "filters": {"year": year, "genre": genre, "limit": limit},
                "top_movies": formatted_movies,
            }
        )
    except Exception as e:
        logger.error(f"Ошибка при получении топ фильмов: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": "Ошибка при получении топ фильмов"}
        )


@movies_router.get(
    "/stats/genres",
    tags=["Аналитика"],
    summary="Статистика по жанрам",
    description="Получить статистику по жанрам: количество фильмов в каждом жанре",
    dependencies=[Security(api_key_header)],
)
async def get_genre_stats(db: AsyncSession = Depends(get_db)):
    try:
        # Выполняем запрос для подсчета фильмов по жанрам
        query = (
            select(Genre.name, func.count(Movie.id).label("movie_count"))
            .join(movie_genres, Genre.id == movie_genres.c.genre_id)
            .join(Movie, movie_genres.c.movie_id == Movie.id)
            .group_by(Genre.name)
            .order_by(desc("movie_count"))
        )

        result = await db.execute(query)
        genre_stats = result.fetchall()

        # Формируем ответ
        formatted_stats = [
            {"genre": item[0], "movie_count": item[1]} for item in genre_stats
        ]

        return JSONResponse(
            content={
                "total_genres": len(formatted_stats),
                "genre_stats": formatted_stats,
            }
        )
    except Exception as e:
        logger.error(f"Ошибка при получении статистики по жанрам: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Ошибка при получении статистики по жанрам"},
        )


@movies_router.get(
    "/filter",
    tags=["Поиск"],
    summary="Расширенная фильтрация фильмов",
    description="Фильтрация фильмов по различным параметрам с возможностью сортировки и пагинации",
    dependencies=[Security(api_key_header)],
)
async def filter_movies(
    title: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    rating_from: Optional[int] = None,
    genre: Optional[str] = None,
    sort_by: str = "rating",  # rating, year, title
    sort_order: str = "desc",  # asc, desc
    page: int = 1,
    page_size: int = 10,
    db: AsyncSession = Depends(get_db),
):
    try:
        # Проверяем параметры пагинации
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 10
        if page_size > 50:
            page_size = 50

        # Строим базовый запрос
        query = select(Movie)
        count_query = select(func.count()).select_from(Movie)

        # Применяем фильтры
        filters = []
        if title:
            title_filter = or_(
                Movie.title.ilike(f"%{title}%"),
                Movie.original_title.ilike(f"%{title}%"),
            )
            filters.append(title_filter)

        if year_from:
            filters.append(Movie.year >= year_from)

        if year_to:
            filters.append(Movie.year <= year_to)

        if rating_from:
            filters.append(Movie.rating >= rating_from)

        # Применяем все добавленные фильтры
        for f in filters:
            query = query.filter(f)
            count_query = count_query.filter(f)

        # Если указан жанр, фильтруем по нему
        if genre:
            query = (
                query.join(movie_genres, Movie.id == movie_genres.c.movie_id)
                .join(Genre, movie_genres.c.genre_id == Genre.id)
                .filter(Genre.name.ilike(f"%{genre}%"))
            )
            count_query = (
                count_query.join(movie_genres, Movie.id == movie_genres.c.movie_id)
                .join(Genre, movie_genres.c.genre_id == Genre.id)
                .filter(Genre.name.ilike(f"%{genre}%"))
            )

        # Применяем сортировку
        if sort_by == "year":
            sort_column = Movie.year
        elif sort_by == "title":
            sort_column = Movie.title
        else:  # По умолчанию сортируем по рейтингу
            sort_column = Movie.rating

        if sort_order.lower() == "asc":
            query = query.order_by(sort_column)
        else:
            query = query.order_by(desc(sort_column))

        # Получаем общее количество результатов
        count_result = await db.execute(count_query)
        total_count = count_result.scalar()

        # Применяем пагинацию
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # Выполняем запрос
        result = await db.execute(query)
        movies = result.scalars().all()

        # Формируем ответ
        formatted_movies = []
        for movie in movies:
            # Получаем жанры для фильма
            genres_result = await db.execute(
                select(Genre.name)
                .join(movie_genres, Genre.id == movie_genres.c.genre_id)
                .where(movie_genres.c.movie_id == movie.id)
            )
            genres = [genre[0] for genre in genres_result.fetchall()]

            movie_data = {
                "id": movie.id,
                "title": movie.title,
                "year": movie.year,
                "genres": genres,
                "rating": movie.rating,
                "created_at": (
                    movie.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if movie.created_at
                    else None
                ),
            }

            # Добавляем необязательные поля только если они не пустые
            if movie.original_title:
                movie_data["original_title"] = movie.original_title

            if movie.description and movie.description.strip():
                movie_data["description"] = movie.description

            formatted_movies.append(movie_data)

        # Рассчитываем информацию о пагинации
        total_pages = (total_count + page_size - 1) // page_size  # Округление вверх

        return JSONResponse(
            content={
                "count": len(formatted_movies),
                "total_count": total_count,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                },
                "filters": {
                    "title": title,
                    "year_from": year_from,
                    "year_to": year_to,
                    "rating_from": rating_from,
                    "genre": genre,
                },
                "sort": {"sort_by": sort_by, "sort_order": sort_order},
                "movies": formatted_movies,
            }
        )
    except Exception as e:
        logger.error(f"Ошибка при фильтрации фильмов: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": "Ошибка при фильтрации фильмов"}
        )


@movies_router.get(
    "/{movie_id}/full",
    tags=["Фильмы"],
    summary="Полная информация о фильме",
    description="Получить расширенную информацию о фильме, включая актёров, режиссёров и страны",
    dependencies=[Security(api_key_header)],
)
async def get_movie_full_info(movie_id: int, db: AsyncSession = Depends(get_db)):
    try:
        # Проверяем существование фильма
        movie_result = await db.execute(select(Movie).where(Movie.id == movie_id))
        movie = movie_result.scalars().first()

        if not movie:
            return JSONResponse(status_code=404, content={"message": "Фильм не найден"})

        # Получаем жанры фильма
        genres_result = await db.execute(
            select(Genre.name)
            .join(movie_genres, Genre.id == movie_genres.c.genre_id)
            .where(movie_genres.c.movie_id == movie_id)
        )
        genres = [genre[0] for genre in genres_result.fetchall()]

        # Получаем актёров фильма
        actors_result = await db.execute(
            select(Actor.name)
            .join(movie_actors, Actor.id == movie_actors.c.actor_id)
            .where(movie_actors.c.movie_id == movie_id)
        )
        actors = [actor[0] for actor in actors_result.fetchall()]

        # Получаем режиссёров фильма
        directors_result = await db.execute(
            select(Director.name)
            .join(movie_directors, Director.id == movie_directors.c.director_id)
            .where(movie_directors.c.movie_id == movie_id)
        )
        directors = [director[0] for director in directors_result.fetchall()]

        # Получаем страны фильма
        countries_result = await db.execute(
            select(Country.name)
            .join(movie_countries, Country.id == movie_countries.c.country_id)
            .where(movie_countries.c.movie_id == movie_id)
        )
        countries = [country[0] for country in countries_result.fetchall()]

        # Формируем ответ
        movie_data = {
            "id": movie.id,
            "title": movie.title,
            "year": movie.year,
            "rating": movie.rating,
            "genres": genres,
            "actors": actors,
            "directors": directors,
            "countries": countries,
            "created_at": (
                movie.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if movie.created_at
                else None
            ),
        }

        # Добавляем необязательные поля только если они не пустые
        if movie.original_title:
            movie_data["original_title"] = movie.original_title

        if movie.description and movie.description.strip():
            movie_data["description"] = movie.description

        return JSONResponse(content=movie_data)
    except Exception as e:
        logger.error(f"Ошибка при получении полной информации о фильме: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Ошибка при получении полной информации о фильме"},
        )


@api_router.get(
    "/usage",
    tags=["Аналитика"],
    summary="Статистика использования API",
    description="Возвращает информацию о текущем использовании API ключа",
    dependencies=[Security(api_key_header)],
)
async def get_api_usage(request: Request):
    api_key = request.headers.get("X-API-Key")

    if not api_key:
        raise HTTPException(status_code=401, detail="API key is required")

    # Получаем информацию об использовании
    count, limit, reset_time = await rate_limiter.get_usage_info(api_key)

    # Форматируем дату сброса
    reset_date = datetime.fromtimestamp(reset_time).strftime("%Y-%m-%d %H:%M:%S UTC")

    return JSONResponse(
        content={
            "api_usage": {
                "requests_used": count,
                "monthly_limit": limit,
                "requests_remaining": limit - count,
                "usage_percent": round((count / limit) * 100, 2) if limit > 0 else 0,
                "reset_date": reset_date,
                "reset_timestamp": reset_time,
            }
        }
    )

