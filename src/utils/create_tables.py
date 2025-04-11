import asyncio
import sys
from models import Base
from db import engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_tables():
    try:
        async with engine.begin() as conn:
            # Удаляем таблицы по одной
            logger.info("Dropping all tables...")
            drop_tables = [
                "movie_actors",
                "movie_directors",
                "movie_genres",
                "movie_countries",
                "movies",
                "actors",
                "directors",
                "genres",
                "countries",
                "users",
            ]

            for table in drop_tables:
                try:
                    await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                    logger.info(f"Dropped table {table}")
                except Exception as e:
                    logger.warning(f"Error dropping table {table}: {str(e)}")

            logger.info("Creating all tables...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Tables created successfully!")

    except Exception as e:
        logger.error(f"Error creating tables: {str(e)}")
        raise


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(create_tables())
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
