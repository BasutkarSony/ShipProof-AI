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


def create_paypal_order(token: str, amount_cents: int, currency: str = "USD") -> dict:
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {
                "currency_code": currency,
                "value": _money(amount_cents),
            },
        }],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "brand_name": "ShipProof AI",
                    "locale": "en-US",
                    "landing_page": "LOGIN",
                    "shipping_preference": "NO_SHIPPING",
                    "return_url": "http://localhost:5173/checkout/return",
                    "cancel_url": "http://localhost:5173/checkout/cancel",
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
