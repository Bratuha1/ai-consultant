r"""Веб-интерфейс консультанта (для демо-видео и питча).

Запуск:  .venv\Scripts\python app.py
Открыть: http://127.0.0.1:5000

Как устроено:
- Flask — маленький веб-сервер на Python. Он отдаёт страницу (templates/index.html)
  и принимает вопросы по адресу /api/ask.
- Страница в браузере отправляет вопрос, сервер передаёт его агенту (ShopAgent)
  и возвращает ответ + список инструментов, которые агент вызвал по пути.
- У каждой вкладки браузера свой разговор: страница при открытии придумывает
  случайный id сессии, а сервер хранит по нему отдельного агента.
"""
import warnings

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from shop.agent import ShopAgent
from shop.tools import QUOTES_DIR

warnings.filterwarnings("ignore")  # прячем предупреждение про сертификат, см. README

app = Flask(__name__)
agents: dict[str, ShopAgent] = {}  # id сессии → агент со своей историей переписки


def get_agent(session_id: str) -> ShopAgent:
    """Находит агента для этой вкладки или создаёт нового."""
    if session_id not in agents:
        agents[session_id] = ShopAgent(verbose=True)  # verbose: вызовы видны и в консоли
    return agents[session_id]


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/ask")
def ask():
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    session_id = data.get("session_id") or "default"
    if not text:
        return jsonify({"error": "Пустой вопрос"}), 400

    agent = get_agent(session_id)
    steps_before = len(agent.tool_log)  # чтобы вернуть только вызовы для ЭТОГО вопроса
    try:
        answer = agent.ask(text)
    except Exception as e:  # сеть, ключ, лимиты GigaChat — показываем, а не падаем
        return jsonify({"error": f"Ошибка при обращении к модели: {e}"}), 500

    return jsonify({
        "answer": answer,
        "steps": agent.tool_log[steps_before:],
        "tokens": agent.tokens,
        "model": agent.model,
    })


@app.post("/api/reset")
def reset():
    """Кнопка «Новый разговор»: забываем агента этой вкладки."""
    session_id = (request.get_json(force=True) or {}).get("session_id")
    agent = agents.pop(session_id, None)
    if agent:
        agent.close()
    return jsonify({"ok": True})


@app.get("/quotes/<path:name>")
def quote_file(name):
    """Скачать сохранённое КП (файл .md из папки quotes)."""
    if not name.endswith(".md"):
        abort(404)
    return send_from_directory(QUOTES_DIR, name, as_attachment=True)


if __name__ == "__main__":
    # debug=False: иначе Flask запускает сервер дважды и создаёт лишних агентов
    app.run(host="127.0.0.1", port=5000, debug=False)
