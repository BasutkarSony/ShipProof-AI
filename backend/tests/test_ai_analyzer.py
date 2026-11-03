import os
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai_analyzer import analyze_shipment_evidence


class AIAnalyzerTests(unittest.TestCase):
    def test_standard_valid_shipment_analysis(self):
        order = {
            "order_id": "ORD-1001",
            "transaction_id": "8MC585209K746392H",
            "tracking_number": "781234567890",
            "carrier": "FEDEX",
            "status": "DELIVERED",
            "shipped_date": "2026-10-25",
            "delivered_date": "2026-10-28",
            "amount": 120.00,
            "currency": "USD",
            "shipping_address": "Seattle, WA 98101",
            "evidence_text": "Carrier scan: Delivered at front porch in Seattle, WA 98101.",
        }
        result = analyze_shipment_evidence(order)
        self.assertGreaterEqual(result["readiness_score"], 85)
        self.assertEqual(result["protection_tier"], "FULL_PROTECTION_READY")
        self.assertTrue(result["seller_protection"]["item_not_received_eligible"])
        self.assertFalse(result["seller_protection"]["signature_confirmation"]["required"])
        self.assertEqual(result["seller_protection"]["signature_confirmation"]["status"], "NOT_REQUIRED")

    def test_high_value_order_missing_signature_is_flagged(self):
        order = {
            "order_id": "ORD-HIGH-VAL",
            "transaction_id": "8MC585209K746392H",
            "tracking_number": "1Z9999999999999999",
            "carrier": "UPS",
            "status": "DELIVERED",
            "shipped_date": "2026-10-25",
            "delivered_date": "2026-10-28",
            "amount": 950.00,
            "currency": "USD",
            "evidence_text": "Delivered to front door.",
        }
        result = analyze_shipment_evidence(order)
        self.assertTrue(result["seller_protection"]["signature_confirmation"]["required"])
        self.assertEqual(result["seller_protection"]["signature_confirmation"]["status"], "MISSING_REQUIRED")
        self.assertIn("signature confirmation", " ".join(result["risk_factors"]).lower())

    def test_high_value_order_with_signature_is_satisfied(self):
        order = {
            "order_id": "ORD-HIGH-VAL-SIG",
            "transaction_id": "8MC585209K746392H",
            "tracking_number": "1Z9999999999999999",
            "carrier": "UPS",
            "status": "DELIVERED",
            "shipped_date": "2026-10-25",
            "delivered_date": "2026-10-28",
            "amount": 1200.00,
            "currency": "USD",
            "evidence_text": "Delivered and signed by: Michael Vance.",
        }
        result = analyze_shipment_evidence(order)
        self.assertTrue(result["seller_protection"]["signature_confirmation"]["required"])
        self.assertEqual(result["seller_protection"]["signature_confirmation"]["status"], "SATISFIED")
        self.assertTrue(result["evidence_summary"]["signature_detected"])

    def test_engine_metadata_accurately_labeled(self):
        order = {"order_id": "ORD-1", "transaction_id": "TXN-1", "tracking_number": "1Z123"}
        result = analyze_shipment_evidence(order)
        self.assertIn("engine_metadata", result)
        self.assertEqual(result["engine_metadata"]["type"], "DETERMINISTIC_RULES_NLP")
        self.assertTrue(result["engine_metadata"]["auditable"])
        self.assertTrue(result["engine_metadata"]["zero_hallucination"])

    def test_carrier_format_mismatch_detected(self):
        # Tracking number is a UPS 1Z format, but carrier is marked as USPS
        order = {
            "order_id": "ORD-MISMATCH",
            "transaction_id": "8MC585209K746392H",
            "tracking_number": "1Z9999999999999999",
            "carrier": "USPS",
            "status": "SHIPPED",
            "shipped_date": "2026-10-25",
        }
        result = analyze_shipment_evidence(order)
        self.assertEqual(result["carrier_analysis"]["probable_detected_carrier"], "UPS")
        self.assertIn("Format mismatch", " ".join(result["risk_factors"]))

    def test_carrier_exception_keywords_detected(self):
        order = {
            "order_id": "ORD-EXCEPTION",
            "transaction_id": "8MC585209K746392H",
            "tracking_number": "781234567890",
            "carrier": "FEDEX",
            "status": "SHIPPED",
            "shipped_date": "2026-10-25",
            "evidence_text": "Delivery failed: damaged in transit, returned to sender.",
        }
        result = analyze_shipment_evidence(order)
        self.assertIn("damaged in transit", result["evidence_summary"]["exceptions_detected"])
        self.assertIn("returned to sender", result["evidence_summary"]["exceptions_detected"])
        self.assertLess(result["readiness_score"], 70)

    def test_paypal_payload_preview_format(self):
        order = {
            "order_id": "ORD-1001",
            "transaction_id": "8MC585209K746392H",
            "tracking_number": "781234567890",
            "carrier": "FEDEX",
            "status": "SHIPPED",
            "shipped_date": "2026-10-25",
        }
        result = analyze_shipment_evidence(order)
        preview = result["paypal_payload_preview"]
        self.assertEqual(
            preview["endpoint"],
            "POST /v2/checkout/orders/{paypal_order_id}/track",
        )
        self.assertEqual(
            preview["request_body"],
            {
                "capture_id": "8MC585209K746392H",
                "tracking_number": "781234567890",
                "carrier": "FEDEX",
                "notify_payer": False,
            },
        )
        self.assertEqual(
            preview["submission_safety_status"], "DISABLED_BY_DEFAULT"
        )
        self.assertIn("human-approved", preview["safety_gate_note"])

    def test_ord_1005_scenario_missing_signature_explicitly_flagged(self):
        order = {
            "order_id": "ORD-1005",
            "transaction_id": "SANDBOX-TXN-1005",
            "tracking_number": "781234567890",
            "carrier": "FEDEX",
            "status": "DELIVERED",
            "shipped_date": "2026-10-25",
            "delivered_date": "2026-10-28",
            "amount": 980.00,
            "currency": "USD",
            "shipping_address": "Boston, MA 02108",
            "evidence_text": "Delivered: Left at front doorstep without signature.",
        }
        result = analyze_shipment_evidence(order)
        self.assertEqual(result["seller_protection"]["signature_confirmation"]["status"], "MISSING_REQUIRED")
        self.assertFalse(result["seller_protection"]["item_not_received_eligible"])
        self.assertIn("without signature", " ".join(result["risk_factors"]).lower())

    def test_ord_1005_scenario_merchant_checkbox_alone_does_not_override_negative_carrier_scan(self):
        order = {
            "order_id": "ORD-1005",
            "transaction_id": "SANDBOX-TXN-1005",
            "tracking_number": "781234567890",
            "carrier": "FEDEX",
            "status": "DELIVERED",
            "shipped_date": "2026-10-25",
            "delivered_date": "2026-10-28",
            "amount": 980.00,
            "currency": "USD",
            "shipping_address": "Boston, MA 02108",
            "evidence_text": "Delivered: Left at front doorstep without signature.",
            "signature_obtained": True,  # Merchant claims signature, but carrier log contradicts it
        }
        result = analyze_shipment_evidence(order)
        # Must not be SATISFIED because carrier delivery record explicitly states left without signature
        self.assertEqual(result["seller_protection"]["signature_confirmation"]["status"], "MISSING_REQUIRED")
        self.assertFalse(result["seller_protection"]["item_not_received_eligible"])

    def test_ord_1005_scenario_remediated_with_carrier_signature_confirmation(self):
        order = {
            "order_id": "ORD-1005",
            "transaction_id": "SANDBOX-TXN-1005",
            "tracking_number": "781234567890",
            "carrier": "FEDEX",
            "status": "DELIVERED",
            "shipped_date": "2026-10-25",
            "delivered_date": "2026-10-28",
            "amount": 980.00,
            "currency": "USD",
            "shipping_address": "Boston, MA 02108",
            "evidence_text": "Delivered and signed by: C. Adams, Boston, MA 02108. FedEx Direct Signature confirmation on file.",
            "signature_obtained": True,
        }
        result = analyze_shipment_evidence(order)
        self.assertEqual(result["seller_protection"]["signature_confirmation"]["status"], "SATISFIED")
        self.assertEqual(result["seller_protection"]["signature_confirmation"]["verification_source"], "CARRIER_SCAN")
        self.assertTrue(result["seller_protection"]["item_not_received_eligible"])
        self.assertGreaterEqual(result["readiness_score"], 85)
        self.assertEqual(result["protection_tier"], "FULL_PROTECTION_READY")
        # Verify PayPal preview uses the exact updated shipment data
        preview_tracker = result["paypal_payload_preview"]["trackers"][0]
        self.assertEqual(preview_tracker["tracking_number"], "781234567890")
        self.assertEqual(preview_tracker["carrier"], "FEDEX")
        self.assertEqual(preview_tracker["status"], "DELIVERED")

    def test_missing_transaction_date_shows_policy_requires_review(self):
        """When transaction_date is absent, policy_applicability must be REQUIRES_REVIEW."""
        order = {
            "order_id": "ORD-1005",
            "transaction_id": "SANDBOX-TXN-1005",
            "tracking_number": "781234567890",
            "carrier": "FEDEX",
            "status": "DELIVERED",
            "shipped_date": "2026-10-25",
            "delivered_date": "2026-10-28",
            "amount": 980.00,
            "currency": "USD",
            "shipping_address": "Boston, MA 02108",
            "evidence_text": "Delivered: Left at front doorstep without signature.",
            # transaction_date intentionally absent
        }
        result = analyze_shipment_evidence(order)
        sig = result["seller_protection"]["signature_confirmation"]
        self.assertEqual(sig["policy_applicability"], "REQUIRES_REVIEW")
        # A warning about missing transaction date should appear
        combined_risks = " ".join(result["risk_factors"]).lower()
        self.assertIn("transaction processing date", combined_risks)

    def test_transaction_date_after_policy_effective_date_is_confirmed(self):
        """When transaction_date is on or after 2023-08-02, policy_applicability is CONFIRMED."""
        order = {
            "order_id": "ORD-POLICY-CONFIRMED",
            "transaction_id": "8MC585209K746392H",
            "tracking_number": "1Z9999999999999999",
            "carrier": "UPS",
            "status": "DELIVERED",
            "shipped_date": "2026-10-24",
            "delivered_date": "2026-10-27",
            "transaction_date": "2026-10-23",
            "amount": 1450.00,
            "currency": "USD",
            "shipping_address": "San Francisco, CA 94105",
            "evidence_text": "Delivered and signed by: M. Vance. Front desk reception, San Francisco, CA 94105.",
            "signature_obtained": True,
        }
        result = analyze_shipment_evidence(order)
        sig = result["seller_protection"]["signature_confirmation"]
        self.assertEqual(sig["policy_applicability"], "CONFIRMED")
        self.assertEqual(sig["status"], "SATISFIED")

    def test_merchant_attestation_alone_is_unverified_when_no_carrier_sig_scan(self):
        """signature_obtained=True with no carrier confirmation keyword yields MERCHANT_ATTESTED_UNVERIFIED."""
        order = {
            "order_id": "ORD-ATTEST",
            "transaction_id": "8MC585209K746392H",
            "tracking_number": "781234567890",
            "carrier": "FEDEX",
            "status": "DELIVERED",
            "shipped_date": "2026-10-25",
            "delivered_date": "2026-10-28",
            "transaction_date": "2026-10-24",
            "amount": 980.00,
            "currency": "USD",
            "shipping_address": "Boston, MA 02108",
            "evidence_text": "Package delivered.",
            "signature_obtained": True,
        }
        result = analyze_shipment_evidence(order)
        sig = result["seller_protection"]["signature_confirmation"]
        self.assertEqual(sig["status"], "MERCHANT_ATTESTED_UNVERIFIED")
        self.assertFalse(result["seller_protection"]["item_not_received_eligible"])

    def test_policy_effective_date_present_in_signature_confirmation(self):
        """policy_effective_date field is always returned in signature_confirmation."""
        order = {
            "order_id": "ORD-DATE-CHECK",
            "transaction_id": "TXN-X",
            "tracking_number": "781234567890",
            "carrier": "FEDEX",
            "status": "DELIVERED",
            "amount": 900.00,
        }
        result = analyze_shipment_evidence(order)
        sig = result["seller_protection"]["signature_confirmation"]
        self.assertIn("policy_effective_date", sig)
        self.assertEqual(sig["policy_effective_date"], "2023-08-02")


if __name__ == "__main__":
    unittest.main()
