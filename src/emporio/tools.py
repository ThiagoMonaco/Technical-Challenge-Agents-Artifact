"""Read-only tools. Identity is bound by the application, never by model arguments."""

from decimal import Decimal
import json
import math

from .data import CONFLICTS, DataError, cents, connect, discounted, normalize


def failure(code, message):
    return {"ok": False, "error": {"code": code, "message": message}}


def function(name, description, properties):
    return {"type": "function", "name": name, "description": description, "strict": True,
            "parameters": {"type": "object", "properties": properties,
                           "required": list(properties), "additionalProperties": False}}


ID = {"type": "integer", "minimum": 1}
TOOLS = [
    function("search_products", "Busque produtos disponíveis. Filtra pelo preço promocional atual, sem PIX. Não use busca por descrição para confirmar specs conflitantes.", {
        "query": {"type": ["string", "null"], "description": "Nome, marca ou palavras-chave; null sem filtro."},
        "category": {"type": ["string", "null"], "description": "Nome da categoria, ex.: Violões; null sem filtro."},
        "max_price": {"type": ["number", "null"], "minimum": 0, "description": "Orçamento em reais, até duas casas; null sem filtro."},
        "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 10, "description": "null usa cinco resultados."},
    }),
    function("get_product_details", "Consulte preço, estoque, promoção, status e especificações de um produto, inclusive indisponível.", {"product_id": ID}),
    function("quote_payment", "Calcule pagamento de produto disponível. Use para PIX ou parcelamento; nunca calcule mentalmente.", {
        "product_id": ID,
        "quantity": {"type": "integer", "minimum": 1, "maximum": 1000},
        "payment_method": {"type": "string", "enum": ["pix", "debit", "credit", "boleto"]},
        "installments": {"type": ["integer", "null"], "minimum": 1, "maximum": 12,
                         "description": "null significa à vista; parcelas só para crédito."},
    }),
    function("get_order_status", "Consulte pedido exclusivamente do cliente da sessão. Não pede nem aceita customer_id.", {"order_id": ID}),
]


class StoreTools:
    def __init__(self, db_path, customer_id=None):
        self.db_path = db_path
        self.customer_id = customer_id

    def _product(self, db, product_id):
        row = db.execute("""SELECT p.*, c.name category FROM products p
                            JOIN categories c USING(category_id) WHERE product_id=?""", (product_id,)).fetchone()
        if row is None:
            return failure("not_found", "Produto não encontrado no catálogo fornecido.")
        promotions = db.execute("""SELECT discount_percent, description FROM promotions
                                   WHERE product_id=? AND is_active=1""", (product_id,)).fetchall()
        if len(promotions) > 1:
            return failure("conflicting_promotions", "Há promoções conflitantes; confirme o preço com a equipe.")
        discount = Decimal(promotions[0]["discount_percent"]) if promotions else Decimal(0)
        active = row["status"] == "active" and row["stock_quantity"] > 0
        conflict = CONFLICTS.get(product_id)
        return {
            "ok": True, "source": "CSV snapshot; não é estoque em tempo real",
            "product_id": row["product_id"], "name": row["name"], "category": row["category"],
            "status": row["status"], "stock_quantity": row["stock_quantity"], "available": active,
            "currency": "BRL", "original_price_cents": row["price_cents"],
            "discount_percent": str(discount),
            "promotion": promotions[0]["description"] if promotions else None,
            "effective_price_cents": discounted(row["price_cents"], discount),
            "description": None if conflict else row["description"],
            "specs": None if conflict else json.loads(row["specs"]),
            "data_warning": conflict,
        }

    def search_products(self, query=None, category=None, max_price=None, limit=None):
        budget = cents(max_price) if max_price is not None else None
        limit = 5 if limit is None else limit
        if type(limit) is not int or not 1 <= limit <= 10:
            raise DataError("Limite deve estar entre 1 e 10.")
        tokens = normalize(query or "").split()
        cat = normalize(category or "")
        with connect(self.db_path) as db:
            rows = db.execute("""SELECT p.product_id, p.name, p.description, c.name category
                    FROM products p JOIN categories c USING(category_id)
                    WHERE p.status='active' AND p.stock_quantity>0""").fetchall()
            products = []
            excluded_conflicts = 0
            for row in rows:
                text = normalize(" ".join([row["name"], row["description"], row["category"]]))
                if cat not in normalize(row["category"]) or not all(token in text for token in tokens):
                    continue
                product = self._product(db, row["product_id"])
                if not product["ok"]:
                    excluded_conflicts += 1
                    continue
                if budget is None or product["effective_price_cents"] <= budget:
                    products.append(product)
        products.sort(key=lambda p: (p["effective_price_cents"], p["product_id"]))
        return {"ok": True, "products": products[:limit], "total_matches": len(products),
                "excluded_conflicting_promotions": excluded_conflicts,
                "budget_basis": "Preço atual antes do PIX; somente status active e estoque positivo."}

    def get_product_details(self, product_id):
        with connect(self.db_path) as db:
            return self._product(db, product_id)

    def quote_payment(self, product_id, quantity, payment_method, installments=None):
        if type(quantity) is not int or not 1 <= quantity <= 1000:
            return failure("invalid_quantity", "Quantidade deve ser de 1 a 1000.")
        if payment_method not in {"pix", "debit", "credit", "boleto"}:
            return failure("invalid_payment", "Forma de pagamento não suportada.")
        count = 1 if installments is None else installments
        if type(count) is not int or not 1 <= count <= 12:
            return failure("invalid_installments", "Escolha de 1 a 12 parcelas.")
        if payment_method != "credit" and count != 1:
            return failure("invalid_installments", "Parcelamento disponível apenas no crédito.")
        product = self.get_product_details(product_id)
        if not product["ok"]:
            return product
        if not product["available"]:
            return failure("unavailable", "Produto indisponível para compra.")
        if quantity > product["stock_quantity"]:
            return failure("insufficient_stock", "Quantidade solicitada excede o estoque do snapshot.")
        subtotal = product["effective_price_cents"] * quantity
        pix = payment_method == "pix" and product["promotion"] is None
        total = discounted(subtotal, 5) if pix else subtotal
        base, remainder = divmod(total, count)
        minimum = 0 if count == 1 else 5000 if count <= 3 else 8000 if count <= 6 else 10000
        if base < minimum:
            return failure("minimum_installment", f"Nesta faixa, cada parcela deve ser de pelo menos {minimum} centavos (seção 3.1).")
        return {"ok": True, "product_id": product_id, "quantity": quantity, "currency": "BRL",
                "original_unit_price_cents": product["original_price_cents"],
                "promotion_discount_percent": product["discount_percent"],
                "promotional_unit_price_cents": product["effective_price_cents"],
                "pix_discount_applied": pix, "payment_method": payment_method,
                "subtotal_cents": subtotal, "total_cents": total,
                "installments_cents": [base + (i < remainder) for i in range(count)],
                "interest_percent": 0, "includes_shipping": False,
                "policy_sections": ["3", "3.1", "6.2"],
                "note": "Cotação do snapshot, sem reserva nem compra. Descontos não cumulativos. Boleto compensa em até 3 dias úteis."}

    def get_order_status(self, order_id):
        if self.customer_id is None:
            return failure("session_required", "Reinicie o chat com --customer-id de um cliente de demonstração; não informe identidade no chat.")
        with connect(self.db_path) as db:
            order = db.execute("""SELECT order_id, order_date, status, total_cents, payment_method,
                                    tracking_code, estimated_delivery FROM orders
                                    WHERE order_id=? AND customer_id=?""",
                               (order_id, self.customer_id)).fetchone()
            if order is None:
                return failure("order_not_found", "Pedido não encontrado para esta sessão.")
            items = db.execute("""SELECT i.product_id, p.name, i.quantity FROM order_items i
                                JOIN products p USING(product_id) WHERE order_id=?""", (order_id,)).fetchall()
            result = dict(order)
            for key in ("tracking_code", "estimated_delivery"):
                result[key] = result[key] or None
            return {"ok": True, **result, "currency": "BRL", "items": [dict(i) for i in items],
                    "actual_delivery_date": None, "purchase_channel": None,
                    "source": "CSV snapshot; estimativa registrada, sem consulta à transportadora.",
                    "note": "Não inferir recebimento a partir de estimated_delivery. Total histórico preservado."}

    def dispatch(self, name, arguments):
        schema = next((t["parameters"] for t in TOOLS if t["name"] == name), None)
        if schema is None:
            return failure("unknown_tool", "Ferramenta não permitida.")
        try:
            args = json.loads(arguments)
            if not isinstance(args, dict) or set(args) != set(schema["required"]):
                raise ValueError
            for key, spec in schema["properties"].items():
                value = args[key]
                allowed = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
                kind = ("null" if value is None else "string" if isinstance(value, str)
                        else "integer" if type(value) is int else "number" if type(value) is float else "invalid")
                if kind not in allowed and not (kind == "integer" and "number" in allowed):
                    raise ValueError
                if value is not None:
                    if "enum" in spec and value not in spec["enum"]:
                        raise ValueError
                    if kind in {"integer", "number"}:
                        if not math.isfinite(value) or value < spec.get("minimum", -math.inf) or value > spec.get("maximum", math.inf):
                            raise ValueError
                    if isinstance(value, str) and len(value) > 500:
                        raise ValueError
            return getattr(self, name)(**args)
        except (ValueError, TypeError, OverflowError):
            return failure("invalid_arguments", "Argumentos inválidos; confira os campos e limites da ferramenta.")
        except Exception:
            # Never return database internals, source customer rows, or exception text.
            return failure("tool_failure", "Consulta indisponível. Não confirme informações; tente novamente ou consulte a equipe.")
