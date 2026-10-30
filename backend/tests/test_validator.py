import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.paypal_client import PayPalConfigurationError, submit_tracking
from app.validator import validate_order


def valid_order(**overrides):
    order = {
        "order_id": "ORD-1",
        "transaction_id": "8MC585209K746392H",
        "tracking_number": "TRACK-123",
        "carrier": "FEDEX",
        "status": "SHIPPED",
        "shipped_date": str(date.today()),
        "delivered_date": None,
    }
    order.update(overrides)
    return order


class ValidatorTests(unittest.TestCase):
    def test_missing_tracking_number_is_blocked(self):
        result = validate_order(valid_order(tracking_number=""))
        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("missing_tracking_number", {issue["code"] for issue in result["issues"]})

    def test_delivery_before_shipment_is_blocked(self):
        result = validate_order(valid_order(shipped_date="2026-10-27", delivered_date="2026-10-26", status="DELIVERED"))
        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("delivery_before_shipment", {issue["code"] for issue in result["issues"]})

    def test_future_shipment_date_is_blocked(self):
        result = validate_order(valid_order(shipped_date=str(date.today() + timedelta(days=1))))
        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("shipment_date_in_future", {issue["code"] for issue in result["issues"]})

    def test_other_carrier_requires_its_name(self):
        result = validate_order(valid_order(carrier="OTHER"))
        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("missing_carrier_name_other", {issue["code"] for issue in result["issues"]})

    def test_tracking_write_is_disabled_by_default(self):
        with patch.dict(os.environ, {"PAYPAL_TRACKING_SUBMISSION_ENABLED": "false"}, clear=False):
            with self.assertRaises(PayPalConfigurationError):
                submit_tracking(valid_order())


if __name__ == "__main__":
    unittest.main()
