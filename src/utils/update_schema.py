import asyncio
import sys
from sqlalchemy import text
from db import engine


async def update_database_schema():
    async with engine.begin() as conn:
        # Обновляем таблицу movies
        await conn.execute(
            text(
                """
            ALTER TABLE movies 
            ADD COLUMN IF NOT EXISTS original_title VARCHAR(255),
            ADD COLUMN IF NOT EXISTS year INTEGER,
            ADD COLUMN IF NOT EXISTS rating DECIMAL(4,3),
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ADD COLUMN IF NOT EXISTS description TEXT
        """
            )
        )

        # Создаем таблицу жанров
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS genres (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL
            )
        """
            )
        )

        # Создаем таблицу стран
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS countries (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL
            )
        """
            )
        )

        # Создаем таблицу режиссеров
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS directors (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL
            )
        """
            )
        )

        # Создаем таблицу актеров
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS actors (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL
            )
        """
            )
        )

        # Создаем связующую таблицу movie_genres
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS movie_genres (
                movie_id INTEGER REFERENCES movies(id) ON DELETE CASCADE,
                genre_id INTEGER REFERENCES genres(id) ON DELETE CASCADE,
                PRIMARY KEY (movie_id, genre_id)
            )
        """
            )
        )

        # Создаем связующую таблицу movie_countries
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS movie_countries (
                movie_id INTEGER REFERENCES movies(id) ON DELETE CASCADE,
                country_id INTEGER REFERENCES countries(id) ON DELETE CASCADE,
                PRIMARY KEY (movie_id, country_id)
            )
        """
            )
        )

        # Создаем связующую таблицу movie_directors
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS movie_directors (
                movie_id INTEGER REFERENCES movies(id) ON DELETE CASCADE,
                director_id INTEGER REFERENCES directors(id) ON DELETE CASCADE,
                PRIMARY KEY (movie_id, director_id)
            )
        """
            )
        )

        # Создаем связующую таблицу movie_actors
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS movie_actors (
                movie_id INTEGER REFERENCES movies(id) ON DELETE CASCADE,
                actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
                PRIMARY KEY (movie_id, actor_id)
            )
        """
            )
        )

        print("Структура базы данных успешно обновлена!")


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(update_database_schema())
