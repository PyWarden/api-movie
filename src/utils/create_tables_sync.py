from sqlalchemy import create_engine
from models import Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Используем синхронное подключение
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/moviedb"


def create_tables():
    try:
        # Создаем синхронный движок
        engine = create_engine(DATABASE_URL, echo=True)

        logger.info("Dropping all tables...")
        Base.metadata.drop_all(engine)

        logger.info("Creating all tables...")
        Base.metadata.create_all(engine)

        logger.info("Tables created successfully!")

    except Exception as e:
        logger.error(f"Error creating tables: {str(e)}")
        raise


if __name__ == "__main__":
    try:
        create_tables()
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
