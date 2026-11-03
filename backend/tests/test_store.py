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
        self.assertEqual(skus, {"MUG-CER-001", "TOTE-COT-002", "NOTE-A5-003"})
        for p in products:
            self.assertEqual(p["currency"], "USD")
            self.assertIsNotNone(p["description"])
            Decimal(p["price"])

    def test_catalogue_prices_match_decimal(self):
        products = {p["sku"]: p for p in get_catalogue()}
        self.assertEqual(Decimal(products["MUG-CER-001"]["price"]), Decimal("18.00"))
        self.assertEqual(Decimal(products["TOTE-COT-002"]["price"]), Decimal("14.00"))
        self.assertEqual(Decimal(products["NOTE-A5-003"]["price"]), Decimal("12.50"))
        self.assertTrue(products["MUG-CER-001"]["fragile"])
        self.assertFalse(products["TOTE-COT-002"]["fragile"])

    def test_create_order_persists_items_and_total(self):
        order = create_order(
            [
                {"sku": "MUG-CER-001", "quantity": 2},
                {"sku": "NOTE-A5-003", "quantity": 1},
            ]
        )
        self.assertIsNotNone(order["id"])
        self.assertEqual(order["payment_status"], "CREATED")
        self.assertEqual(order["currency"], "USD")
        # 2 * 18.00 + 1 * 12.50 = 48.50
        self.assertEqual(Decimal(order["total"]), Decimal("48.50"))
        self.assertTrue(order["items"][0]["fragile"])

    def test_get_order_returns_manifest_with_quantities(self):
        order = create_order(
            [
                {"sku": "TOTE-COT-002", "quantity": 3},
                {"sku": "MUG-CER-001", "quantity": 1},
            ]
        )
        fetched = get_order(order["id"])
        self.assertIsNotNone(fetched)
        items = {i["sku"]: i for i in fetched["items"]}
        self.assertEqual(len(items), 2)
        self.assertEqual(items["TOTE-COT-002"]["quantity"], 3)
        self.assertEqual(items["MUG-CER-001"]["quantity"], 1)
        self.assertEqual(items["TOTE-COT-002"]["unit_price"], "14.00")
        self.assertEqual(items["TOTE-COT-002"]["line_total"], "42.00")
        self.assertEqual(items["MUG-CER-001"]["line_total"], "18.00")
        # 3 * 14.00 + 1 * 18.00 = 60.00
        self.assertEqual(Decimal(fetched["total"]), Decimal("60.00"))

    def test_get_order_unknown_id_returns_none(self):
        self.assertIsNone(get_order("00000000-0000-0000-0000-000000000000"))

    def test_list_orders_returns_all_created(self):
        create_order([{"sku": "MUG-CER-001", "quantity": 1}])
        create_order([{"sku": "NOTE-A5-003", "quantity": 2}])
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
            create_order([{"sku": "MUG-CER-001", "quantity": 0}])

    def test_negative_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "MUG-CER-001", "quantity": -1}])

    def test_empty_order_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([])

    def test_float_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "MUG-CER-001", "quantity": 2.5}])

    def test_decimal_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "MUG-CER-001", "quantity": Decimal("2")}])

    def test_boolean_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "MUG-CER-001", "quantity": True}])

    def test_string_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "MUG-CER-001", "quantity": "2"}])

    def test_non_usd_currency_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "MUG-CER-001", "quantity": 1}], currency="EUR")

    def test_order_persists_buyer_delivery_details(self):
        address = {
            "address_line_1": "123 Test Street",
            "address_line_2": "Unit 4",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78701",
            "country_code": "US",
        }
        order = create_order(
            [{"sku": "MUG-CER-001", "quantity": 1}],
            buyer_name="Demo Test Buyer",
            shipping_address=address,
        )
        fetched = get_order(order["id"])
        self.assertEqual(fetched["buyer_name"], "Demo Test Buyer")
        self.assertEqual(fetched["shipping_address"], address)

    def test_catalogue_seed_does_not_overwrite_merchant_edits(self):
        conn = store._connect()
        try:
            conn.execute(
                "UPDATE products SET name = ?, price_cents = ? WHERE sku = ?",
                ("Merchant edited mug", 1999, "MUG-CER-001"),
            )
            conn.commit()
        finally:
            conn.close()

        init_db()
        edited = {p["sku"]: p for p in get_catalogue()}["MUG-CER-001"]
        self.assertEqual(edited["name"], "Merchant edited mug")
        self.assertEqual(edited["price"], "19.99")

    def test_multiple_failed_checkouts_can_store_no_capture_id(self):
        first = create_order([{"sku": "MUG-CER-001", "quantity": 1}])
        second = create_order([{"sku": "TOTE-COT-002", "quantity": 1}])
        store.set_capture(first["id"], "", "FAILED")
        store.set_capture(second["id"], "", "FAILED")
        self.assertIsNone(get_order(first["id"])["paypal_capture_id"])
        self.assertIsNone(get_order(second["id"])["paypal_capture_id"])

    def test_server_calculated_total_uses_decimal(self):
        order = create_order(
            [
                {"sku": "MUG-CER-001", "quantity": 1},
                {"sku": "TOTE-COT-002", "quantity": 1},
                {"sku": "NOTE-A5-003", "quantity": 1},
            ]
        )
        expected = Decimal("18.00") + Decimal("14.00") + Decimal("12.50")
        self.assertEqual(Decimal(order["total"]), expected)
        # Verify no floating-point rounding in stored cents
        conn = store._connect()
        try:
            row = conn.execute(
                "SELECT total_cents FROM orders WHERE id = ?", (order["id"],)
            ).fetchone()
            self.assertEqual(row["total_cents"], 4450)  # 1800 + 1400 + 1250
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
