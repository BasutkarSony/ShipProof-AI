import os
from decimal import Decimal
import requests
from dotenv import load_dotenv

load_dotenv()

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"

TWO_PLACES = Decimal("0.01")


def _money(amount_cents: int) -> str:
    return str((Decimal(amount_cents) / 100).quantize(TWO_PLACES))


class PayPalConfigurationError(RuntimeError):
    pass


def configured() -> bool:
    return bool(
        os.getenv("PAYPAL_CLIENT_ID", "").strip()
        and os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    )


def submissions_enabled() -> bool:
    """Require an explicit local opt-in before any external tracking write."""
    return os.getenv("PAYPAL_TRACKING_SUBMISSION_ENABLED", "").strip().lower() == "true"


def get_access_token() -> str:
    client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise PayPalConfigurationError(
            "PayPal Sandbox credentials are not configured. Add them to backend/.env."
        )

    response = requests.post(
        f"{SANDBOX_BASE}/v1/oauth2/token",
        auth=(client_id, client_secret),
        headers={"Accept": "application/json", "Accept-Language": "en_US"},
        data={"grant_type": "client_credentials"},
        timeout=20,
    )
    if not response.ok:
        # Do not return or log credentials or access tokens.
        raise RuntimeError(
            f"PayPal OAuth failed with HTTP {response.status_code}. "
            "Check that the Sandbox REST app Client ID and Secret are correct."
        )
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("PayPal OAuth response did not contain an access token.")
    return token


def submit_tracking(order: dict) -> dict:
    if not submissions_enabled():
        raise PayPalConfigurationError(
            "PayPal tracking submission is disabled. Set "
            "PAYPAL_TRACKING_SUBMISSION_ENABLED=true only after approving a Sandbox write."
        )

    token = get_access_token()
    tracker = {
        "transaction_id": str(order.get("transaction_id", "")).strip(),
        "tracking_number": str(order.get("tracking_number", "")).strip(),
        "status": str(order.get("status", "SHIPPED")).strip().upper(),
        "carrier": str(order.get("carrier", "")).strip().upper(),
    }
    if order.get("shipped_date"):
        tracker["shipment_date"] = str(order["shipped_date"]).strip()
    if tracker["carrier"] == "OTHER":
        carrier_name = str(order.get("carrier_name_other", "")).strip()
        if not carrier_name:
            raise ValueError(
                "When carrier is OTHER, provide carrier_name_other (the carrier's name)."
            )
        tracker["carrier_name_other"] = carrier_name

    try:
        response = requests.post(
            f"{SANDBOX_BASE}/v1/shipping/trackers-batch",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"trackers": [tracker]},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError("Could not reach PayPal Sandbox to submit tracking.") from exc
    try:
        body = response.json()
    except ValueError:
        body = {"message": "PayPal returned a non-JSON response."}

    if not response.ok:
        # Surface PayPal's response details, but never credentials/tokens.
        raise RuntimeError({
            "http_status": response.status_code,
            "paypal_response": body,
        }.__str__())
    return body


def create_paypal_order(
    token: str,
    amount_cents: int,
    currency: str = "USD",
    items: list[dict] | None = None,
    buyer_name: str = "",
    shipping_address: dict | None = None,
) -> dict:
    """Create an Orders v2 checkout with persisted line items and buyer delivery details."""
    from os import getenv

    if not items:
        raise ValueError("At least one persisted order item is required for PayPal checkout.")
    if not isinstance(shipping_address, dict):
        raise ValueError("A structured shipping address is required for physical goods.")

    paypal_items = []
    computed_item_total = 0
    for item in items:
        quantity = item.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("PayPal item quantity must be a positive integer.")
        unit_amount = Decimal(str(item.get("unit_price", "0"))).quantize(TWO_PLACES)
        if unit_amount <= 0:
            raise ValueError("PayPal item unit amount must be positive.")
        line_total = unit_amount * quantity
        computed_item_total += int(line_total * 100)
        paypal_item = {
            "name": str(item.get("name", "")).strip()[:127],
            "quantity": str(quantity),
            "unit_amount": {
                "currency_code": currency,
                "value": str(unit_amount),
            },
            "category": "PHYSICAL_GOODS",
        }
        if item.get("sku"):
            paypal_item["sku"] = str(item["sku"])[:50]
        paypal_items.append(paypal_item)

    if computed_item_total != amount_cents:
        raise ValueError("Persisted PayPal line items do not add up to the server-calculated order total.")

    address = {
        "address_line_1": str(shipping_address.get("address_line_1", "")).strip(),
        "admin_area_2": str(shipping_address.get("city", "")).strip(),
        "postal_code": str(shipping_address.get("postal_code", "")).strip(),
        "country_code": str(shipping_address.get("country_code", "")).strip().upper(),
    }
    if shipping_address.get("address_line_2"):
        address["address_line_2"] = str(shipping_address["address_line_2"]).strip()
    if shipping_address.get("state"):
        address["admin_area_1"] = str(shipping_address["state"]).strip()

    frontend_url = getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    return_url = getenv("PAYPAL_RETURN_URL", f"{frontend_url}/checkout/return")
    cancel_url = getenv("PAYPAL_CANCEL_URL", f"{frontend_url}/checkout/cancel")

    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {
                "currency_code": currency,
                "value": _money(amount_cents),
                "breakdown": {
                    "item_total": {
                        "currency_code": currency,
                        "value": _money(computed_item_total),
                    }
                },
            },
            "items": paypal_items,
            "shipping": {
                "name": {"full_name": str(buyer_name).strip()},
                "address": address,
            },
        }],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "brand_name": "ShipProof AI",
                    "locale": "en-US",
                    "landing_page": "LOGIN",
                    "shipping_preference": "SET_PROVIDED_ADDRESS",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                }
            }
        },
    }

    response = requests.post(
        f"{SANDBOX_BASE}/v2/checkout/orders",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        json=body,
        timeout=30,
    )
    try:
        response_body = response.json()
    except ValueError:
        response_body = {"message": "PayPal returned a non-JSON response."}

    if not response.ok:
        raise RuntimeError({
            "http_status": response.status_code,
            "paypal_response": response_body,
        }.__str__())
    return response_body


def capture_paypal_order(token: str, order_id: str, request_id: str | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if request_id:
        headers["PayPal-Request-Id"] = request_id

    response = requests.post(
        f"{SANDBOX_BASE}/v2/checkout/orders/{order_id}/capture",
        headers=headers,
        timeout=30,
    )
    try:
        response_body = response.json()
    except ValueError:
        response_body = {"message": "PayPal returned a non-JSON response."}

    if not response.ok:
        raise RuntimeError({
            "http_status": response.status_code,
            "paypal_response": response_body,
        }.__str__())
    return response_body
