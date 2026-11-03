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
            "amount": {"currency_code": "USD", "value": "50.00"},
            "payments": {
                "captures": [
                    {
                        "id": "CAPTURE-789",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "50.00"},
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
                        {"sku": "MUG-CER-001", "quantity": 2},
                        {"sku": "TOTE-COT-002", "quantity": 1},
                    ],
                    "currency": "USD",
                    "buyer_name": "Demo Buyer",
                    "shipping_address": {
                        "address_line_1": "123 Sample Street",
                        "city": "Austin",
                        "state": "TX",
                        "postal_code": "78701",
                        "country_code": "US",
                    },
                }
            )

    def test_checkout_sends_order_items_and_shipping_details_to_paypal(self):
        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token:
            mock_token.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-789",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            result = self._create_mock_order()

        self.assertEqual(result["total"], "50.00")
        args = mock_create.call_args
        self.assertEqual(args.args[1], 5000)
        self.assertEqual(args.args[2], "USD")
        self.assertEqual(args.kwargs["items"][0]["name"], "Ceramic Coffee Mug")
        self.assertEqual(args.kwargs["items"][0]["quantity"], 2)
        self.assertEqual(args.kwargs["shipping_address"]["country_code"], "US")
        self.assertEqual(args.kwargs["buyer_name"], "Demo Buyer")

    def test_checkout_rejects_missing_delivery_details(self):
        with patch("app.main.get_access_token") as mock_token:
            with self.assertRaises(HTTPException) as ctx:
                create_checkout_order({
                    "items": [{"sku": "MUG-CER-001", "quantity": 1}],
                    "currency": "USD",
                })
        self.assertEqual(ctx.exception.status_code, 422)
        mock_token.assert_not_called()

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_successful_payment_creates_shipment(self, mock_token, mock_capture):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_SUCCESS

        order_res = self._create_mock_order()
        capture_res = capture_checkout_order(order_res["order_id"], {})

        self.assertEqual(capture_res["payment_status"], "PAID")
        self.assertEqual(capture_res["total"], "50.00")
        self.assertEqual(len(capture_res["items"]), 2)
        self.assertEqual(capture_res["items"][0]["name"], "Ceramic Coffee Mug")
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
        self.assertEqual(float(shipment["amount"]), 50.00)
        self.assertEqual(shipment["currency"], "USD")
        self.assertEqual(shipment["status"], "ON_HOLD")
        self.assertIsNone(shipment["shipped_date"])
        self.assertEqual(shipment["tracking_number"], "")
        self.assertIn("123 Sample Street", shipment["shipping_address"])
        self.assertEqual(shipment["buyer_name"], "Demo Buyer")
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
        order = create_order([{"sku": "MUG-CER-001", "quantity": 1}], "USD")
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-1",
                amount="18.00",
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
                amount="18.00",
                currency="USD",
            )
        self.assertIn("order ID mismatch", str(ctx.exception))

        # 3. PayPal capture ID mismatch rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-WRONG",
                amount="18.00",
                currency="USD",
            )
        self.assertIn("capture ID mismatch", str(ctx.exception))

        # 4. Currency mismatch rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-1",
                amount="18.00",
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
            amount="18.00",
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
            amount="18.00",
            currency="USD",
        )
        self.assertEqual(retried["id"], shipment["id"])

        # 8. Retry with incorrect PayPal order ID is rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-INCORRECT-RETRY",
                paypal_capture_id="CAP-1",
                amount="18.00",
                currency="USD",
            )
        self.assertIn("order ID mismatch", str(ctx.exception))

        # 9. Retry with incorrect PayPal capture ID is rejected
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-1",
                paypal_capture_id="CAP-INCORRECT-RETRY",
                amount="18.00",
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
                amount="18.00",
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
                amount="18.00",
                currency="USD",
            )
        self.assertIn("unpaid", str(ctx.exception).lower())

        # Reset back to PAID
        store.set_capture(order["id"], "CAP-1", "PAID")

        # 13. Collision: Another order trying to use the same capture ID raises error
        order2 = create_order([{"sku": "MUG-CER-001", "quantity": 1}], "USD")
        store.set_paypal_order_id(order2["id"], "PP-2")
        store.set_capture(order2["id"], "CAP-2", "PAID")

        # Directly attempt to invoke create_shipment_for_order with CAP-1 which belongs to order1's shipment
        with self.assertRaises(ValueError) as ctx:
            store.create_shipment_for_order(
                checkout_order_id=order2["id"],
                paypal_order_id="PP-2",
                paypal_capture_id="CAP-1",
                amount="18.00",
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

        # The paid checkout creates the manifest from the exact persisted order items.
        manifest = get_manifest_for_shipment(shipment_order_id)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["status"], "DRAFT")
        self.assertEqual(manifest["shipment_order_id"], shipment_order_id)
        self.assertEqual(len(manifest["items"]), 2)
        by_sku = {item["sku"]: item for item in manifest["items"]}
        self.assertEqual(by_sku["MUG-CER-001"]["description"], "Ceramic Coffee Mug")
        self.assertEqual(by_sku["MUG-CER-001"]["expected_qty"], 2)
        self.assertTrue(by_sku["MUG-CER-001"]["fragile"])
        self.assertEqual(by_sku["TOTE-COT-002"]["expected_qty"], 1)
        self.assertFalse(by_sku["TOTE-COT-002"]["fragile"])
        self.assertTrue(all(item["source_order_item_id"] for item in manifest["items"]))

        # Retries return the same manifest rather than duplicating it.
        recovered = store.create_manifest_from_checkout_order(
            shipment_order_id, order_res["order_id"]
        )
        self.assertEqual(recovered["id"], manifest["id"])

        # Saving a draft in the merchant UI must retain each order-item source link.
        edited_items = [
            {
                "sku": item["sku"],
                "description": item["description"],
                "expected_qty": item["expected_qty"],
                "unit_value_cents": item["unit_value_cents"],
                "fragile": item["fragile"],
                "source_order_item_id": item["source_order_item_id"],
            }
            for item in manifest["items"]
        ]
        updated = store.update_manifest(
            manifest["id"], edited_items, notes="Checked against paid order"
        )
        self.assertEqual(
            {item["source_order_item_id"] for item in updated["items"]},
            {item["source_order_item_id"] for item in manifest["items"]},
        )

        # A source ID from outside this shipment's order must be rejected.
        forged_items = [dict(item) for item in edited_items]
        forged_items[0]["source_order_item_id"] = "not-an-order-item"
        with self.assertRaises(ValueError):
            store.update_manifest(manifest["id"], forged_items)

        # Rejected edits must not damage the saved manifest.
        saved_after_rejection = get_manifest_for_shipment(shipment_order_id)
        self.assertEqual(
            {item["source_order_item_id"] for item in saved_after_rejection["items"]},
            {item["source_order_item_id"] for item in manifest["items"]},
        )

        # Finalize the generated manifest.
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

        order = create_order([{"sku": "MUG-CER-001", "quantity": 1}], "USD")
        store.set_paypal_order_id(order["id"], "PP-CONC-1")
        store.set_capture(order["id"], "CAP-CONC-1", "PAID")

        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            return store.create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id="PP-CONC-1",
                paypal_capture_id="CAP-CONC-1",
                amount="18.00",
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

        order_a = create_order([{"sku": "MUG-CER-001", "quantity": 1}], "USD")
        order_b = create_order([{"sku": "MUG-CER-001", "quantity": 1}], "USD")

        # Mark BOTH checkout orders as PAID using distinct capture IDs
        store.set_paypal_order_id(order_a["id"], "PP-A")
        store.set_capture(order_a["id"], "CAP-A", "PAID")

        store.set_paypal_order_id(order_b["id"], "PP-B")
        store.set_capture(order_b["id"], "CAP-B", "PAID")

        # First, order_a creates a valid shipment with its capture CAP-A
        shipment_a = store.create_shipment_for_order(
            checkout_order_id=order_a["id"],
            paypal_order_id="PP-A",
            paypal_capture_id="CAP-A",
            amount="18.00",
            currency="USD",
        )
        self.assertIsNotNone(shipment_a)

        # Now test concurrent calls where order_a retries its legitimate CAP-A
        # while order_b simultaneously attempts to hijack CAP-A
        barrier = threading.Barrier(2)

        def worker_legitimate():
            barrier.wait()
            return store.create_shipment_for_order(
                checkout_order_id=order_a["id"],
                paypal_order_id="PP-A",
                paypal_capture_id="CAP-A",
                amount="18.00",
                currency="USD",
            )

        def worker_hijack():
            barrier.wait()
            # Order B attempts to claim CAP-A which already belongs to Order A
            return store.create_shipment_for_order(
                checkout_order_id=order_b["id"],
                paypal_order_id="PP-B",
                paypal_capture_id="CAP-A",
                amount="18.00",
                currency="USD",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_legit = executor.submit(worker_legitimate)
            fut_hijack = executor.submit(worker_hijack)

            res_legit = None
            res_hijack = None
            err_legit = None
            err_hijack = None

            try:
                res_legit = fut_legit.result()
            except Exception as e:
                err_legit = e

            try:
                res_hijack = fut_hijack.result()
            except Exception as e:
                err_hijack = e

        # Legitimate caller succeeds without error
        self.assertIsNone(err_legit)
        self.assertIsNotNone(res_legit)
        self.assertEqual(res_legit["id"], shipment_a["id"])

        # Hijack attempt must fail specifically with the capture collision error
        self.assertIsNone(res_hijack)
        self.assertIsNotNone(err_hijack)
        self.assertIsInstance(err_hijack, ValueError)
        self.assertIn("already belongs to another checkout order", str(err_hijack))

        # In SQLite, exactly 1 shipment exists for CAP-A, owned by order_a
        conn = store._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM shipments WHERE paypal_capture_id = 'CAP-A'"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["checkout_order_id"], order_a["id"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
