r"""Консольный чат с консультантом.

Запуск:  .venv\Scripts\python chat.py
Выход:   напиши «выход» или нажми Ctrl+C.
"""
import sys
import warnings

warnings.filterwarnings("ignore")  # прячем предупреждение про сертификат, см. README
sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")

from shop.agent import ShopAgent  # noqa: E402

agent = ShopAgent()
print(f"Консультант магазина «Старт» (модель {agent.model}). Чем помочь?\n")
try:
    while True:
        text = input("Вы: ").strip()
        if not text:
            continue
        if text.lower() in {"выход", "exit", "quit"}:
            break
        print(f"Консультант: {agent.ask(text)}\n")
except (KeyboardInterrupt, EOFError):
    pass
finally:
    t = agent.tokens
    print(f"\nТокенов за разговор: вопрос {t['prompt']}, ответ {t['completion']}, всего {t['prompt'] + t['completion']}")
    agent.close()
