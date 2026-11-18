r"""Тесты инструментов. Запуск:  .venv\Scripts\python -m pytest

Модель тут не участвует: проверяем, что функции сами по себе
считают и ищут правильно. Токены не тратятся.
"""
import pytest

from shop import tools


@pytest.fixture(autouse=True)
def quotes_in_tmp(tmp_path, monkeypatch):
    """КП в тестах сохраняем во временную папку, чтобы не мусорить."""
    monkeypatch.setattr(tools, "QUOTES_DIR", tmp_path)


def test_search_finds_running_shoes_under_budget():
    result = tools.search_products("беговые кроссовки", max_price=8000)
    ids = [p["id"] for p in result["products"]]
    assert "SH-001" in ids and "SH-002" in ids
    assert "SH-003" not in ids  # 11 990 ₽ — дороже бюджета


def test_search_by_category():
    result = tools.search_products(category="инвентарь", max_price=1000)
    assert {p["id"] for p in result["products"]} == {"EQ-003"}


def test_search_nothing_found():
    assert tools.search_products("сноуборд")["found"] == 0


def test_check_stock_size():
    assert tools.check_stock("SH-001", "42")["available"] == 2
    assert tools.check_stock("SH-001", "41")["available"] == 0
    assert tools.check_stock("CL-002", "m")["available"] == 3  # размер строчными


def test_check_stock_unknown_product():
    assert "error" in tools.check_stock("XX-999")


def test_policy_and_unknown_topic():
    assert "390" in tools.get_policy("Доставка")["text"]
    assert "available_topics" in tools.get_policy("кешбэк")


@pytest.mark.parametrize("subtotal, percent", [(14999, 0), (15000, 5), (29999, 5), (30000, 10)])
def test_discount_thresholds(subtotal, percent):
    assert tools.calc_discount(subtotal)[0] == percent


def test_quote_small_order_pays_delivery(tmp_path):
    q = tools.make_quote([{"product_id": "AC-001", "size": "39-42", "qty": 2}])
    assert q["subtotal"] == 780
    assert q["delivery_cost"] == 390
    assert q["grand_total"] == 1170
    assert len(list(tmp_path.iterdir())) == 1  # файл КП создан


def test_quote_discount_and_free_delivery():
    q = tools.make_quote([
        {"product_id": "EQ-006", "qty": 1},              # 24 990, без размера
        {"product_id": "SH-001", "size": "42", "qty": 1},  # 6 990
    ])
    assert q["subtotal"] == 31980
    assert q["discount_percent"] == 10
    assert q["grand_total"] == 31980 - 3198  # доставка бесплатная


def test_quote_rejects_out_of_stock_and_missing_size():
    q = tools.make_quote([
        {"product_id": "SH-001", "size": "41", "qty": 1},  # нет в наличии
        {"product_id": "CL-001", "qty": 1},                # не указан размер
    ])
    assert q["error"] == "КП не собрано"
    assert len(q["problems"]) == 2


def test_quote_file_keeps_shop_address_commas(tmp_path):
    tools.make_quote([{"product_id": "EQ-002", "qty": 1}], customer="Иванов, ИП")
    text = next(tmp_path.iterdir()).read_text(encoding="utf-8")
    assert "Иванов, ИП" in text
    assert "ул. Малышева, 51" in text
    assert "1 490 ₽" in text
