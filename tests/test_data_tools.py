import csv
import json
import shutil
import sqlite3

import pytest

from emporio.data import ROOT, DataError, build, cents, connect, read_sources
from emporio.tools import StoreTools


def test_repeatable_import(prepared):
    expected = dict(categories=9, customers=50, products=65, promotions=25, orders=20, order_items=22)
    assert build(ROOT / "data", prepared)["counts"] == expected
    assert build(ROOT / "data", prepared)["counts"] == expected
    with connect(prepared / "store.sqlite3") as db:
        for table, count in expected.items():
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == count
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM products")
    policy = (prepared / "policies.txt").read_text()
    assert "[Página 8]" in policy and "6.2" in policy


@pytest.mark.parametrize("table,field,value", [
    ("products", "price_brl", "NaN"),
    ("products", "price_brl", "-2"),
    ("products", "stock_quantity", "1.5"),
    ("products", "specs", "[]"),
    ("products", "created_at", "2026-99-01"),
    ("products", "category_id", "999"),
    ("products", "status", "unknown"),
    ("products", "name", ""),
    ("orders", "estimated_delivery", "invalid"),
    ("promotions", "is_active", "yes"),
    ("promotions", "discount_percent", "101"),
])
def test_source_validation(tmp_path, table, field, value):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    path = next((tmp_path / "data").glob(f"* - {table}.csv"))
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    rows[0][field] = value
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(DataError):
        read_sources(tmp_path / "data")


def test_duplicate_and_missing_columns(tmp_path):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    path = next((tmp_path / "data").glob("* - categories.csv"))
    with path.open("a") as stream:
        stream.write('\n1,Duplicate,Duplicate\n')
    with pytest.raises(DataError, match="duplicada"):
        read_sources(tmp_path / "data")
    path.write_text("wrong,columns\n1,2\n")
    with pytest.raises(DataError, match="Colunas"):
        read_sources(tmp_path / "data")


def test_failed_setup_preserves_existing_database(tmp_path):
    source = tmp_path / "data"
    output = tmp_path / "output"
    shutil.copytree(ROOT / "data", source)
    build(source, output)
    before = (output / "store.sqlite3").read_bytes()
    next(source.glob("* - products.csv")).write_text("invalid\n")
    with pytest.raises(DataError):
        build(source, output)
    assert (output / "store.sqlite3").read_bytes() == before


def test_search_filters_and_accents(store):
    result = store.search_products(category="violoes", max_price=1000, limit=10)
    assert result["products"] and len(result["products"]) == 10
    assert result["total_matches"] > 10
    assert all(p["category"] == "Violões" and p["effective_price_cents"] <= 100000
               and p["available"] for p in result["products"])
    assert len(store.search_products()["products"]) == 5
    assert store.search_products(query="TAKAMINE gd20")["products"][0]["product_id"] == 95
    assert not store.search_products(query="nonexistent")["products"]
    assert not store.search_products(query="%' OR 1=1 --")["products"]


@pytest.mark.parametrize("product_id,status,stock", [(96, "active", 0), (113, "discontinued", 0),
                                                    (130, "coming_soon", 2), (136, "discontinued", 13)])
def test_unavailable_products(store, product_id, status, stock):
    product = store.get_product_details(product_id)
    assert (product["status"], product["stock_quantity"], product["available"]) == (status, stock, False)
    assert store.quote_payment(product_id, 1, "pix")["error"]["code"] == "unavailable"


def test_pricing_and_promotions(store):
    expired = store.get_product_details(95)
    assert expired["promotion"] is None
    assert expired["original_price_cents"] == expired["effective_price_cents"] == 219900
    assert store.quote_payment(95, 1, "pix")["total_cents"] == 208905
    active = store.get_product_details(94)
    assert active["effective_price_cents"] == 551908  # 5999 * .92
    assert store.quote_payment(94, 1, "pix")["total_cents"] == 551908
    assert not store.quote_payment(94, 1, "pix")["pix_discount_applied"]
    assert store.get_product_details(999)["error"]["code"] == "not_found"


def test_budget_uses_promotional_price(store):
    result = store.search_products(query="Ohana CK-20", max_price=450)
    assert result["products"][0]["effective_price_cents"] == 43920


@pytest.mark.parametrize("product_id,count,allowed", [
    (119, 3, True), (119, 4, False), (120, 4, True), (120, 5, False),
    (82, 6, True), (82, 7, True), (82, 9, False), (82, 12, False),
    (95, 12, True),
])
def test_installment_tiers(store, product_id, count, allowed):
    result = store.quote_payment(product_id, 1, "credit", count)
    assert result["ok"] is allowed
    if allowed:
        assert sum(result["installments_cents"]) == result["total_cents"]
        assert max(result["installments_cents"]) - min(result["installments_cents"]) <= 1


@pytest.mark.parametrize("count,minimum", [(3, 5000), (6, 8000), (12, 10000)])
def test_exact_installment_boundaries(tmp_path, prepared, count, minimum):
    path = tmp_path / "store.sqlite3"
    shutil.copyfile(prepared / "store.sqlite3", path)
    tools = StoreTools(path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE products SET price_cents=? WHERE product_id=81", (count * minimum,))
    assert tools.quote_payment(81, 1, "credit", count)["ok"]
    with sqlite3.connect(path) as db:
        db.execute("UPDATE products SET price_cents=price_cents-1 WHERE product_id=81")
    assert not tools.quote_payment(81, 1, "credit", count)["ok"]


def test_rounding_and_invalid_quotes(store):
    assert cents("599.90") == 59990
    assert store.quote_payment(83, 1, "pix")["total_cents"] == 40841  # half up
    assert not store.quote_payment(81, 13, "pix")["ok"]
    assert not store.quote_payment(81, 0, "pix")["ok"]
    assert not store.quote_payment(81, 1, "pix", 2)["ok"]
    assert not store.quote_payment(81, 1, "credit", 13)["ok"]


def test_customer_access_and_historical_totals(prepared, store):
    assert store.get_order_status(1)["ok"]
    assert store.get_order_status(2) == store.get_order_status(999)
    order = StoreTools(prepared / "store.sqlite3", 12).get_order_status(3)
    assert order["total_cents"] == 345000  # not current catalog sum 349800
    assert order["actual_delivery_date"] is None
    assert order["purchase_channel"] is None
    pending = StoreTools(prepared / "store.sqlite3", 6).get_order_status(9)
    assert pending["tracking_code"] is None and pending["estimated_delivery"] is None
    assert StoreTools(prepared / "store.sqlite3").get_order_status(1)["error"]["code"] == "session_required"
    assert not {"customer_id", "phone", "email", "notes"}.intersection(order)


def test_conflicting_specs_are_not_exposed(store):
    result = store.get_product_details(142)
    assert result["data_warning"] and result["description"] is None and result["specs"] is None


def test_multiple_promotions_fail_closed(tmp_path, prepared):
    path = tmp_path / "store.sqlite3"
    shutil.copyfile(prepared / "store.sqlite3", path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO promotions VALUES(99,94,'10','conflict',1)")
    tools = StoreTools(path)
    assert not tools.quote_payment(94, 1, "pix")["ok"]
    assert tools.search_products(query="Taylor 110e")["excluded_conflicting_promotions"] == 1


@pytest.mark.parametrize("name,args", [
    ("get_order_status", '{"order_id":1,"customer_id":7}'),
    ("get_order_status", '{"order_id":true}'),
    ("get_order_status", '{"order_id":0}'),
    ("get_order_status", 'null'),
    ("get_order_status", '{'),
    ("search_products", '{"query":null,"category":null,"max_price":NaN,"limit":5}'),
    ("search_products", '{"query":null,"category":null,"max_price":null,"limit":11}'),
])
def test_untrusted_tool_arguments(store, name, args):
    assert store.dispatch(name, args)["error"]["code"] == "invalid_arguments"


def test_unknown_tool_and_database_failure(prepared, store):
    assert store.dispatch("execute_sql", '{}')["error"]["code"] == "unknown_tool"
    broken = StoreTools(prepared / "missing.sqlite3")
    assert broken.dispatch("get_product_details", '{"product_id":81}')["error"]["code"] == "tool_failure"
