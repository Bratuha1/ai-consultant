"""Агент-консультант: модель GigaChat + наши инструменты.

Как это работает (цикл агента):
1. Отправляем модели историю переписки и ОПИСАНИЯ инструментов.
2. Модель либо отвечает текстом, либо просит: «вызови функцию X с аргументами Y».
3. Если просит — вызываем функцию сами, результат кладём в переписку
   и снова идём к модели (шаг 1). Так модель может сделать несколько
   шагов подряд: найти товар → проверить размер → собрать КП.
4. Когда модель отвечает текстом — это ответ покупателю.
"""
import json
import os

from dotenv import load_dotenv
from gigachat import GigaChat
from gigachat.models import Chat, Function, Messages, MessagesRole

from shop.tools import TOOLS

load_dotenv()

MAX_STEPS = 6  # защита от зацикливания: не больше 6 вызовов инструментов на один вопрос

SYSTEM_PROMPT = """Ты — консультант магазина спорттоваров «Старт» в Екатеринбурге.
Отвечай покупателям вежливо, коротко и по делу, на «вы».

Правила:
- Цены, наличие, размеры и условия бери ТОЛЬКО из инструментов. Никогда не выдумывай.
- id товаров (вида SH-001) бери ТОЛЬКО из результатов search_products. Прежде чем звать check_stock или make_quote, найди каждый товар через search_products.
- Перечисляй ВСЕ подходящие варианты из поиска (до 3–4), с ценой — пусть покупатель выберет.
- Если товара нет или ничего не нашлось — так и скажи и предложи похожее.
- Для одежды и обуви уточняй размер, прежде чем собирать КП.
- Когда покупатель определился, предложи собрать коммерческое предложение (make_quote).
- Если просят больше штук, чем есть на складе, — скажи, сколько есть, и спроси, собрать ли КП на это количество. Сам количество не меняй.
- После make_quote назови сумму, скидку, доставку, итог и имя файла КП. Если в ответе есть problems — обязательно скажи о них.
- Для юрлиц и секций с заказом от 50 000 ₽ упомяни индивидуальные условия через менеджера.
- На вопросы не про магазин отвечай, что помогаешь только с покупками в «Старте».
"""

# Описания инструментов для модели. По ним она понимает, что умеет каждая
# функция и какие аргументы передавать. Чем понятнее описание — тем точнее агент.
FUNCTIONS = [
    Function(
        name="search_products",
        description="Поиск товаров в каталоге магазина по словам, категории и максимальной цене.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Что ищем, например «беговые кроссовки» или «гантели»"},
                "category": {"type": "string", "enum": ["обувь", "одежда", "аксессуары", "инвентарь"],
                             "description": "Категория, если понятна"},
                "max_price": {"type": "integer", "description": "Максимальная цена в рублях, если покупатель назвал бюджет"},
                "size": {"type": "string", "description": "Размер, если покупатель его назвал — вернутся только товары, где он есть"},
            },
            "required": ["query"],
        },
    ),
    Function(
        name="check_stock",
        description="Проверить наличие товара по его id, при необходимости — конкретного размера.",
        parameters={
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "id товара, например SH-001"},
                "size": {"type": "string", "description": "Размер: 42 для обуви, M для одежды"},
            },
            "required": ["product_id"],
        },
    ),
    Function(
        name="get_policy",
        description="Условия магазина: адрес и часы работы, доставка, оплата, возврат, гарантия, скидки, примерка, размеры.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string",
                          "enum": ["shop", "доставка", "оплата", "возврат", "гарантия", "скидки", "примерка", "размеры"]},
            },
            "required": ["topic"],
        },
    ),
    Function(
        name="make_quote",
        description="Собрать коммерческое предложение (КП) с итоговой суммой, скидкой и доставкой и сохранить в файл.",
        parameters={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Товары в КП",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "string"},
                            "size": {"type": "string", "description": "Размер; для товаров без размера не нужен"},
                            "qty": {"type": "integer", "description": "Количество, по умолчанию 1"},
                        },
                        "required": ["product_id"],
                    },
                },
                "customer": {"type": "string", "description": "Имя покупателя или название организации"},
                "delivery": {"type": "string", "enum": ["курьер", "самовывоз"]},
            },
            "required": ["items"],
        },
    ),
]


class ShopAgent:
    """Один разговор с одним покупателем. Помнит историю переписки."""

    def __init__(self, verbose: bool = True):
        self.model = os.getenv("GIGACHAT_MODEL", "GigaChat-2")
        self.client = GigaChat(
            credentials=os.getenv("GIGACHAT_CREDENTIALS"),
            scope="GIGACHAT_API_PERS",
            model=self.model,
            verify_ssl_certs=False,  # временно, см. README
        )
        self.messages = [Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT)]
        self.verbose = verbose
        self.tokens = {"prompt": 0, "completion": 0}  # счётчик для расчёта стоимости
        self.tool_log = []  # какие инструменты вызывались — для демо и отладки

    def ask(self, user_text: str) -> str:
        """Принимает вопрос покупателя, возвращает ответ консультанта."""
        self.messages.append(Messages(role=MessagesRole.USER, content=user_text))

        for _ in range(MAX_STEPS):
            response = self.client.chat(Chat(
                messages=self.messages,
                functions=FUNCTIONS,
                function_call="auto",   # модель сама решает, звать инструмент или отвечать
                temperature=0.2,        # пониже — чтобы отвечала стабильно, без фантазий
            ))
            self.tokens["prompt"] += response.usage.prompt_tokens
            self.tokens["completion"] += response.usage.completion_tokens

            choice = response.choices[0]
            message = choice.message
            self.messages.append(message)  # запоминаем ход модели

            if choice.finish_reason != "function_call" or message.function_call is None:
                return message.content  # обычный текстовый ответ — готово

            # Модель попросила вызвать инструмент
            name = message.function_call.name
            args = message.function_call.arguments or {}
            result = self._run_tool(name, args)
            self.messages.append(Messages(
                role=MessagesRole.FUNCTION,
                name=name,
                content=json.dumps(result, ensure_ascii=False),
            ))

        return "Извините, не получилось разобраться с запросом. Попробуйте сформулировать иначе."

    def _run_tool(self, name: str, args: dict) -> dict:
        """Вызывает инструмент по имени. Ошибки не роняют бота, а уходят модели."""
        if self.verbose:
            print(f"   [инструмент] {name}({json.dumps(args, ensure_ascii=False)})")
        tool = TOOLS.get(name)
        if tool is None:
            result = {"error": f"Нет инструмента {name}"}
        else:
            try:
                result = tool(**args)
            except TypeError as e:  # модель передала лишний или кривой аргумент
                result = {"error": f"Неверные аргументы: {e}"}
        self.tool_log.append({"tool": name, "args": args, "result": result})
        return result

    def close(self):
        self.client.close()
