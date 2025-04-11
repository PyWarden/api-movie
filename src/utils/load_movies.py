import asyncio
import json
import sys
from sqlalchemy import select
from db import AsyncSessionLocal
from models import Movie, Genre, Country, Director, Actor
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def load_movies():
    try:
        # Читаем JSON файл
        with open("movies.json", "r", encoding="utf-8") as f:
            movies_data = json.load(f)

        async with AsyncSessionLocal() as session:
            for movie_data in movies_data:
                # Создаем или получаем жанры
                genres = []
                for genre_name in movie_data.get("genres", []):
                    if genre_name:
                        stmt = select(Genre).where(Genre.name == genre_name)
                        result = await session.execute(stmt)
                        genre = result.scalar()
                        if not genre:
                            genre = Genre(name=genre_name)
                            session.add(genre)
                            await session.flush()
                        genres.append(genre)

                # Создаем или получаем страны
                countries = []
                for country_name in movie_data.get("countries", []):
                    if country_name:
                        stmt = select(Country).where(Country.name == country_name)
                        result = await session.execute(stmt)
                        country = result.scalar()
                        if not country:
                            country = Country(name=country_name)
                            session.add(country)
                            await session.flush()
                        countries.append(country)

                # Создаем или получаем режиссеров
                directors = []
                for director_name in movie_data.get("directors", []):
                    if director_name:
                        stmt = select(Director).where(Director.name == director_name)
                        result = await session.execute(stmt)
                        director = result.scalar()
                        if not director:
                            director = Director(name=director_name)
                            session.add(director)
                            await session.flush()
                        directors.append(director)

                # Создаем или получаем актеров
                actors = []
                for actor_name in movie_data.get("actors", []):
                    if actor_name:
                        stmt = select(Actor).where(Actor.name == actor_name)
                        result = await session.execute(stmt)
                        actor = result.scalar()
                        if not actor:
                            actor = Actor(name=actor_name)
                            session.add(actor)
                            await session.flush()
                        actors.append(actor)

                # Создаем фильм
                movie = Movie(
                    title=movie_data["title"],
                    original_title=movie_data["original_title"],
                    description=None,
                    year=movie_data["year"],
                    rating=movie_data["rating"],
                    created_at=datetime.utcnow(),
                )

                # Добавляем связи
                movie.genres.extend(genres)
                movie.countries.extend(countries)
                movie.directors.extend(directors)
                movie.actors.extend(actors)

                session.add(movie)
                logger.info(f"Added movie: {movie.title}")

            # Сохраняем все изменения
            await session.commit()
            logger.info("Movies loaded successfully!")

    except Exception as e:
        logger.error(f"Error loading movies: {str(e)}")
        raise


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(load_movies())
