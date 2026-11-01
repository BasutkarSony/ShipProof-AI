"""Tests for shipment manifest persistence and API endpoint handler functions.

Conventions followed:
- Plain unittest.TestCase (no pytest-specific features).
- Temporary SQLite file redirected via store.DB_PATH (same pattern as test_store.py).
- FastAPI handler functions called directly (same pattern as test_paypal_checkout.py).
  No HTTP client library is required.
- No Gemini API calls, no external HTTP calls.
- Checkout orders and their packaging catalogue must remain unaffected.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import app.store as store
from app.store import (
    init_db,
    create_manifest,
    get_manifest,
    get_manifest_for_shipment,
    update_manifest,
    finalize_manifest,
    # Checkout helpers — used to verify they are unaffected.
    get_catalogue,
    create_order,
    get_order,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SHIPMENT_ORDER_ID = "ORD-1004"  # exists in sample_orders.json


def _item(description="Wireless headphones", qty=1, **kwargs):
    """Build a minimal valid manifest item dict."""
    base = {"description": description, "expected_qty": qty}
    base.update(kwargs)
    return base


def _valid_items():
    return [
        {"description": "Wireless headphones", "expected_qty": 1,
         "sku": "WH-1000", "fragile": True},
        {"description": "USB-C cable 2m", "expected_qty": 2},
    ]


# ---------------------------------------------------------------------------
# Store-layer tests
# ---------------------------------------------------------------------------

class ManifestStoreTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._tmp_path = self._tmp.name
        store.DB_PATH = Path(self._tmp_path)
        init_db()

    def tearDown(self):
        store.DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shipproof.db"
        os.unlink(self._tmp_path)

    # -- Creation & retrieval ------------------------------------------------

    def test_create_manifest_returns_draft(self):
        m = create_manifest(SHIPMENT_ORDER_ID, [_item()])
        self.assertEqual(m["status"], "DRAFT")
        self.assertEqual(m["shipment_order_id"], SHIPMENT_ORDER_ID)
        self.assertIsNone(m["manifest_hash"])
        self.assertIsNotNone(m["id"])

    def test_create_manifest_stores_items(self):
        items = [
            _item("Wireless headphones", qty=1, sku="WH-1000", fragile=True),
            _item("USB-C cable", qty=3, unit_value_cents=999),
        ]
        m = create_manifest(SHIPMENT_ORDER_ID, items)
        self.assertEqual(len(m["items"]), 2)
        by_desc = {i["description"]: i for i in m["items"]}
        self.assertEqual(by_desc["Wireless headphones"]["expected_qty"], 1)
        self.assertEqual(by_desc["Wireless headphones"]["sku"], "WH-1000")
        self.assertTrue(by_desc["Wireless headphones"]["fragile"])
        self.assertEqual(by_desc["USB-C cable"]["expected_qty"], 3)
        self.assertEqual(by_desc["USB-C cable"]["unit_value_cents"], 999)
        self.assertFalse(by_desc["USB-C cable"]["fragile"])

    def test_get_manifest_by_id(self):
        m = create_manifest(SHIPMENT_ORDER_ID, [_item()])
        fetched = get_manifest(m["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], m["id"])

    def test_get_manifest_returns_none_for_unknown_id(self):
        self.assertIsNone(get_manifest("00000000-0000-0000-0000-000000000000"))

    def test_get_manifest_for_shipment_returns_most_recent(self):
        create_manifest(SHIPMENT_ORDER_ID, [_item("First item")])
        m2 = create_manifest(SHIPMENT_ORDER_ID, [_item("Second item")])
        latest = get_manifest_for_shipment(SHIPMENT_ORDER_ID)
        self.assertEqual(latest["id"], m2["id"])

    def test_get_manifest_for_shipment_returns_none_if_no_manifest(self):
        self.assertIsNone(get_manifest_for_shipment("ORD-NONEXISTENT"))

    def test_create_manifest_with_notes(self):
        m = create_manifest(SHIPMENT_ORDER_ID, [_item()], notes="Fragile — handle with care")
        self.assertEqual(m["notes"], "Fragile — handle with care")

    # -- Validation: empty manifest ------------------------------------------

    def test_empty_items_raises(self):
        with self.assertRaises(ValueError) as ctx:
            create_manifest(SHIPMENT_ORDER_ID, [])
        self.assertIn("at least one item", str(ctx.exception))

    # -- Validation: description ---------------------------------------------

    def test_blank_description_raises(self):
        with self.assertRaises(ValueError) as ctx:
            create_manifest(SHIPMENT_ORDER_ID, [_item(description="")])
        self.assertIn("description", str(ctx.exception).lower())

    def test_whitespace_only_description_raises(self):
        with self.assertRaises(ValueError):
            create_manifest(SHIPMENT_ORDER_ID, [_item(description="   ")])

    # -- Validation: quantity ------------------------------------------------

    def test_zero_quantity_raises(self):
        with self.assertRaises(ValueError) as ctx:
            create_manifest(SHIPMENT_ORDER_ID, [_item(qty=0)])
        self.assertIn("positive integer", str(ctx.exception))

    def test_negative_quantity_raises(self):
        with self.assertRaises(ValueError):
            create_manifest(SHIPMENT_ORDER_ID, [_item(qty=-1)])

    def test_float_quantity_raises(self):
        with self.assertRaises(ValueError):
            create_manifest(SHIPMENT_ORDER_ID, [_item(qty=1.5)])

    def test_string_quantity_raises(self):
        with self.assertRaises(ValueError):
            create_manifest(SHIPMENT_ORDER_ID, [_item(qty="2")])

    def test_boolean_quantity_raises(self):
        with self.assertRaises(ValueError):
            create_manifest(SHIPMENT_ORDER_ID, [_item(qty=True)])

    # -- Validation: monetary value ------------------------------------------

    def test_negative_unit_value_raises(self):
        with self.assertRaises(ValueError):
            create_manifest(SHIPMENT_ORDER_ID, [_item(unit_value_cents=-1)])

    def test_float_unit_value_raises(self):
        with self.assertRaises(ValueError):
            create_manifest(SHIPMENT_ORDER_ID, [_item(unit_value_cents=9.99)])

    def test_zero_unit_value_is_valid(self):
        m = create_manifest(SHIPMENT_ORDER_ID, [_item(unit_value_cents=0)])
        self.assertEqual(m["items"][0]["unit_value_cents"], 0)

    def test_none_unit_value_is_valid(self):
        m = create_manifest(SHIPMENT_ORDER_ID, [_item()])
        self.assertIsNone(m["items"][0]["unit_value_cents"])

    # -- Update (DRAFT only) -------------------------------------------------

    def test_update_draft_replaces_items(self):
        m = create_manifest(SHIPMENT_ORDER_ID, [_item("Original item")])
        updated = update_manifest(m["id"], [_item("Replacement item", qty=5)])
        self.assertEqual(len(updated["items"]), 1)
        self.assertEqual(updated["items"][0]["description"], "Replacement item")
        self.assertEqual(updated["items"][0]["expected_qty"], 5)

    def test_update_draft_updates_notes(self):
        m = create_manifest(SHIPMENT_ORDER_ID, [_item()])
        updated = update_manifest(m["id"], [_item()], notes="Updated note")
        self.assertEqual(updated["notes"], "Updated note")

    def test_update_unknown_manifest_raises(self):
        with self.assertRaises(ValueError) as ctx:
            update_manifest("00000000-0000-0000-0000-000000000000", [_item()])
        self.assertIn("not found", str(ctx.exception).lower())

    def test_update_empty_items_raises(self):
        m = create_manifest(SHIPMENT_ORDER_ID, [_item()])
        with self.assertRaises(ValueError):
            update_manifest(m["id"], [])

    # -- Finalization --------------------------------------------------------

    def test_finalize_sets_status_and_hash(self):
        m = create_manifest(SHIPMENT_ORDER_ID, [_item()])
        finalized = finalize_manifest(m["id"])
        self.assertEqual(finalized["status"], "FINALIZED")
        self.assertIsNotNone(finalized["manifest_hash"])
        self.assertEqual(len(finalized["manifest_hash"]), 64)  # SHA-256 hex

    def test_finalize_already_finalized_raises(self):
        m = create_manifest(SHIPMENT_ORDER_ID, [_item()])
        finalize_manifest(m["id"])
        with self.assertRaises(ValueError) as ctx:
            finalize_manifest(m["id"])
        self.assertIn("already FINALIZED", str(ctx.exception))

    def test_update_finalized_manifest_raises(self):
        m = create_manifest(SHIPMENT_ORDER_ID, [_item()])
        finalize_manifest(m["id"])
        with self.assertRaises(ValueError) as ctx:
            update_manifest(m["id"], [_item("New item")])
        self.assertIn("cannot be edited", str(ctx.exception))

    # -- Hash stability ------------------------------------------------------

    def test_hash_stable_on_refetch(self):
        """Re-fetching a finalized manifest must return the same hash."""
        items = [
            _item("Laptop", qty=1, sku="LAP-001", unit_value_cents=120000, fragile=True),
            _item("Charger", qty=1, sku="CHG-001", unit_value_cents=2999),
        ]
        finalized = finalize_manifest(create_manifest(SHIPMENT_ORDER_ID, items)["id"])
        refetched = get_manifest(finalized["id"])
        self.assertEqual(refetched["manifest_hash"], finalized["manifest_hash"])

    def test_different_content_produces_different_hash(self):
        m1 = finalize_manifest(
            create_manifest(SHIPMENT_ORDER_ID, [_item("Item A", qty=1)])["id"]
        )
        m2 = finalize_manifest(
            create_manifest(SHIPMENT_ORDER_ID, [_item("Item B", qty=2)])["id"]
        )
        self.assertNotEqual(m1["manifest_hash"], m2["manifest_hash"])

    def test_different_shipment_order_id_produces_different_hash(self):
        """Identical item content on different shipment records must hash differently.

        This proves shipment_order_id is included in the canonical payload so
        a manifest cannot be reused to misrepresent which shipment was inspected.
        """
        items = [_item("Laptop", qty=1, sku="LAP-001", unit_value_cents=120000, fragile=True)]
        m1 = finalize_manifest(create_manifest("ORD-1001", items)["id"])
        m2 = finalize_manifest(create_manifest("ORD-1004", items)["id"])
        self.assertNotEqual(m1["manifest_hash"], m2["manifest_hash"])

    # -- Checkout isolation --------------------------------------------------

    def test_checkout_catalogue_unaffected(self):
        """Manifest operations must not change the packaging product catalogue."""
        create_manifest(SHIPMENT_ORDER_ID, [_item()])
        products = get_catalogue()
        self.assertEqual(len(products), 3)
        skus = {p["sku"] for p in products}
        self.assertEqual(skus, {"SHIP-STD-001", "SHIP-HEV-002", "SHIP-FRA-003"})

    def test_checkout_order_items_unaffected(self):
        """Manifest items must not appear in checkout order_items."""
        checkout = create_order([{"sku": "SHIP-STD-001", "quantity": 2}])
        create_manifest(SHIPMENT_ORDER_ID, [_item("Smartwatch", qty=1, sku="SW-X1")])
        fetched = get_order(checkout["id"])
        self.assertEqual(len(fetched["items"]), 1)
        self.assertEqual(fetched["items"][0]["sku"], "SHIP-STD-001")

    def test_init_db_creates_manifest_tables(self):
        """Both new tables must be present after init_db."""
        conn = store._connect()
        try:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("shipment_manifests", tables)
            self.assertIn("manifest_items", tables)
            # Original tables must still be present.
            self.assertIn("orders", tables)
            self.assertIn("order_items", tables)
            self.assertIn("products", tables)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# FastAPI endpoint handler tests
# Calls handler functions directly — same convention as test_paypal_checkout.py.
# No HTTP client library required.
# ---------------------------------------------------------------------------

class ManifestAPITests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._tmp_path = self._tmp.name
        store.DB_PATH = Path(self._tmp_path)
        init_db()

        # Import handlers after redirecting DB_PATH.
        from app.main import (
            create_shipment_manifest,
            get_shipment_manifest,
            get_manifest_by_id,
            update_manifest_by_id,
            finalize_manifest_by_id,
        )
        self.create_shipment_manifest = create_shipment_manifest
        self.get_shipment_manifest = get_shipment_manifest
        self.get_manifest_by_id = get_manifest_by_id
        self.update_manifest_by_id = update_manifest_by_id
        self.finalize_manifest_by_id = finalize_manifest_by_id

    def tearDown(self):
        store.DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shipproof.db"
        os.unlink(self._tmp_path)

    # -- POST /api/shipments/{id}/manifest -----------------------------------

    def test_create_manifest_returns_draft(self):
        result = self.create_shipment_manifest("ORD-1004", {"items": _valid_items()})
        self.assertEqual(result["status"], "DRAFT")
        self.assertEqual(result["shipment_order_id"], "ORD-1004")
        self.assertEqual(len(result["items"]), 2)

    def test_create_manifest_missing_shipment_raises_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self.create_shipment_manifest("ORD-NONEXISTENT", {"items": _valid_items()})
        self.assertEqual(ctx.exception.status_code, 404)

    def test_create_manifest_empty_items_raises_422(self):
        with self.assertRaises(HTTPException) as ctx:
            self.create_shipment_manifest("ORD-1004", {"items": []})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_create_manifest_blank_description_raises_422(self):
        with self.assertRaises(HTTPException) as ctx:
            self.create_shipment_manifest(
                "ORD-1004",
                {"items": [{"description": "", "expected_qty": 1}]},
            )
        self.assertEqual(ctx.exception.status_code, 422)

    def test_create_manifest_zero_qty_raises_422(self):
        with self.assertRaises(HTTPException) as ctx:
            self.create_shipment_manifest(
                "ORD-1004",
                {"items": [{"description": "Widget", "expected_qty": 0}]},
            )
        self.assertEqual(ctx.exception.status_code, 422)

    def test_create_manifest_items_not_list_raises_422(self):
        with self.assertRaises(HTTPException) as ctx:
            self.create_shipment_manifest("ORD-1004", {"items": "not a list"})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_create_manifest_negative_unit_value_raises_422(self):
        with self.assertRaises(HTTPException) as ctx:
            self.create_shipment_manifest(
                "ORD-1004",
                {"items": [{"description": "Widget", "expected_qty": 1,
                            "unit_value_cents": -50}]},
            )
        self.assertEqual(ctx.exception.status_code, 422)

    # -- GET /api/shipments/{id}/manifest ------------------------------------

    def test_get_shipment_manifest_returns_most_recent(self):
        self.create_shipment_manifest("ORD-1004", {"items": _valid_items()})
        result = self.get_shipment_manifest("ORD-1004")
        self.assertEqual(result["shipment_order_id"], "ORD-1004")

    def test_get_shipment_manifest_no_manifest_raises_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self.get_shipment_manifest("ORD-1001")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_get_shipment_manifest_missing_shipment_raises_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self.get_shipment_manifest("ORD-NONEXISTENT")
        self.assertEqual(ctx.exception.status_code, 404)

    # -- GET /api/manifests/{manifest_id} ------------------------------------

    def test_get_manifest_by_id_returns_correct_record(self):
        created = self.create_shipment_manifest("ORD-1004", {"items": _valid_items()})
        fetched = self.get_manifest_by_id(created["id"])
        self.assertEqual(fetched["id"], created["id"])

    def test_get_manifest_by_id_unknown_raises_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self.get_manifest_by_id("00000000-0000-0000-0000-000000000000")
        self.assertEqual(ctx.exception.status_code, 404)

    # -- PUT /api/manifests/{manifest_id} ------------------------------------

    def test_update_draft_replaces_items(self):
        created = self.create_shipment_manifest("ORD-1004", {"items": _valid_items()})
        updated = self.update_manifest_by_id(
            created["id"],
            {"items": [{"description": "Replacement item", "expected_qty": 5}]},
        )
        self.assertEqual(len(updated["items"]), 1)
        self.assertEqual(updated["items"][0]["description"], "Replacement item")
        self.assertEqual(updated["items"][0]["expected_qty"], 5)

    def test_update_unknown_manifest_raises_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self.update_manifest_by_id(
                "00000000-0000-0000-0000-000000000000",
                {"items": [{"description": "Item", "expected_qty": 1}]},
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_update_empty_items_raises_422(self):
        created = self.create_shipment_manifest("ORD-1004", {"items": _valid_items()})
        with self.assertRaises(HTTPException) as ctx:
            self.update_manifest_by_id(created["id"], {"items": []})
        self.assertEqual(ctx.exception.status_code, 422)

    # -- POST /api/manifests/{manifest_id}/finalize --------------------------

    def test_finalize_sets_finalized_status_and_hash(self):
        created = self.create_shipment_manifest("ORD-1004", {"items": _valid_items()})
        finalized = self.finalize_manifest_by_id(created["id"])
        self.assertEqual(finalized["status"], "FINALIZED")
        self.assertIsNotNone(finalized["manifest_hash"])
        self.assertEqual(len(finalized["manifest_hash"]), 64)

    def test_finalize_already_finalized_raises_422(self):
        created = self.create_shipment_manifest("ORD-1004", {"items": _valid_items()})
        self.finalize_manifest_by_id(created["id"])
        with self.assertRaises(HTTPException) as ctx:
            self.finalize_manifest_by_id(created["id"])
        self.assertEqual(ctx.exception.status_code, 422)

    def test_update_after_finalize_raises_422(self):
        created = self.create_shipment_manifest("ORD-1004", {"items": _valid_items()})
        self.finalize_manifest_by_id(created["id"])
        with self.assertRaises(HTTPException) as ctx:
            self.update_manifest_by_id(
                created["id"],
                {"items": [{"description": "Sneaky edit", "expected_qty": 1}]},
            )
        self.assertEqual(ctx.exception.status_code, 422)

    def test_finalize_unknown_manifest_raises_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self.finalize_manifest_by_id("00000000-0000-0000-0000-000000000000")
        self.assertEqual(ctx.exception.status_code, 404)

    # -- Checkout isolation --------------------------------------------------

    def test_checkout_catalogue_unaffected_by_manifest_api(self):
        self.create_shipment_manifest("ORD-1004", {"items": _valid_items()})
        products = get_catalogue()
        self.assertEqual(len(products), 3)
        skus = {p["sku"] for p in products}
        self.assertEqual(skus, {"SHIP-STD-001", "SHIP-HEV-002", "SHIP-FRA-003"})


if __name__ == "__main__":
    unittest.main()
