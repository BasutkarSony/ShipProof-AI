import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.store as store
from app.store import init_db, get_catalogue, create_order, get_order, list_orders


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._tmp_path = self._tmp.name
        store.DB_PATH = Path(self._tmp_path)
        init_db()

    def tearDown(self):
        store.DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shipproof.db"
        os.unlink(self._tmp_path)

    def test_init_db_creates_tables(self):
        conn = store._connect()
        try:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("products", tables)
            self.assertIn("orders", tables)
            self.assertIn("order_items", tables)
        finally:
            conn.close()

    def test_catalogue_seeded_with_three_products(self):
        products = get_catalogue()
        self.assertEqual(len(products), 3)
        skus = {p["sku"] for p in products}
        self.assertEqual(skus, {"SHIP-STD-001", "SHIP-HEV-002", "SHIP-FRA-003"})
        for p in products:
            self.assertEqual(p["currency"], "USD")
            self.assertIsNotNone(p["description"])
            Decimal(p["price"])

    def test_catalogue_prices_match_decimal(self):
        products = {p["sku"]: p for p in get_catalogue()}
        self.assertEqual(Decimal(products["SHIP-STD-001"]["price"]), Decimal("12.99"))
        self.assertEqual(Decimal(products["SHIP-HEV-002"]["price"]), Decimal("24.50"))
        self.assertEqual(Decimal(products["SHIP-FRA-003"]["price"]), Decimal("18.75"))

    def test_create_order_persists_items_and_total(self):
        order = create_order(
            [
                {"sku": "SHIP-STD-001", "quantity": 2},
                {"sku": "SHIP-FRA-003", "quantity": 1},
            ]
        )
        self.assertIsNotNone(order["id"])
        self.assertEqual(order["payment_status"], "CREATED")
        self.assertEqual(order["currency"], "USD")
        # 2 * 12.99 + 1 * 18.75 = 25.98 + 18.75 = 44.73
        self.assertEqual(Decimal(order["total"]), Decimal("44.73"))

    def test_get_order_returns_manifest_with_quantities(self):
        order = create_order(
            [
                {"sku": "SHIP-HEV-002", "quantity": 3},
                {"sku": "SHIP-STD-001", "quantity": 1},
            ]
        )
        fetched = get_order(order["id"])
        self.assertIsNotNone(fetched)
        items = {i["sku"]: i for i in fetched["items"]}
        self.assertEqual(len(items), 2)
        self.assertEqual(items["SHIP-HEV-002"]["quantity"], 3)
        self.assertEqual(items["SHIP-STD-001"]["quantity"], 1)
        self.assertEqual(items["SHIP-HEV-002"]["unit_price"], "24.50")
        self.assertEqual(items["SHIP-HEV-002"]["line_total"], "73.50")
        self.assertEqual(items["SHIP-STD-001"]["line_total"], "12.99")
        # 3 * 24.50 + 1 * 12.99 = 73.50 + 12.99 = 86.49
        self.assertEqual(Decimal(fetched["total"]), Decimal("86.49"))

    def test_get_order_unknown_id_returns_none(self):
        self.assertIsNone(get_order("00000000-0000-0000-0000-000000000000"))

    def test_list_orders_returns_all_created(self):
        create_order([{"sku": "SHIP-STD-001", "quantity": 1}])
        create_order([{"sku": "SHIP-FRA-003", "quantity": 2}])
        orders = list_orders()
        self.assertEqual(len(orders), 2)
        for o in orders:
            self.assertIn("id", o)
            self.assertIn("total", o)
            self.assertIn("created_at", o)

    def test_unknown_sku_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "NONEXISTENT", "quantity": 1}])

    def test_zero_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "SHIP-STD-001", "quantity": 0}])

    def test_negative_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "SHIP-STD-001", "quantity": -1}])

    def test_empty_order_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([])

    def test_float_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "SHIP-STD-001", "quantity": 2.5}])

    def test_decimal_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "SHIP-STD-001", "quantity": Decimal("2")}])

    def test_boolean_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "SHIP-STD-001", "quantity": True}])

    def test_string_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "SHIP-STD-001", "quantity": "2"}])

    def test_non_usd_currency_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "SHIP-STD-001", "quantity": 1}], currency="EUR")

    def test_server_calculated_total_uses_decimal(self):
        order = create_order(
            [
                {"sku": "SHIP-STD-001", "quantity": 1},
                {"sku": "SHIP-HEV-002", "quantity": 1},
                {"sku": "SHIP-FRA-003", "quantity": 1},
            ]
        )
        expected = Decimal("12.99") + Decimal("24.50") + Decimal("18.75")
        self.assertEqual(Decimal(order["total"]), expected)
        # Verify no floating-point rounding in stored cents
        conn = store._connect()
        try:
            row = conn.execute(
                "SELECT total_cents FROM orders WHERE id = ?", (order["id"],)
            ).fetchone()
            self.assertEqual(row["total_cents"], 5624)  # 1299 + 2450 + 1875
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
