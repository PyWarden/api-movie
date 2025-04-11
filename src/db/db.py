import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from databases import Database
from dotenv import load_dotenv
from typing import AsyncGenerator

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://user:password@db/moviesdb"
)

# Проверяем URL для databases (должен быть без asyncpg)
DATABASE_URL_SYNC = SQLALCHEMY_DATABASE_URL.replace("+asyncpg", "")
database = Database(DATABASE_URL_SYNC)  # Используем URL без asyncpg для databases

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, echo=bool(os.getenv("DEBUG", False))
)
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


# Асинхронный генератор сессий
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()  # Опционально: commit после успешного yield
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Подключение/отключение для databases
async def connect_db():
    if not database.is_connected:
        await database.connect()


async def disconnect_db():
    if database.is_connected:
        await database.disconnect()
