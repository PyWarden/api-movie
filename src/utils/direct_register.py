import requests
import json
import random
import string
import sys

# URL для регистрации - измените на ваш URL
REGISTER_URL = "http://127.0.0.1:8000/register"


def generate_random_username():
    """Генерирует случайное имя пользователя"""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def register_user(username=None, password="password123"):
    """Отправляет запрос на регистрацию пользователя"""
    if not username:
        username = generate_random_username()

    payload = {"username": username, "password": password}

    # Дополнительные заголовки для эмуляции браузера
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        # Отправляем запрос на регистрацию
        response = requests.post(REGISTER_URL, json=payload, headers=headers)

        # Выводим информацию о запросе и ответе
        print(f"URL: {REGISTER_URL}")
        print(f"Запрос: {json.dumps(payload)}")
        print(f"Статус: {response.status_code}")
        print(f"Заголовки: {dict(response.headers)}")

        # Пытаемся получить JSON-ответ
        try:
            resp_json = response.json()
            print(
                f"Ответ (JSON): {json.dumps(resp_json, ensure_ascii=False, indent=2)}"
            )

            if "token" in resp_json:
                print(f"\nПОЛУЧЕН ТОКЕН: {resp_json['token']}")
                with open("registered_token.txt", "w") as f:
                    f.write(f"{resp_json['username']},{resp_json['token']}")
                print(f"Токен сохранен в registered_token.txt")
        except:
            print(f"Ответ (текст): {response.text[:500]}...")

        return response
    except Exception as e:
        print(f"Ошибка при отправке запроса: {str(e)}")
        return None


if __name__ == "__main__":
    # Можно передать имя пользователя как аргумент
    username = sys.argv[1] if len(sys.argv) > 1 else None

    print(
        f"Отправка запроса на регистрацию пользователя {'с именем ' + username if username else 'со случайным именем'}..."
    )
    register_user(username)
