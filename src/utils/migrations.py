from sqlalchemy import create_engine, text
from db import DATABASE_URL

# Используем синхронный URL для PostgreSQL
sync_url = DATABASE_URL.replace("+asyncpg", "")
engine = create_engine(sync_url)


def run_migration():
    with engine.connect() as conn:
        # Добавляем новые колонки в таблицу users
        conn.execute(
            text(
                """
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN IF NOT EXISTS daily_request_limit INTEGER NOT NULL DEFAULT 1000,
            ADD COLUMN IF NOT EXISTS last_request_reset TIMESTAMP WITH TIME ZONE DEFAULT now()
        """
            )
        )

        # Создаем таблицу api_requests
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS api_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                endpoint VARCHAR,
                method VARCHAR,
                status_code INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
            )
        """
            )
        )

        # Создаем индекс
        conn.execute(
            text(
                """
            CREATE INDEX IF NOT EXISTS ix_api_requests_id ON api_requests (id)
        """
            )
        )

        conn.commit()


if __name__ == "__main__":
    run_migration()
