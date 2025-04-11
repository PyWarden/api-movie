import uuid
import hashlib
import secrets
import json
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from passlib.context import CryptContext
from fastapi import Depends
from typing import Union
from ..db.models import User
from ..db.schemas import UserCreate
from ..db.db import get_db
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


# --- Загрузка конфигурации ---
def load_config():
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.json"
    )  # Путь к config.json в корне
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
email_config = config.get("email_config") if config else None
# -----------------------------

# Контекст для хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    # Конструктор __init__ не нужен, если все методы статические

    @staticmethod
    async def send_api_key_email(user_email: str, username: str, api_key: str):
        if not email_config or not all(
            k in email_config
            for k in ("smtp_server", "smtp_port", "sender_email", "app_password")
        ):
            logger.error(
                "Email configuration is missing or incomplete in config.json. Cannot send email."
            )
            return

        # Проверка, что пароль не является плейсхолдером
        if email_config["app_password"] == "YOUR_YANDEX_APP_PASSWORD":
            logger.error(
                "Placeholder Yandex app password detected in config.json. Please replace it with a real app password."
            )
            return

        smtp_server = email_config["smtp_server"]
        smtp_port = email_config["smtp_port"]
        sender_email = email_config["sender_email"]
        app_password = email_config["app_password"]

        # Создаем HTML версию письма
        html = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 20px auto;
                    padding: 20px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                }}
                .api-key {{
                    background: #f5f5f5;
                    padding: 15px;
                    border-radius: 4px;
                    font-family: monospace;
                    margin: 15px 0;
                }}
                .warning {{
                    color: #dc3545;
                    margin-top: 15px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Добро пожаловать в Movie API!</h2>
                <p>Здравствуйте, {username}!</p>
                <p>Спасибо за регистрацию в нашем сервисе. Ваш API ключ:</p>

                <div class="api-key">
                    {api_key}
                </div>

                <p class="warning">
                    ⚠️ Важно: Сохраните этот ключ в надежном месте. 
                    Он будет необходим для доступа к API.
                </p>

                <p>С этим ключом вы можете:</p>
                <ul>
                    <li>Получать информацию о фильмах</li>
                    <li>Добавлять новые фильмы</li>
                    <li>Использовать все возможности нашего API</li>
                </ul>

                <p>Если у вас возникнут вопросы, не стесняйтесь обращаться в нашу службу поддержки.</p>
            </div>
        </body>
        </html>
        """

        # Создаем сообщение
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Ваш API ключ Movie API"
        msg["From"] = sender_email
        msg["To"] = user_email

        # Добавляем HTML версию
        msg.attach(MIMEText(html, "html"))

        try:
            # Подключаемся к SMTP серверу
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(sender_email, app_password)

            # Отправляем письмо
            server.send_message(msg)
            server.quit()
            logger.info(f"API key email successfully sent to {user_email}")
        except smtplib.SMTPAuthenticationError:
            logger.error(
                f"SMTP authentication failed for {sender_email}. Check email/password in config.json."
            )
        except Exception as e:
            logger.error(f"Error sending email to {user_email}: {str(e)}")

    @staticmethod
    async def get_user_by_username(
        db: AsyncSession, username: str
    ) -> Union[User, None]:
        result = await db.execute(select(User).filter(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Union[User, None]:
        result = await db.execute(select(User).filter(User.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
        logger.info(f"Начинаем создание пользователя: {user_data.username}")
        try:
            # Проверка сложности пароля
            if len(user_data.password) < 8:
                logger.warning(f"Пароль для {user_data.username} слишком короткий.")
                raise ValueError("Пароль должен содержать не менее 8 символов")
            logger.info("Проверка длины пароля пройдена.")

            # Хеширование пароля
            logger.info("Начинаем хеширование пароля...")
            hashed_password = pwd_context.hash(user_data.password)
            logger.info("Хеширование пароля завершено.")

            # Генерация API ключа
            api_key = secrets.token_urlsafe(32)
            logger.info("API ключ сгенерирован.")

            # Создание объекта модели User
            db_user = User(
                username=user_data.username,
                email=user_data.email,
                password_hash=hashed_password,
                api_key=api_key,
                daily_request_limit=1000,
            )
            logger.info("Объект User создан.")

            # Добавление в сессию
            db.add(db_user)
            logger.info("Пользователь добавлен в сессию.")

            # Коммит и рефреш
            logger.info("Начинаем commit...")
            await db.commit()
            logger.info("Commit завершен.")
            logger.info("Начинаем refresh...")
            await db.refresh(db_user)
            logger.info("Refresh завершен.")

            # --- Отправка email после успешного создания пользователя ---
            try:
                logger.info(f"Attempting to send API key email to {db_user.email}...")
                await UserService.send_api_key_email(
                    user_email=db_user.email,
                    username=db_user.username,
                    api_key=db_user.api_key,
                )
                # Лог об успешной отправке теперь внутри send_api_key_email
            except Exception as email_error:
                # Логируем ошибку отправки, но не прерываем процесс регистрации
                logger.error(
                    f"Failed attempt to send API key email for {db_user.username} to {db_user.email}: {email_error}",
                    exc_info=True,
                )
            # --------------------------------------------------------------

            logger.info(f"User {user_data.username} successfully created.")
            return db_user

        except ValueError as ve:  # Перехватываем ValueError от проверки пароля
            logger.error(
                f"Validation error during user creation {user_data.username}: {ve}"
            )
            raise  # Передаем дальше, чтобы routes.py вернул 400

        except Exception as e:
            logger.error(
                f"Unexpected error saving user {user_data.username} to DB: {e}",
                exc_info=True,
            )  # exc_info=True для полного трейсбека
            logger.info("Rolling back transaction...")
            await db.rollback()  # Откатываем транзакцию
            logger.info("Rollback complete.")
            raise  # Передаем исключение дальше, чтобы routes.py вернул 500

    @staticmethod
    def verify_password(stored_password: str, provided_password: str) -> bool:
        return pwd_context.verify(provided_password, stored_password)

    @staticmethod
    async def get_user_by_api_key(db: AsyncSession, api_key: str) -> Union[User, None]:
        result = await db.execute(select(User).filter(User.api_key == api_key))
        return result.scalars().first()
