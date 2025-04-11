import redis
import os

# Создайте новый файл для тестирования Redis
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
print(f"Попытка подключения к Redis: {redis_url}")

r = redis.from_url(redis_url)

try:
    # Тест подключения
    ping = r.ping()
    print(f"Подключение к Redis: {ping}")

    # Тест записи
    r.set("test_key", "test_value")
    print(f"Тест записи: {r.get('test_key')}")

    # Тест инкремента
    r.set("test_counter", 0)
    new_value = r.incr("test_counter")
    print(f"Тест инкремента: {new_value}")

    # Проверка всех ключей
    keys = r.keys("*")
    print(f"Все ключи в Redis: {keys}")

except Exception as e:
    print(f"Ошибка при работе с Redis: {str(e)}")
