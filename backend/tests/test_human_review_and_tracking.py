import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import app.store as store
from app.store import (
    init_db,
    create_order,
    set_paypal_order_id,
    set_capture,
    create_shipment_for_order,
    create_manifest_from_checkout_order,
    finalize_manifest,
    create_inspection,
    get_inspection,
    get_shipment_by_order_id,
)
from app.main import review_packing_inspection, submit_shipment_tracking


class HumanReviewAndTrackingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._tmp_path = self._tmp.name
        store.DB_PATH = Path(self._tmp_path)
        init_db()

        self.order = create_order(
            [{"sku": "MUG-CER-001", "quantity": 1}],
            "USD",
            buyer_name="Demo Buyer",
            shipping_address={
                "address_line_1": "12 Test Road",
                "city": "Hyderabad",
                "state": "Telangana",
                "postal_code": "500001",
                "country_code": "IN",
            },
        )
        set_paypal_order_id(self.order["id"], "PAYPALORDER123")
        set_capture(self.order["id"], "CAPTURE123", "PAID")
        self.shipment = create_shipment_for_order(
            checkout_order_id=self.order["id"],
            paypal_order_id="PAYPALORDER123",
            paypal_capture_id="CAPTURE123",
            amount=self.order["total"],
            currency="USD",
            shipping_address=self.order["shipping_address"],
            buyer_name=self.order["buyer_name"],
        )
        self.manifest = create_manifest_from_checkout_order(
            self.shipment["order_id"], self.order["id"]
        )
        self.manifest = finalize_manifest(self.manifest["id"])
        self.inspection = self._create_inspection()

    def tearDown(self):
        store.DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shipproof.db"
        if os.path.exists(self._tmp_path):
            os.unlink(self._tmp_path)

    def _create_inspection(self):
        return create_inspection(
            manifest_id=self.manifest["id"],
            manifest_hash=self.manifest["manifest_hash"],
            model_used="gemini-test-model",
            ai_result={
                "inspection_summary": "One mug is visible in the packing photo.",
                "item_checks": [],
                "additional_observations": {},
            },
            photo_records=[
                {
                    "id": "PHOTO-" + str(len(store.list_inspections_for_manifest(self.manifest["id"])) + 1),
                    "sha256": "a" * 64,
                    "mime_type": "image/jpeg",
                    "size_bytes": 1024,
                }
            ],
        )

    def test_human_decision_is_persisted_without_changing_ai_result(self):
        result = review_packing_inspection(
            self.inspection["id"],
            {
                "decision": "APPROVED",
                "reviewer_label": "Merchant",
                "notes": "Visible items match the finalized manifest.",
            },
        )
        saved = get_inspection(self.inspection["id"])

        self.assertEqual(result["inspection_status"], "APPROVED")
        self.assertEqual(saved["inspection_status"], "APPROVED")
        self.assertEqual(saved["ai_result"]["inspection_summary"], "One mug is visible in the packing photo.")
        self.assertEqual(len(saved["review_history"]), 1)
        self.assertEqual(saved["review_history"][0]["decision"], "APPROVED")
        self.assertEqual(saved["review_history"][0]["reviewer_label"], "Merchant")

    def test_rejection_and_correction_require_explanation(self):
        with self.assertRaises(HTTPException) as ctx:
            review_packing_inspection(
                self.inspection["id"],
                {"decision": "NEEDS_CORRECTION", "reviewer_label": "Merchant"},
            )
        self.assertEqual(ctx.exception.status_code, 422)

        result = review_packing_inspection(
            self.inspection["id"],
            {
                "decision": "NEEDS_CORRECTION",
                "reviewer_label": "Merchant",
                "notes": "Please include a wider photo showing the mug and protective padding.",
            },
        )
        self.assertEqual(result["inspection_status"], "NEEDS_CORRECTION")

    def test_a_reviewed_inspection_cannot_be_overwritten(self):
        review_packing_inspection(
            self.inspection["id"],
            {
                "decision": "REJECTED",
                "reviewer_label": "Merchant",
                "notes": "The photographed item does not match the order.",
            },
        )
        with self.assertRaises(HTTPException) as ctx:
            review_packing_inspection(
                self.inspection["id"],
                {"decision": "APPROVED", "reviewer_label": "Merchant"},
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(get_inspection(self.inspection["id"])["inspection_status"], "REJECTED")

    def test_tracking_is_blocked_until_latest_inspection_is_approved(self):
        with patch.dict(os.environ, {"PAYPAL_TRACKING_SUBMISSION_ENABLED": "true"}):
            with patch("app.main.submit_tracking") as mock_submit:
                with self.assertRaises(HTTPException) as ctx:
                    submit_shipment_tracking(
                        self.shipment["order_id"],
                        {"tracking_number": "DELH123", "carrier": "OTHER", "carrier_name_other": "Delhivery"},
                    )
        self.assertEqual(ctx.exception.status_code, 409)
        mock_submit.assert_not_called()

    @patch.dict(os.environ, {"PAYPAL_TRACKING_SUBMISSION_ENABLED": "true"})
    @patch("app.main.submit_tracking")
    def test_tracking_uses_persisted_paypal_ids_and_paid_order_items(self, mock_submit):
        review_packing_inspection(
            self.inspection["id"],
            {
                "decision": "APPROVED",
                "reviewer_label": "Merchant",
                "notes": "Visible contents match the order manifest.",
            },
        )
        mock_submit.return_value = {"id": "PAYPALORDER123", "status": "COMPLETED"}

        result = submit_shipment_tracking(
            self.shipment["order_id"],
            {
                "tracking_number": "DELH123456",
                "carrier": "OTHER",
                "carrier_name_other": "Delhivery",
                "notify_payer": True,
                "paypal_order_id": "ATTACKER-ORDER-ID",
                "paypal_capture_id": "ATTACKER-CAPTURE-ID",
            },
        )

        sent = mock_submit.call_args.args[0]
        self.assertEqual(sent["paypal_order_id"], "PAYPALORDER123")
        self.assertEqual(sent["paypal_capture_id"], "CAPTURE123")
        self.assertEqual(sent["items"][0]["sku"], "MUG-CER-001")
        self.assertEqual(sent["items"][0]["quantity"], 1)
        self.assertEqual(result["submitted"], True)

        saved = get_shipment_by_order_id(self.shipment["order_id"])
        self.assertEqual(saved["tracking_submission_status"], "SUBMITTED")
        self.assertEqual(saved["tracking_number"], "DELH123456")
        self.assertEqual(saved["carrier"], "OTHER")
        self.assertEqual(saved["carrier_name_other"], "Delhivery")
        self.assertEqual(saved["status"], "SHIPPED")
        self.assertIsNotNone(saved["paypal_tracking_submitted_at"])

        repeated = submit_shipment_tracking(
            self.shipment["order_id"],
            {
                "tracking_number": "DELH123456",
                "carrier": "OTHER",
                "carrier_name_other": "Delhivery",
                "notify_payer": True,
            },
        )
        self.assertTrue(repeated["already_submitted"])
        self.assertEqual(mock_submit.call_count, 1)

    @patch.dict(os.environ, {"PAYPAL_TRACKING_SUBMISSION_ENABLED": "true"})
    @patch("app.main.submit_tracking", side_effect=RuntimeError("temporary PayPal failure"))
    def test_failed_tracking_write_can_be_retried(self, mock_submit):
        review_packing_inspection(
            self.inspection["id"],
            {
                "decision": "APPROVED",
                "reviewer_label": "Merchant",
                "notes": "Contents visibly match.",
            },
        )
        with self.assertRaises(HTTPException) as ctx:
            submit_shipment_tracking(
                self.shipment["order_id"],
                {"tracking_number": "TRACK123", "carrier": "DHL"},
            )
        self.assertEqual(ctx.exception.status_code, 502)
        saved = get_shipment_by_order_id(self.shipment["order_id"])
        self.assertEqual(saved["tracking_submission_status"], "FAILED")
        self.assertEqual(saved["status"], "ON_HOLD")


if __name__ == "__main__":
    unittest.main()
