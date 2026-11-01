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
        self.assertEqual(shipment["status"], "ON_HOLD")
        self.assertIsNone(shipment["shipped_date"])
        self.assertEqual(shipment["tracking_number"], "")
        self.assertEqual(shipment["shipping_address"], "")
        self.assertEqual(shipment["carrier"], "OTHER")
        self.assertEqual(shipment["carrier_name_other"], "UNASSIGNED")

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

    def test_create_shipment_for_order_validations(self):
        # 1. Unpaid order rejected
        order = create_order([{"sku": "SHIP-STD-001", "quantity": 1}], "USD")
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-1",
                amount="12.99",
                currency="USD",
            )
        self.assertIn("unpaid", str(ctx.exception).lower())

        # Set order to PAID
        store.set_paypal_order_id(order["id"], "PP-1")
        store.set_capture(order["id"], "CAP-1", "PAID")

        # 2. PayPal order ID mismatch rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-WRONG",
                paypal_capture_id="CAP-1",
                amount="12.99",
                currency="USD",
            )
        self.assertIn("order ID mismatch", str(ctx.exception))

        # 3. PayPal capture ID mismatch rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-WRONG",
                amount="12.99",
                currency="USD",
            )
        self.assertIn("capture ID mismatch", str(ctx.exception))

        # 4. Currency mismatch rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-1",
                amount="12.99",
                currency="EUR",
            )
        self.assertIn("Currency mismatch", str(ctx.exception))

        # 5. Amount mismatch rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-1",
                amount="99.99",
                currency="USD",
            )
        self.assertIn("Amount mismatch", str(ctx.exception))

        # 6. Valid creation succeeds
        shipment = store.create_shipment_for_order(
            checkout_order_id=order["id"],
            paypal_order_id="PP-1",
            paypal_capture_id="CAP-1",
            amount="12.99",
            currency="USD",
        )
        self.assertEqual(shipment["status"], "ON_HOLD")
        self.assertIsNone(shipment["shipped_date"])
        self.assertEqual(shipment["carrier_name_other"], "UNASSIGNED")

        # 7. Valid retry returns existing shipment
        retried = store.create_shipment_for_order(
            checkout_order_id=order["id"],
            paypal_order_id="PP-1",
            paypal_capture_id="CAP-1",
            amount="12.99",
            currency="USD",
        )
        self.assertEqual(retried["id"], shipment["id"])

        # 8. Retry with incorrect PayPal order ID is rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-INCORRECT-RETRY",
                paypal_capture_id="CAP-1",
                amount="12.99",
                currency="USD",
            )
        self.assertIn("order ID mismatch", str(ctx.exception))

        # 9. Retry with incorrect PayPal capture ID is rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-INCORRECT-RETRY",
                amount="12.99",
                currency="USD",
            )
        self.assertIn("capture ID mismatch", str(ctx.exception))

        # 10. Retry with incorrect amount is rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-1",
                amount="50.00",
                currency="USD",
            )
        self.assertIn("Amount mismatch", str(ctx.exception))

        # 11. Retry with incorrect currency is rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-1",
                amount="12.99",
                currency="GBP",
            )
        self.assertIn("Currency mismatch", str(ctx.exception))

        # 12. Retry after payment status altered/reset to CREATED is rejected
        store.set_capture(order["id"], "CAP-1", "CREATED")
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-1",
                amount="12.99",
                currency="USD",
            )
        self.assertIn("unpaid", str(ctx.exception).lower())

        # Reset back to PAID
        store.set_capture(order["id"], "CAP-1", "PAID")

        # 13. Collision: Another order trying to use the same capture ID raises error
        order2 = create_order([{"sku": "SHIP-STD-001", "quantity": 1}], "USD")
        store.set_paypal_order_id(order2["id"], "PP-2")
        store.set_capture(order2["id"], "CAP-2", "PAID")

        # Directly attempt to invoke create_shipment_for_order with CAP-1 which belongs to order1's shipment
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order2["id"],
                paypal_order_id="PP-2",
                paypal_capture_id="CAP-1",
                amount="12.99",
                currency="USD",
            )
        self.assertIn("already belongs to another checkout order", str(ctx.exception))

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

    def test_concurrent_shipment_creation_same_order(self):
        """Simultaneous calls to create_shipment_for_order for the same paid checkout order."""
        import threading
        from concurrent.futures import ThreadPoolExecutor

        order = create_order([{"sku": "SHIP-STD-001", "quantity": 1}], "USD")
        store.set_paypal_order_id(order["id"], "PP-CONC-1")
        store.set_capture(order["id"], "CAP-CONC-1", "PAID")

        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            return store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-CONC-1",
                paypal_capture_id="CAP-CONC-1",
                amount="12.99",
                currency="USD",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut1 = executor.submit(worker)
            fut2 = executor.submit(worker)
            res1 = fut1.result()
            res2 = fut2.result()

        # Both calls complete successfully and return the same shipment
        self.assertEqual(res1["id"], res2["id"])
        self.assertEqual(res1["order_id"], res2["order_id"])

        # Exactly 1 shipment exists in SQLite
        shipments = list_shipments()
        self.assertEqual(len(shipments), 1)
        self.assertEqual(shipments[0]["id"], res1["id"])

    def test_concurrent_shipment_creation_different_orders_same_capture_collision(self):
        """Simultaneous attempts to associate one capture ID with two different checkout orders."""
        import threading
        from concurrent.futures import ThreadPoolExecutor

        order_a = create_order([{"sku": "SHIP-STD-001", "quantity": 1}], "USD")
        order_b = create_order([{"sku": "SHIP-STD-001", "quantity": 1}], "USD")

        store.set_paypal_order_id(order_a["id"], "PP-A")
        store.set_capture(order_a["id"], "SHARED-CAP-1", "PAID")

        # Manually link order_b in DB with a distinct capture first to satisfy order table unique constraint,
        # then test create_shipment_for_order attempting to claim SHARED-CAP-1
        store.set_paypal_order_id(order_b["id"], "PP-B")

        barrier = threading.Barrier(2)

        def worker_a():
            barrier.wait()
            return store.create_shipment_for_order(
                checkout_order_id=order_a["id"],
                paypal_order_id="PP-A",
                paypal_capture_id="SHARED-CAP-1",
                amount="12.99",
                currency="USD",
            )

        def worker_b():
            barrier.wait()
            # Order B attempts to claim SHARED-CAP-1
            return store.create_shipment_for_order(
                checkout_order_id=order_b["id"],
                paypal_order_id="PP-B",
                paypal_capture_id="SHARED-CAP-1",
                amount="12.99",
                currency="USD",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_a = executor.submit(worker_a)
            fut_b = executor.submit(worker_b)

            res_a = None
            res_b = None
            err_a = None
            err_b = None

            try:
                res_a = fut_a.result()
            except Exception as e:
                err_a = e

            try:
                res_b = fut_b.result()
            except Exception as e:
                err_b = e

        # Exactly one order succeeds; the other gets an error (order_b is unpaid or collision error)
        # Because SHARED-CAP-1 cannot belong to both orders
        successes = [r for r in [res_a, res_b] if r is not None]
        errors = [e for e in [err_a, err_b] if e is not None]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)

        # In SQLite, exactly 1 shipment exists with SHARED-CAP-1
        conn = store._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM shipments WHERE paypal_capture_id = 'SHARED-CAP-1'"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["checkout_order_id"], successes[0]["checkout_order_id"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
