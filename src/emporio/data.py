"""Validate source snapshots and build a disposable SQLite database."""

import csv
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
DB_PATH = RUNTIME / "store.sqlite3"
POLICY_PATH = RUNTIME / "policies.txt"

COLUMNS = {
    "categories": "category_id name description",
    "customers": "customer_id name phone email city",
    "products": "product_id price_brl name category_id description stock_quantity status specs created_at",
    "promotions": "promotion_id product_id discount_percent description is_active",
    "orders": "order_id customer_id order_date status total_brl payment_method tracking_code estimated_delivery notes",
    "order_items": "order_id quantity product_id",
}

# Explicit source review, not guesses about the instruments' real-world specs.
CONFLICTS = {
    135: "Nome Music Man; descrição identifica Fender Jazz Bass; madeira também diverge.",
    137: "Nome Yamaha; descrição identifica Ibanez de 5 cordas; specs indicam 4 cordas.",
    139: "Nome Yamaha; descrição identifica Pearl; madeiras divergem das specs.",
    140: "Nome Pearl; descrição identifica Tama; madeira diverge das specs.",
    142: "Nome Korg; descrição identifica Roland de 88 teclas; specs indicam 61.",
    144: "Nome Roland; descrição identifica Yamaha.",
}


class DataError(ValueError):
    pass


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


def cents(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal(".01")):
            raise ValueError
        return int(amount * 100)
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise DataError("Valor monetário inválido; use um número não negativo com até duas casas.") from exc


def discounted(amount, percent):
    return int((Decimal(amount) * (100 - Decimal(str(percent))) / 100)
               .quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def positive_int(value, *, allow_zero=False):
    try:
        result = int(value)
        if str(result) != str(value) or result < (0 if allow_zero else 1):
            raise ValueError
        return result
    except (ValueError, TypeError) as exc:
        raise DataError("Inteiro inválido.") from exc


def read_sources(source):
    tables = {}
    for table, fields in COLUMNS.items():
        matches = list(source.glob(f"* - {table}.csv"))
        if len(matches) != 1:
            raise DataError(f"Esperado um CSV para {table}.")
        with matches[0].open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != fields.split():
                raise DataError(f"Colunas inesperadas em {table}.")
            rows = list(reader)
        if not rows:
            raise DataError(f"Tabela vazia: {table}.")
        seen = set()
        for row in rows:
            if None in row or any(v is None for v in row.values()):
                raise DataError(f"Linha incompleta em {table}.")
            key = tuple(row[k] for k in (["order_id", "product_id"] if table == "order_items"
                                        else [fields.split()[0]]))
            if key in seen:
                raise DataError(f"Chave duplicada em {table}.")
            seen.add(key)
            optional = {"tracking_code", "estimated_delivery", "notes"}
            if any(not value.strip() for k, value in row.items() if k not in optional):
                raise DataError(f"Campo obrigatório vazio em {table}.")
            for k, value in row.items():
                if k.endswith("_id") or k == "quantity":
                    positive_int(value)
                elif k == "stock_quantity":
                    positive_int(value, allow_zero=True)
                elif k in {"price_brl", "total_brl"}:
                    cents(value)
                elif k in {"created_at", "order_date", "estimated_delivery"} and value:
                    try:
                        date.fromisoformat(value)
                    except ValueError as exc:
                        raise DataError(f"Data inválida em {table}.") from exc
            if table == "products":
                if row["status"] not in {"active", "discontinued", "coming_soon"}:
                    raise DataError("Status de produto inválido.")
                try:
                    if not isinstance(json.loads(row["specs"]), dict):
                        raise ValueError
                except (ValueError, TypeError) as exc:
                    raise DataError("Specs devem ser um objeto JSON.") from exc
            if table == "orders" and row["status"] not in {
                    "pending", "confirmed", "shipped", "delivered", "cancelled"}:
                raise DataError("Status de pedido inválido.")
            if table == "promotions":
                if row["is_active"] not in {"0", "1"}:
                    raise DataError("is_active deve ser 0 ou 1.")
                try:
                    discount = Decimal(row["discount_percent"])
                    if not discount.is_finite() or not 0 < discount <= 100:
                        raise ValueError
                except (InvalidOperation, ValueError) as exc:
                    raise DataError("Desconto inválido.") from exc
        tables[table] = rows
    relations = [("products", "category_id", "categories"),
                 ("promotions", "product_id", "products"),
                 ("orders", "customer_id", "customers"),
                 ("order_items", "order_id", "orders"),
                 ("order_items", "product_id", "products")]
    for table, field, target in relations:
        keys = {r[field] for r in tables[target]}
        if any(r[field] not in keys for r in tables[table]):
            raise DataError(f"Referência inválida: {table}.{field}.")
    return tables


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE categories(category_id INTEGER PRIMARY KEY, name TEXT, description TEXT);
CREATE TABLE customers(customer_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, email TEXT, city TEXT);
CREATE TABLE products(product_id INTEGER PRIMARY KEY, price_cents INTEGER CHECK(price_cents>=0),
 name TEXT, category_id INTEGER REFERENCES categories, description TEXT,
 stock_quantity INTEGER CHECK(stock_quantity>=0), status TEXT, specs TEXT, created_at TEXT);
CREATE TABLE promotions(promotion_id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products,
 discount_percent TEXT, description TEXT, is_active INTEGER CHECK(is_active IN (0,1)));
CREATE TABLE orders(order_id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers,
 order_date TEXT, status TEXT, total_cents INTEGER CHECK(total_cents>=0), payment_method TEXT,
 tracking_code TEXT, estimated_delivery TEXT, notes TEXT);
CREATE TABLE order_items(order_id INTEGER REFERENCES orders, quantity INTEGER CHECK(quantity>0),
 product_id INTEGER REFERENCES products, PRIMARY KEY(order_id,product_id));
"""


def build(source=ROOT / "data", output=RUNTIME):
    from pypdf import PdfReader

    source, output = Path(source), Path(output)
    tables = read_sources(source)
    pdfs = list(source.glob("*.pdf"))
    if len(pdfs) != 1:
        raise DataError("Esperado um manual PDF na pasta de dados.")
    pages = [page.extract_text(extraction_mode="layout") or "" for page in PdfReader(pdfs[0]).pages]
    if not pages or any(not page.strip() for page in pages):
        raise DataError("Não foi possível extrair todas as páginas do manual.")
    policy = "\n\n".join(f"[Página {n}]\n{text}" for n, text in enumerate(pages, 1))
    warnings = [f"Produto {key}: {value}" for key, value in CONFLICTS.items()]
    warnings.extend([
        "Manual: números de WhatsApp divergem entre seções 1.2 e 7; encaminhar sem escolher um número.",
        "Manual: seção 3.1 prevalece sobre resumo da seção 3 para parcelas mínimas.",
        "Manual: frete local de exatamente R$ 500 não está definido; consultar equipe.",
        "Pedidos: não há canal de compra nem data efetiva de recebimento.",
        "Catálogo: manual menciona mais de 300 itens; snapshot contém 65.",
    ])
    for row in tables["products"]:
        if row["status"] != "active" and int(row["stock_quantity"]) > 0:
            warnings.append(f"Produto {row['product_id']}: status impede oferta apesar do estoque.")
    counts = {table: len(rows) for table, rows in tables.items()}
    output.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=output, suffix=".sqlite3")
    os.close(handle)
    try:
        with sqlite3.connect(name) as db:
            db.executescript(SCHEMA)
            for table, rows in tables.items():
                for raw in rows:
                    row = dict(raw)
                    for old, new in [("price_brl", "price_cents"), ("total_brl", "total_cents")]:
                        if old in row:
                            row[new] = cents(row.pop(old))
                    columns = ",".join(row)
                    placeholders = ",".join("?" for _ in row)
                    db.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(row.values()))
            for item in db.execute("""SELECT o.order_id, o.total_cents, SUM(i.quantity*p.price_cents)
                FROM orders o JOIN order_items i USING(order_id) JOIN products p USING(product_id)
                GROUP BY o.order_id HAVING o.total_cents != SUM(i.quantity*p.price_cents)"""):
                warnings.append(f"Pedido {item[0]}: total histórico difere do catálogo atual; preservar total armazenado.")
            for item in db.execute("""SELECT product_id FROM promotions WHERE is_active=1
                                      GROUP BY product_id HAVING COUNT(*)>1"""):
                warnings.append(f"Produto {item[0]}: múltiplas promoções ativas; cotação requer equipe.")
        os.replace(name, output / "store.sqlite3")
    finally:
        Path(name).unlink(missing_ok=True)
    (output / "policies.txt").write_text(policy, encoding="utf-8")
    report = {"counts": counts, "policy_pages": len(pages), "warnings": warnings}
    (output / "data_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


@contextmanager
def connect(path=DB_PATH):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError("Base não preparada. Execute: emporio setup")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.create_function("normalize", 1, normalize)
    db.execute("PRAGMA query_only=ON")
    try:
        yield db
    finally:
        db.close()
