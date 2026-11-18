"""Проверка связи с GigaChat: отправляем одно сообщение и печатаем ответ.

Запуск:  .venv\Scripts\python hello_gigachat.py
"""
import os
import sys

from dotenv import load_dotenv
from gigachat import GigaChat

# Чтобы русские буквы нормально печатались в консоли Windows
sys.stdout.reconfigure(encoding="utf-8")

# 1. Читаем ключ из файла .env (он не попадает на GitHub)
load_dotenv()
credentials = os.getenv("GIGACHAT_CREDENTIALS")
if not credentials:
    sys.exit("Нет ключа: впиши GIGACHAT_CREDENTIALS в файл .env")

# 2. Подключаемся к GigaChat
#    scope GIGACHAT_API_PERS — тариф для физлиц.
#    verify_ssl_certs=False — временно, пока не поставим сертификат Минцифры
#    (у Сбера свой сертификат, которого Python по умолчанию не знает).
#    Модель берём из .env (GIGACHAT_MODEL), чтобы менять её без правки кода.
model = os.getenv("GIGACHAT_MODEL", "GigaChat-2")
print("Модель:", model)

with GigaChat(
    credentials=credentials,
    model=model,
    scope="GIGACHAT_API_PERS",
    verify_ssl_certs=False,
) as giga:
    # 3. Отправляем сообщение и печатаем ответ
    response = giga.chat("Привет! Ответь одним предложением: кто ты?")
    print("Ответ:", response.choices[0].message.content)

    # 4. Сколько токенов ушло — пригодится для расчёта стоимости
    u = response.usage
    print(f"Токены: вопрос {u.prompt_tokens}, ответ {u.completion_tokens}, всего {u.total_tokens}")
