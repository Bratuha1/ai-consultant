r"""Замер расхода токенов на типовых разговорах — для расчёта стоимости в README.

Запуск:  .venv\Scripts\python measure_tokens.py

Каждый сценарий — отдельный разговор (новый агент). Печатаем, сколько токенов
ушло на каждый вопрос и на весь разговор. Обращения к модели настоящие,
поэтому цифры немного плавают от запуска к запуску.
"""
import sys
import warnings

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

from shop.agent import ShopAgent  # noqa: E402

SCENARIOS = {
    "Вопрос про условия": [
        "Сколько стоит доставка и можно ли вернуть товар?",
    ],
    "Подбор товара": [
        "Нужны беговые кроссовки до 8000, размер 42",
        "А Asics есть в 43 размере?",
    ],
    "Подбор + КП": [
        "Нужны беговые кроссовки до 8000, размер 42",
        "Давайте Nike, соберите КП, доставка курьером, меня зовут Ирина",
    ],
    "Оптовое КП для секции": [
        "Для секции: 5 футбольных мячей и 8 скакалок, соберите КП",
    ],
}

grand = {"prompt": 0, "completion": 0, "questions": 0}
for title, questions in SCENARIOS.items():
    agent = ShopAgent(verbose=False)
    print(f"\n=== {title} ===")
    before = 0
    for q in questions:
        tools_before = len(agent.tool_log)
        agent.ask(q)
        total = agent.tokens["prompt"] + agent.tokens["completion"]
        tools = [s["tool"] for s in agent.tool_log[tools_before:]]
        print(f"  «{q[:45]}»: {total - before} токенов, инструменты: {', '.join(tools) or '—'}")
        before = total
    t = agent.tokens
    print(f"  ИТОГО: вопрос {t['prompt']}, ответ {t['completion']}, всего {t['prompt'] + t['completion']}")
    grand["prompt"] += t["prompt"]
    grand["completion"] += t["completion"]
    grand["questions"] += len(questions)
    agent.close()

all_tokens = grand["prompt"] + grand["completion"]
print(f"\nВсего: {all_tokens} токенов на {grand['questions']} вопросов "
      f"≈ {all_tokens // grand['questions']} на вопрос "
      f"(отправлено {grand['prompt']}, сгенерировано {grand['completion']})")
