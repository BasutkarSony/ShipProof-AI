import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import app.store as store
from app.store import (
    init_db,
    create_order,
    get_order,
    get_shipment_by_order_id,
    get_shipment_by_checkout_order_id,
    list_shipments,
    create_manifest,
    get_manifest_for_shipment,
    finalize_manifest,
)
from app.main import (
    create_checkout_order,
    capture_checkout_order,
    list_orders,
    create_shipment_manifest,
    get_shipment_manifest,
)

CAPTURE_SUCCESS = {
    "id": "PAYPAL-ORDER-789",
    "status": "COMPLETED",
    "purchase_units": [
        {
            "reference_id": "default",
            "amount": {"currency_code": "USD", "value": "44.73"},
            "payments": {
                "captures": [
                    {
                        "id": "CAPTURE-789",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "44.73"},
                    }
                ]
            },
        }
    ],
}


class PayPalToShipmentIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._tmp_path = self._tmp.name
        store.DB_PATH = Path(self._tmp_path)
        init_db()

    def tearDown(self):
        store.DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shipproof.db"
        if os.path.exists(self._tmp_path):
            os.unlink(self._tmp_path)

    def _create_mock_order(self):
        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token:
            mock_token.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-789",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            return create_checkout_order(
                {
                    "items": [
                        {"sku": "SHIP-STD-001", "quantity": 2},
                        {"sku": "SHIP-FRA-003", "quantity": 1},
                    ],
                    "currency": "USD",
                }
            )

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_successful_payment_creates_shipment(self, mock_token, mock_capture):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_SUCCESS

        order_res = self._create_mock_order()
        capture_res = capture_checkout_order(order_res["order_id"], {})

        self.assertEqual(capture_res["payment_status"], "PAID")
        self.assertIsNotNone(capture_res.get("shipment_id"))
        self.assertIsNotNone(capture_res.get("shipment_order_id"))

        # Verify shipment persisted and linked to checkout order
        shipment = get_shipment_by_checkout_order_id(order_res["order_id"])
        self.assertIsNotNone(shipment)
        self.assertEqual(shipment["id"], capture_res["shipment_id"])
        self.assertEqual(shipment["order_id"], capture_res["shipment_order_id"])
        self.assertEqual(shipment["checkout_order_id"], order_res["order_id"])
        self.assertEqual(shipment["paypal_capture_id"], "CAPTURE-789")
        self.assertEqual(shipment["paypal_order_id"], "PAYPAL-ORDER-789")
        self.assertEqual(float(shipment["amount"]), 44.73)
        self.assertEqual(shipment["currency"], "USD")
        self.assertEqual(shipment["status"], "SHIPPED")

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_rejection_of_failed_or_unverified_payments_creates_no_shipment(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.side_effect = RuntimeError("Payment rejected by bank")

        order_res = self._create_mock_order()
        with self.assertRaises(HTTPException):
            capture_checkout_order(order_res["order_id"], {})

        # Order must be FAILED, no shipment created
        order = get_order(order_res["order_id"])
        self.assertEqual(order["payment_status"], "FAILED")
        self.assertIsNone(get_shipment_by_checkout_order_id(order_res["order_id"]))
        self.assertEqual(len(list_shipments()), 0)

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_duplicate_capture_is_idempotent_and_does_not_duplicate_shipment(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_SUCCESS

        order_res = self._create_mock_order()
        res1 = capture_checkout_order(order_res["order_id"], {})
        self.assertFalse(res1["already_captured"])

        res2 = capture_checkout_order(order_res["order_id"], {})
        self.assertTrue(res2["already_captured"])
        self.assertEqual(res1["shipment_order_id"], res2["shipment_order_id"])

        # Exactly 1 shipment exists
        shipments = list_shipments()
        self.assertEqual(len(shipments), 1)

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_recovery_if_payment_succeeded_but_shipment_was_missing(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_SUCCESS

        order_res = self._create_mock_order()
        # Mark order PAID directly in store without creating shipment
        store.set_capture(order_res["order_id"], "CAPTURE-MANUAL-1", "PAID")
        self.assertIsNone(get_shipment_by_checkout_order_id(order_res["order_id"]))

        # Calling capture_checkout_order should recover and create the shipment
        res = capture_checkout_order(order_res["order_id"], {})
        self.assertTrue(res["already_captured"])
        self.assertIsNotNone(res["shipment_order_id"])

        recovered_shipment = get_shipment_by_checkout_order_id(order_res["order_id"])
        self.assertIsNotNone(recovered_shipment)
        self.assertEqual(recovered_shipment["paypal_capture_id"], "CAPTURE-MANUAL-1")

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_manifest_workflow_for_paid_shipment(self, mock_token, mock_capture):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_SUCCESS

        order_res = self._create_mock_order()
        capture_res = capture_checkout_order(order_res["order_id"], {})
        shipment_order_id = capture_res["shipment_order_id"]

        # 1. Create a DRAFT manifest for this shipment (goods being shipped, not packaging supplies)
        goods = [
            {"sku": "PROD-A", "description": "Handmade Ceramic Vase", "expected_qty": 2, "unit_value_cents": 2500, "fragile": True},
            {"sku": "PROD-B", "description": "Linen Table Runner", "expected_qty": 1, "unit_value_cents": 1800, "fragile": False},
        ]
        manifest = create_shipment_manifest(shipment_order_id, {"items": goods, "notes": "Fragile items inside"})
        self.assertEqual(manifest["status"], "DRAFT")
        self.assertEqual(manifest["shipment_order_id"], shipment_order_id)
        self.assertEqual(len(manifest["items"]), 2)

        # 2. Get manifest for shipment
        fetched = get_shipment_manifest(shipment_order_id)
        self.assertEqual(fetched["id"], manifest["id"])

        # 3. Finalize manifest
        finalized = finalize_manifest(manifest["id"])
        self.assertEqual(finalized["status"], "FINALIZED")
        self.assertIsNotNone(finalized["manifest_hash"])
        self.assertEqual(len(finalized["manifest_hash"]), 64)

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_compatibility_with_existing_sample_shipments(self, mock_token, mock_capture):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_SUCCESS

        # Initially, list_orders has the 5 sample shipments
        orders_before = list_orders()["orders"]
        sample_ids = {o["order_id"] for o in orders_before}
        self.assertIn("ORD-1001", sample_ids)
        self.assertIn("ORD-1004", sample_ids)

        # Create a paid shipment
        order_res = self._create_mock_order()
        capture_res = capture_checkout_order(order_res["order_id"], {})
        new_shipment_id = capture_res["shipment_order_id"]

        # Combined list_orders contains both sample shipments and the new persistent shipment
        orders_after = list_orders()["orders"]
        after_ids = {o["order_id"] for o in orders_after}
        self.assertIn(new_shipment_id, after_ids)
        self.assertIn("ORD-1001", after_ids)
        self.assertIn("ORD-1004", after_ids)
        self.assertEqual(len(orders_after), len(orders_before) + 1)


if __name__ == "__main__":
    unittest.main()
