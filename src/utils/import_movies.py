import asyncio
import json
import sys
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from models import Base, Movie, Genre, Country, Director, Actor
from db import engine, AsyncSessionLocal


async def import_movies_data(json_data: list) -> None:
    async with AsyncSessionLocal() as session:
        try:
            for movie_data in json_data:
                # Проверяем, существует ли фильм
                existing_movie = await session.execute(
                    select(Movie).where(
                        Movie.title == movie_data["title"],
                        Movie.year == movie_data["year"],
                    )
                )
                if existing_movie.scalar_one_or_none():
                    print(f"Фильм {movie_data['title']} уже существует, пропускаем...")
                    continue

                # Создаем новый фильм
                movie = Movie(
                    title=movie_data["title"],
                    original_title=movie_data["original_title"],
                    year=movie_data["year"],
                    rating=movie_data["rating"],
                )
                session.add(movie)

                # Добавляем жанры
                for genre_name in movie_data["genres"]:
                    genre = await get_or_create(session, Genre, name=genre_name)
                    movie.genres.append(genre)

                # Добавляем страны
                for country_name in movie_data["countries"]:
                    country = await get_or_create(session, Country, name=country_name)
                    movie.countries.append(country)

                # Добавляем режиссеров
                for director_name in movie_data["directors"]:
                    director = await get_or_create(
                        session, Director, name=director_name
                    )
                    movie.directors.append(director)

                # Добавляем актеров
                for actor_name in movie_data["actors"]:
                    actor = await get_or_create(session, Actor, name=actor_name)
                    movie.actors.append(actor)

            await session.commit()
            print("Данные успешно импортированы!")

        except Exception as e:
            print(f"Ошибка при импорте данных: {e}")
            await session.rollback()
            raise


async def get_or_create(session: AsyncSession, model, **kwargs):
    """Получает существующий объект из БД или создает новый."""
    result = await session.execute(
        select(model).where(*[getattr(model, k) == v for k, v in kwargs.items()])
    )
    instance = result.scalar_one_or_none()
    if instance is None:
        instance = model(**kwargs)
        session.add(instance)
        await session.flush()
    return instance


async def main():
    # Создаем таблицы если они не существуют
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Читаем JSON файл
    try:
        with open("movies.json", "r", encoding="utf-8") as f:
            movies_data = json.load(f)
        await import_movies_data(movies_data)
    except FileNotFoundError:
        print("Файл movies.json не найден!")
    except json.JSONDecodeError:
        print("Ошибка при чтении JSON файла!")
    except Exception as e:
        print(f"Произошла ошибка: {e}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
