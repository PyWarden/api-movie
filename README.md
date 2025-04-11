![Демонстрация](https://github.com/user-attachments/assets/ff8704f4-d5b4-4edc-bb29-64169cbe0fdd)

# 🎬 Movie API (FastAPI)

**Быстрый и функциональный REST API для доступа к данным о тысячах фильмов.**

![Главная страница](https://github.com/user-attachments/assets/0228ceda-a767-4f8a-bf6d-2afa845eb977)

Этот проект представляет собой современный RESTful API, построенный на FastAPI, для поиска, фильтрации и получения детальной информации о фильмах.

✨ **Ключевые особенности:**

*   🚀 **Высокая производительность:** Асинхронность FastAPI и кэширование Redis.
*   🔑 **Бесплатный доступ:** Регистрация и получение API ключа с лимитом 1000 запросов/месяц.
*   🛡️ **Безопасность:** Защита регистрации Cloudflare Turnstile, хеширование паролей, ограничение запросов.
*   🔎 **Гибкий поиск и фильтрация:** Находите фильмы по названию, году, жанру, рейтингу и другим параметрам.
*   📊 **Статистика и Аналитика:** Эндпоинты для получения топ-фильмов и статистики по жанрам.
*   📚 **Авто-документация:** Интерактивная документация API (Swagger UI) доступна по `/docs`.
*   🐳 **Простой запуск:** Полностью контейнеризировано с Docker Compose.

---

### 🛠️ Технологический Стек

*   **Backend:** ![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white) ![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat&logo=sqlalchemy&logoColor=white)
*   **База данных:** ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white)
*   **Кэш / Rate Limiting:** ![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=flat&logo=redis&logoColor=white)
*   **Контейнеризация:** ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)
*   **Frontend (Шаблоны):** ![HTML5](https://img.shields.io/badge/html5-%23E34F26.svg?style=flat&logo=html5&logoColor=white) ![CSS3](https://img.shields.io/badge/css3-%231572B6.svg?style=flat&logo=css3&logoColor=white) ![JavaScript](https://img.shields.io/badge/javascript-%23323330.svg?style=flat&logo=javascript&logoColor=%23F7DF1E)

---

### 🚀 Как запустить локально

1.  **Клонируйте репозиторий:**
    ```bash
    git clone https://github.com/PyWarden/api-movie.git
    cd movie-api
    ```
2.  **Создайте файл конфигурации:**
    Заполните файл config.json

3.  **Запустите с помощью Docker Compose:**
    ```bash
    docker-compose up -d --build
    ```


### Лицензия

Этот проект распространяется под лицензией MIT.
