"""Инструменты консультанта — обычные функции на Python, без всякого ИИ.

Модель сама их не выполняет. Она только говорит: «вызови search_products
с такими-то параметрами». Вызываем мы (в agent.py), а результат отдаём
модели обратно. Поэтому цены и наличие модель никогда не выдумывает —
она берёт их отсюда.
"""
import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
QUOTES_DIR = Path(__file__).parent.parent / "quotes"

# Загружаем базу знаний один раз при старте
PRODUCTS = json.loads((DATA_DIR / "products.json").read_text(encoding="utf-8"))
POLICIES = json.loads((DATA_DIR / "policies.json").read_text(encoding="utf-8"))
PRODUCTS_BY_ID = {p["id"]: p for p in PRODUCTS}

FREE_DELIVERY_FROM = 5000   # бесплатная доставка по Екатеринбургу от этой суммы
DELIVERY_PRICE = 390        # иначе курьер стоит столько


def money(amount: int) -> str:
    """12990 → «12 990 ₽» (как принято писать цены в России)."""
    return f"{amount:,} ₽".replace(",", " ")


def _sizes_in_stock(product):
    """Список размеров, которые есть на складе (остаток больше нуля)."""
    return [size for size, count in product["stock"].items() if count > 0]


def _short(product):
    """Короткая карточка товара для модели — только то, что нужно для ответа."""
    sizes = _sizes_in_stock(product)
    return {
        "id": product["id"],
        "name": product["name"],
        "price": product["price"],
        "in_stock": bool(sizes),
        # "one" значит «без размера» (гантели, бутылка и т.п.)
        "sizes_in_stock": [s for s in sizes if s != "one"],
    }


def search_products(query: str = "", category: str = "", max_price: int = 0, limit: int = 5):
    """Ищет товары по словам из запроса, категории и максимальной цене.

    Поиск простой: каждое слово запроса ищем в названии и тегах товара,
    сравнивая первые 4 буквы (так «кроссовки» найдёт и «кроссовок»).
    Умный поиск с опечатками и сленгом — это отдельный проект 2.
    """
    words = [w for w in query.lower().replace(",", " ").split() if len(w) > 1]
    results = []
    for product in PRODUCTS:
        if category and product["category"] != category.lower():
            continue
        if max_price and product["price"] > max_price:
            continue
        text = (product["name"] + " " + " ".join(product["tags"])).lower()
        text_words = text.split()
        # Счёт = сколько слов запроса нашлось в товаре
        score = sum(
            any(tw.startswith(w[:4]) for tw in text_words) for w in words
        )
        if words and score == 0:
            continue
        results.append((score, product))

    # Сначала самые подходящие, потом те, что в наличии, потом дешевле
    results.sort(key=lambda r: (-r[0], not _sizes_in_stock(r[1]), r[1]["price"]))
    found = [_short(p) for _, p in results[:limit]]
    return {"found": len(found), "products": found}


def check_stock(product_id: str, size: str = ""):
    """Проверяет наличие товара (и конкретного размера, если указан)."""
    product = PRODUCTS_BY_ID.get(product_id)
    if product is None:
        return {"error": f"Товар {product_id} не найден"}

    result = {"id": product_id, "name": product["name"], "price": product["price"]}
    if size:
        count = product["stock"].get(str(size).upper(), product["stock"].get(str(size), 0))
        result["size"] = size
        result["available"] = count
    else:
        result["stock"] = {s: c for s, c in product["stock"].items()}
    result["sizes_in_stock"] = [s for s in _sizes_in_stock(product) if s != "one"]
    return result


def get_policy(topic: str):
    """Отдаёт условия магазина по теме: доставка, оплата, возврат и т.д."""
    topic = topic.lower().strip()
    if topic in POLICIES:
        return {"topic": topic, "text": POLICIES[topic]}
    # Если тема названа неточно — подсказываем модели, какие есть
    return {"error": "Нет такой темы", "available_topics": list(POLICIES)}


def calc_discount(subtotal: int):
    """Скидка по правилам магазина: 5% от 15 000 ₽, 10% от 30 000 ₽."""
    if subtotal >= 30000:
        percent = 10
    elif subtotal >= 15000:
        percent = 5
    else:
        percent = 0
    return percent, round(subtotal * percent / 100)


def make_quote(items: list, customer: str = "Покупатель", delivery: str = "курьер"):
    """Собирает коммерческое предложение (КП) и сохраняет его в файл.

    items — список вида [{"product_id": "SH-001", "size": "42", "qty": 1}, ...]
    delivery — "курьер" (по Екатеринбургу) или "самовывоз".
    Все цены и суммы считает Python, а не модель, — чтобы не было ошибок.
    """
    lines, problems = [], []
    subtotal = 0
    for item in items:
        product = PRODUCTS_BY_ID.get(item.get("product_id", ""))
        if product is None:
            problems.append(f"нет товара {item.get('product_id')}")
            continue
        qty = int(item.get("qty", 1) or 1)
        size = str(item.get("size", "") or "")
        if not size and list(product["stock"]) == ["one"]:
            size = "one"
        available = product["stock"].get(size.upper(), product["stock"].get(size, 0))
        if not size:
            problems.append(f"{product['name']}: не указан размер")
            continue
        if available < qty:
            problems.append(f"{product['name']} (размер {size}): в наличии {available} шт.")
            continue
        total = product["price"] * qty
        subtotal += total
        lines.append({
            "id": product["id"], "name": product["name"],
            "size": "" if size == "one" else size,
            "qty": qty, "price": product["price"], "total": total,
        })

    if not lines:
        return {"error": "КП не собрано", "problems": problems}

    percent, discount = calc_discount(subtotal)
    after_discount = subtotal - discount
    if delivery == "самовывоз" or after_discount >= FREE_DELIVERY_FROM:
        delivery_cost = 0
    else:
        delivery_cost = DELIVERY_PRICE
    grand_total = after_discount + delivery_cost

    # Сохраняем КП в файл Markdown — его можно отправить клиенту
    QUOTES_DIR.mkdir(exist_ok=True)
    number = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = QUOTES_DIR / f"КП-{number}.md"
    rows = "\n".join(
        f"| {i}. {l['name']} | {l['size'] or '—'} | {l['qty']} | {money(l['price'])} | {money(l['total'])} |"
        for i, l in enumerate(lines, 1)
    )
    path.write_text(
        f"# Коммерческое предложение № {number}\n\n"
        f"**Клиент:** {customer}  \n**Дата:** {datetime.now():%d.%m.%Y}  \n"
        f"**Магазин:** {POLICIES['shop']}\n\n"
        f"| Товар | Размер | Кол-во | Цена | Сумма |\n|---|---|---|---|---|\n{rows}\n\n"
        f"Сумма товаров: **{money(subtotal)}**  \n"
        f"Скидка {percent}%: **−{money(discount)}**  \n"
        f"Доставка ({delivery}): **{money(delivery_cost)}**  \n"
        f"## Итого к оплате: {money(grand_total)}\n\n"
        "Предложение действительно 3 дня. Наличие на складе резервируется после оплаты.\n",
        encoding="utf-8",
    )

    return {
        "quote_file": str(path.relative_to(path.parent.parent)),
        "lines": lines,
        "subtotal": subtotal,
        "discount_percent": percent,
        "discount": discount,
        "delivery": delivery,
        "delivery_cost": delivery_cost,
        "grand_total": grand_total,
        "problems": problems,
    }


# Реестр: имя инструмента → функция. Агент по имени находит, что вызвать.
TOOLS = {
    "search_products": search_products,
    "check_stock": check_stock,
    "get_policy": get_policy,
    "make_quote": make_quote,
}
