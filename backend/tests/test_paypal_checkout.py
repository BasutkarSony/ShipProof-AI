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
from app.store import init_db, create_order, get_order
from app.main import create_checkout_order, capture_checkout_order


# Realistic PayPal Orders v2 capture response (capture nested inside purchase_units[].payments.captures[])
CAPTURE_SUCCESS = {
    "id": "PAYPAL-ORDER-123",
    "status": "COMPLETED",
    "purchase_units": [
        {
            "reference_id": "default",
            "amount": {"currency_code": "USD", "value": "44.73"},
            "payments": {
                "captures": [
                    {
                        "id": "CAPTURE-123",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "44.73"},
                    }
                ]
            },
        }
    ],
}

CAPTURE_MISSING_CAPTURES = {
    "id": "PAYPAL-ORDER-123",
    "status": "COMPLETED",
    "purchase_units": [
        {
            "reference_id": "default",
            "amount": {"currency_code": "USD", "value": "44.73"},
            "payments": {},
        }
    ],
}

CAPTURE_WRONG_AMOUNT = {
    "id": "PAYPAL-ORDER-123",
    "status": "COMPLETED",
    "purchase_units": [
        {
            "reference_id": "default",
            "amount": {"currency_code": "USD", "value": "44.73"},
            "payments": {
                "captures": [
                    {
                        "id": "CAPTURE-123",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "99.99"},
                    }
                ]
            },
        }
    ],
}

CAPTURE_WRONG_CURRENCY = {
    "id": "PAYPAL-ORDER-123",
    "status": "COMPLETED",
    "purchase_units": [
        {
            "reference_id": "default",
            "amount": {"currency_code": "USD", "value": "44.73"},
            "payments": {
                "captures": [
                    {
                        "id": "CAPTURE-123",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "EUR", "value": "44.73"},
                    }
                ]
            },
        }
    ],
}

CAPTURE_INCOMPLETE_STATUS = {
    "id": "PAYPAL-ORDER-123",
    "status": "APPROVED",
    "purchase_units": [
        {
            "reference_id": "default",
            "amount": {"currency_code": "USD", "value": "44.73"},
            "payments": {
                "captures": [
                    {
                        "id": "CAPTURE-123",
                        "status": "APPROVED",
                        "amount": {"currency_code": "USD", "value": "44.73"},
                    }
                ]
            },
        }
    ],
}

CAPTURE_MISMATCHED_ORDER_ID = {
    "id": "PAYPAL-ORDER-WRONG",
    "status": "COMPLETED",
    "purchase_units": [
        {
            "reference_id": "default",
            "amount": {"currency_code": "USD", "value": "44.73"},
            "payments": {
                "captures": [
                    {
                        "id": "CAPTURE-123",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "44.73"},
                    }
                ]
            },
        }
    ],
}

CAPTURE_EMPTY_CAPTURE_ID = {
    "id": "PAYPAL-ORDER-123",
    "status": "COMPLETED",
    "purchase_units": [
        {
            "reference_id": "default",
            "amount": {"currency_code": "USD", "value": "44.73"},
            "payments": {
                "captures": [
                    {
                        "id": "",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "44.73"},
                    }
                ]
            },
        }
    ],
}

CAPTURE_MISSING_ORDER_ID = {
    "status": "COMPLETED",
    "purchase_units": [
        {
            "reference_id": "default",
            "amount": {"currency_code": "USD", "value": "44.73"},
            "payments": {
                "captures": [
                    {
                        "id": "CAPTURE-123",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "44.73"},
                    }
                ]
            },
        }
    ],
}


class PayPalCheckoutTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._tmp_path = self._tmp.name
        store.DB_PATH = Path(self._tmp_path)
        init_db()

    def tearDown(self):
        store.DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shipproof.db"
        os.unlink(self._tmp_path)

    # ---------- checkout order creation ----------

    @patch("app.main.create_paypal_order")
    @patch("app.main.get_access_token")
    def test_create_checkout_order_returns_approval_url_and_paypal_id(
        self, mock_token, mock_create
    ):
        mock_token.return_value = "test-token"
        mock_create.return_value = {
            "id": "PAYPAL-ORDER-123",
            "status": "CREATED",
            "links": [
                {
                    "rel": "approve",
                    "href": "https://www.sandbox.paypal.com/checkoutnow?token=PAYPAL-ORDER-123",
                }
            ],
        }

        result = create_checkout_order(
            {
                "items": [
                    {"sku": "SHIP-STD-001", "quantity": 2},
                    {"sku": "SHIP-FRA-003", "quantity": 1},
                ],
                "currency": "USD",
            }
        )

        self.assertIsNotNone(result["order_id"])
        self.assertEqual(result["paypal_order_id"], "PAYPAL-ORDER-123")
        self.assertEqual(result["total"], "44.73")
        self.assertEqual(result["currency"], "USD")
        self.assertIsNotNone(result["approval_url"])
        self.assertEqual(result["status"], "CREATED")

        # Verify PayPal order ID persisted against local order.
        order = get_order(result["order_id"])
        self.assertEqual(order["paypal_order_id"], "PAYPAL-ORDER-123")
        self.assertEqual(order["payment_status"], "CREATED")

        # Verify PayPal was called with server-calculated total, not frontend price.
        call_args = mock_create.call_args
        self.assertEqual(call_args[0][1], 4473)  # amount_cents is 2nd positional arg

    @patch("app.main.create_paypal_order")
    @patch("app.main.get_access_token")
    def test_create_checkout_order_uses_server_calculated_total(
        self, mock_token, mock_create
    ):
        mock_token.return_value = "test-token"
        mock_create.return_value = {
            "id": "PAYPAL-ORDER-456",
            "status": "CREATED",
            "links": [{"rel": "approve", "href": "https://example.com/approve"}],
        }

        # Frontend might try to send a different price, but server calculates from catalogue.
        result = create_checkout_order(
            {
                "items": [{"sku": "SHIP-HEV-002", "quantity": 3}],
                "currency": "USD",
            }
        )

        self.assertEqual(result["total"], "73.50")
        call_args = mock_create.call_args
        self.assertEqual(call_args[0][1], 7350)  # amount_cents is 2nd positional arg

    @patch("app.main.create_paypal_order")
    @patch("app.main.get_access_token")
    def test_create_checkout_order_payer_action_link(self, mock_token, mock_create):
        mock_token.return_value = "test-token"
        mock_create.return_value = {
            "id": "PAYPAL-ORDER-PAYER",
            "status": "CREATED",
            "links": [
                {"rel": "payer-action", "href": "https://example.com/payer-action"}
            ],
        }

        result = create_checkout_order(
            {
                "items": [{"sku": "SHIP-STD-001", "quantity": 1}],
                "currency": "USD",
            }
        )

        self.assertIsNotNone(result["approval_url"])
        self.assertEqual(result["approval_url"], "https://example.com/payer-action")

    @patch("app.paypal_client.requests.post")
    @patch("app.main.get_access_token")
    def test_create_checkout_order_includes_return_and_cancel_urls(
        self, mock_token, mock_post
    ):
        mock_token.return_value = "test-token"
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "id": "PAYPAL-ORDER-URLS",
            "status": "CREATED",
            "links": [{"rel": "approve", "href": "https://example.com/approve"}],
        }
        mock_post.return_value = mock_response

        create_checkout_order(
            {
                "items": [{"sku": "SHIP-STD-001", "quantity": 1}],
                "currency": "USD",
            }
        )

        call_args = mock_post.call_args
        request_body = call_args[1]["json"]

        # application_context must be absent (deprecated).
        self.assertNotIn("application_context", request_body)

        context = request_body["payment_source"]["paypal"]["experience_context"]
        self.assertEqual(
            context["return_url"], "http://localhost:5173/checkout/return"
        )
        self.assertEqual(
            context["cancel_url"], "http://localhost:5173/checkout/cancel"
        )
        self.assertEqual(context["brand_name"], "ShipProof AI")
        self.assertEqual(context["locale"], "en-US")
        self.assertEqual(context["landing_page"], "LOGIN")
        self.assertEqual(context["shipping_preference"], "NO_SHIPPING")

    @patch("app.main.create_paypal_order")
    @patch("app.main.get_access_token")
    def test_create_checkout_order_no_approval_link_raises(self, mock_token, mock_create):
        mock_token.return_value = "test-token"
        mock_create.return_value = {
            "id": "PAYPAL-ORDER-NOLINK",
            "status": "CREATED",
            "links": [{"rel": "self", "href": "https://example.com/self"}],
        }

        with self.assertRaises(HTTPException) as ctx:
            create_checkout_order(
                {
                    "items": [{"sku": "SHIP-STD-001", "quantity": 1}],
                    "currency": "USD",
                }
            )

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("approval link", str(ctx.exception.detail))

    # ---------- payment capture ----------

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_capture_successful_payment_marks_order_paid(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_SUCCESS

        # Setup: create order with mocked PayPal create.
        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token2:
            mock_token2.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-123",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            create_result = create_checkout_order(
                {
                    "items": [
                        {"sku": "SHIP-STD-001", "quantity": 2},
                        {"sku": "SHIP-FRA-003", "quantity": 1},
                    ],
                    "currency": "USD",
                }
            )

        result = capture_checkout_order(create_result["order_id"], {})

        self.assertEqual(result["payment_status"], "PAID")
        self.assertEqual(result["paypal_capture_id"], "CAPTURE-123")
        self.assertEqual(result["already_captured"], False)

        # Verify actual nested capture ID persisted against local order (not order ID).
        order = get_order(create_result["order_id"])
        self.assertEqual(order["payment_status"], "PAID")
        self.assertEqual(order["paypal_capture_id"], "CAPTURE-123")
        self.assertNotEqual(order["paypal_capture_id"], order["paypal_order_id"])

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_capture_missing_capture_details_rejected_and_marked_failed(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_MISSING_CAPTURES

        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token2:
            mock_token2.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-123",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            create_result = create_checkout_order(
                {
                    "items": [
                        {"sku": "SHIP-STD-001", "quantity": 2},
                        {"sku": "SHIP-FRA-003", "quantity": 1},
                    ],
                    "currency": "USD",
                }
            )

        with self.assertRaises(HTTPException) as ctx:
            capture_checkout_order(create_result["order_id"], {})

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("capture ID is missing or invalid", str(ctx.exception.detail))

        # Order marked as FAILED.
        order = get_order(create_result["order_id"])
        self.assertEqual(order["payment_status"], "FAILED")

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_capture_mismatched_order_id_rejected_and_marked_failed(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_MISMATCHED_ORDER_ID

        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token2:
            mock_token2.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-123",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            create_result = create_checkout_order(
                {
                    "items": [
                        {"sku": "SHIP-STD-001", "quantity": 2},
                        {"sku": "SHIP-FRA-003", "quantity": 1},
                    ],
                    "currency": "USD",
                }
            )

        with self.assertRaises(HTTPException) as ctx:
            capture_checkout_order(create_result["order_id"], {})

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("mismatch or missing", str(ctx.exception.detail))

        # Order marked as FAILED.
        order = get_order(create_result["order_id"])
        self.assertEqual(order["payment_status"], "FAILED")

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_capture_missing_order_id_rejected_and_marked_failed(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_MISSING_ORDER_ID

        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token2:
            mock_token2.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-123",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            create_result = create_checkout_order(
                {
                    "items": [
                        {"sku": "SHIP-STD-001", "quantity": 2},
                        {"sku": "SHIP-FRA-003", "quantity": 1},
                    ],
                    "currency": "USD",
                }
            )

        with self.assertRaises(HTTPException) as ctx:
            capture_checkout_order(create_result["order_id"], {})

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("mismatch or missing", str(ctx.exception.detail))

        order = get_order(create_result["order_id"])
        self.assertEqual(order["payment_status"], "FAILED")

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_capture_empty_capture_id_rejected_and_marked_failed(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_EMPTY_CAPTURE_ID

        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token2:
            mock_token2.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-123",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            create_result = create_checkout_order(
                {
                    "items": [
                        {"sku": "SHIP-STD-001", "quantity": 2},
                        {"sku": "SHIP-FRA-003", "quantity": 1},
                    ],
                    "currency": "USD",
                }
            )

        with self.assertRaises(HTTPException) as ctx:
            capture_checkout_order(create_result["order_id"], {})

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("capture ID is missing or invalid", str(ctx.exception.detail))

        order = get_order(create_result["order_id"])
        self.assertEqual(order["payment_status"], "FAILED")

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_capture_invalid_capture_id_type_rejected_and_marked_failed(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.return_value = {
            "id": "PAYPAL-ORDER-123",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "reference_id": "default",
                    "amount": {"currency_code": "USD", "value": "44.73"},
                    "payments": {
                        "captures": [
                            {
                                "id": 12345,
                                "status": "COMPLETED",
                                "amount": {
                                    "currency_code": "USD",
                                    "value": "44.73",
                                },
                            }
                        ]
                    },
                }
            ],
        }

        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token2:
            mock_token2.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-123",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            create_result = create_checkout_order(
                {
                    "items": [
                        {"sku": "SHIP-STD-001", "quantity": 2},
                        {"sku": "SHIP-FRA-003", "quantity": 1},
                    ],
                    "currency": "USD",
                }
            )

        with self.assertRaises(HTTPException) as ctx:
            capture_checkout_order(create_result["order_id"], {})

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("capture ID is missing or invalid", str(ctx.exception.detail))

        order = get_order(create_result["order_id"])
        self.assertEqual(order["payment_status"], "FAILED")

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_capture_wrong_amount_rejected_and_marked_failed(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_WRONG_AMOUNT

        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token2:
            mock_token2.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-123",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            create_result = create_checkout_order(
                {
                    "items": [
                        {"sku": "SHIP-STD-001", "quantity": 2},
                        {"sku": "SHIP-FRA-003", "quantity": 1},
                    ],
                    "currency": "USD",
                }
            )

        with self.assertRaises(HTTPException) as ctx:
            capture_checkout_order(create_result["order_id"], {})

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("Captured amount does not match order total", str(ctx.exception.detail))

        # Order marked as FAILED.
        order = get_order(create_result["order_id"])
        self.assertEqual(order["payment_status"], "FAILED")

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_capture_wrong_currency_rejected_and_marked_failed(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_WRONG_CURRENCY

        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token2:
            mock_token2.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-123",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            create_result = create_checkout_order(
                {
                    "items": [
                        {"sku": "SHIP-STD-001", "quantity": 2},
                        {"sku": "SHIP-FRA-003", "quantity": 1},
                    ],
                    "currency": "USD",
                }
            )

        with self.assertRaises(HTTPException) as ctx:
            capture_checkout_order(create_result["order_id"], {})

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("currency is not USD", str(ctx.exception.detail))

        order = get_order(create_result["order_id"])
        self.assertEqual(order["payment_status"], "FAILED")

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_capture_incomplete_status_rejected_and_marked_failed(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_INCOMPLETE_STATUS

        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token2:
            mock_token2.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-123",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            create_result = create_checkout_order(
                {
                    "items": [
                        {"sku": "SHIP-STD-001", "quantity": 2},
                        {"sku": "SHIP-FRA-003", "quantity": 1},
                    ],
                    "currency": "USD",
                }
            )

        with self.assertRaises(HTTPException) as ctx:
            capture_checkout_order(create_result["order_id"], {})

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("PayPal capture did not complete", str(ctx.exception.detail))

        order = get_order(create_result["order_id"])
        self.assertEqual(order["payment_status"], "FAILED")

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_capture_paypal_api_error_handled_and_marked_failed(
        self, mock_token, mock_capture
    ):
        mock_token.return_value = "test-token"
        mock_capture.side_effect = RuntimeError(
            '{"http_status": 500, "paypal_response": {"message": "Internal Error"}}'
        )

        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token2:
            mock_token2.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-123",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            create_result = create_checkout_order(
                {
                    "items": [{"sku": "SHIP-STD-001", "quantity": 1}],
                    "currency": "USD",
                }
            )

        with self.assertRaises(HTTPException) as ctx:
            capture_checkout_order(create_result["order_id"], {})

        self.assertEqual(ctx.exception.status_code, 502)

        order = get_order(create_result["order_id"])
        self.assertEqual(order["payment_status"], "FAILED")

    @patch("app.main.capture_paypal_order")
    @patch("app.main.get_access_token")
    def test_repeated_capture_is_idempotent(self, mock_token, mock_capture):
        mock_token.return_value = "test-token"
        mock_capture.return_value = CAPTURE_SUCCESS

        with patch("app.main.create_paypal_order") as mock_create, patch(
            "app.main.get_access_token"
        ) as mock_token2:
            mock_token2.return_value = "test-token"
            mock_create.return_value = {
                "id": "PAYPAL-ORDER-123",
                "status": "CREATED",
                "links": [{"rel": "approve", "href": "https://example.com/approve"}],
            }
            create_result = create_checkout_order(
                {
                    "items": [
                        {"sku": "SHIP-STD-001", "quantity": 2},
                        {"sku": "SHIP-FRA-003", "quantity": 1},
                    ],
                    "currency": "USD",
                }
            )

        # First capture succeeds.
        result1 = capture_checkout_order(create_result["order_id"], {})
        self.assertEqual(result1["already_captured"], False)
        self.assertEqual(result1["payment_status"], "PAID")

        # Second capture returns idempotent response, PayPal capture not called again.
        result2 = capture_checkout_order(create_result["order_id"], {})
        self.assertEqual(result2["already_captured"], True)
        self.assertEqual(result2["payment_status"], "PAID")

        # capture_paypal_order was called only once.
        self.assertEqual(mock_capture.call_count, 1)

    # ---------- validation (delegated to store) ----------

    def test_create_checkout_order_empty_items_rejected(self):
        with self.assertRaises(ValueError):
            create_order([], "USD")

    def test_create_checkout_order_non_usd_rejected(self):
        with self.assertRaises(ValueError):
            create_order(
                [{"sku": "SHIP-STD-001", "quantity": 1}], currency="EUR"
            )

    def test_create_checkout_order_unknown_sku_rejected(self):
        with self.assertRaises(ValueError):
            create_order([{"sku": "NONEXISTENT", "quantity": 1}], "USD")

    def test_get_unknown_order_returns_404(self):
        with self.assertRaises(HTTPException) as ctx:
            capture_checkout_order("00000000-0000-0000-0000-000000000000", {})
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
