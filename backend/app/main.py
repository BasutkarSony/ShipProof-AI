from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from app.validator import validate_order
from app.ai_analyzer import analyze_shipment_evidence
from app.paypal_client import (
    configured as paypal_configured,
    submissions_enabled as paypal_submissions_enabled,
    get_access_token,
    submit_tracking,
    create_paypal_order,
    capture_paypal_order,
    PayPalConfigurationError,
)
from app.store import (
    init_db,
    get_catalogue,
    create_order,
    get_order,
    list_orders as store_list_orders,
    set_paypal_order_id,
    set_capture,
    create_manifest,
    create_manifest_from_checkout_order,
    get_manifest,
    get_manifest_for_shipment,
    update_manifest,
    finalize_manifest,
    create_inspection,
    get_inspection,
    list_inspections_for_manifest,
    record_inspection_review,
    create_shipment_for_order,
    get_shipment_by_order_id,
    get_shipment_by_checkout_order_id,
    list_shipments,
    update_shipment,
)
import json
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

app = FastAPI(
    title="ShipProof AI API",
    description="Pre-submission shipment evidence validation and PayPal Sandbox tracking",
    version="0.2.0",
)


@app.on_event("startup")
def on_startup():
    init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = Path(__file__).parent.parent / "data" / "sample_orders.json"


@app.get("/")
def root():
    return {"app": "ShipProof AI", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/orders")
def list_orders():
    # Load sample shipment orders
    with DATA_FILE.open("r", encoding="utf-8-sig") as file:
        sample_orders = json.load(file)

    # Load persistent shipments created from PayPal checkout payments
    persistent_shipments = list_shipments()

    # Combine persistent shipments with sample orders (persistent shipments first)
    combined = list(persistent_shipments) + sample_orders
    return {"orders": combined}


@app.get("/api/catalog")
def catalog():
    return {"products": get_catalogue()}


@app.get("/api/checkout/orders")
def checkout_orders():
    return {"orders": store_list_orders()}


def _normalize_checkout_details(payload: dict) -> tuple[str, dict]:
    buyer_name = str(payload.get("buyer_name", "")).strip()
    if not buyer_name or len(buyer_name) > 100:
        raise HTTPException(
            status_code=422,
            detail="Enter the recipient's full name (up to 100 characters).",
        )

    raw_address = payload.get("shipping_address")
    if not isinstance(raw_address, dict):
        raise HTTPException(status_code=422, detail="Enter a delivery address.")

    address = {
        "address_line_1": str(raw_address.get("address_line_1", "")).strip(),
        "address_line_2": str(raw_address.get("address_line_2", "")).strip(),
        "city": str(raw_address.get("city", "")).strip(),
        "state": str(raw_address.get("state", "")).strip(),
        "postal_code": str(raw_address.get("postal_code", "")).strip(),
        "country_code": str(raw_address.get("country_code", "")).strip().upper(),
    }
    required_fields = {
        "street address": address["address_line_1"],
        "city": address["city"],
        "postal code": address["postal_code"],
    }
    missing = [name for name, value in required_fields.items() if not value]
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Complete the delivery address: " + ", ".join(missing) + ".",
        )
    if len(address["country_code"]) != 2 or not address["country_code"].isalpha():
        raise HTTPException(
            status_code=422,
            detail="Enter the two-letter country code, such as IN or US.",
        )

    # PayPal requires admin_area_1 for these countries when a shipping
    # address is supplied in an Orders v2 request.
    region_required_countries = {
        "AR", "BR", "CA", "CN", "ID", "IN", "JP", "MX", "TH", "US"
    }
    if (
        address["country_code"] in region_required_countries
        and not address["state"]
    ):
        raise HTTPException(
            status_code=422,
            detail="Enter the state or region for the selected country.",
        )

    if any(len(value) > 120 for value in address.values()):
        raise HTTPException(status_code=422, detail="Delivery address fields are too long.")

    return buyer_name, address


@app.post("/api/checkout/orders")
def create_checkout_order(payload: dict):
    items = payload.get("items", [])
    currency = str(payload.get("currency", "USD")).strip().upper()
    buyer_name, shipping_address = _normalize_checkout_details(payload)

    # Authenticate before writing a local order so missing credentials do not
    # leave an incomplete checkout record behind.
    try:
        token = get_access_token()
    except PayPalConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        order = create_order(
            items,
            currency,
            buyer_name=buyer_name,
            shipping_address=shipping_address,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    total_cents = int(Decimal(order["total"]) * 100)
    try:
        paypal_result = create_paypal_order(
            token,
            total_cents,
            currency,
            items=order["items"],
            buyer_name=buyer_name,
            shipping_address=shipping_address,
        )
    except (RuntimeError, ValueError) as exc:
        set_capture(order["id"], "", "FAILED")
        raise HTTPException(status_code=502, detail=f"PayPal could not create checkout: {exc}")

    paypal_order_id = paypal_result.get("id")
    if not paypal_order_id:
        set_capture(order["id"], "", "FAILED")
        raise HTTPException(status_code=502, detail="PayPal did not return an order ID.")

    set_paypal_order_id(order["id"], paypal_order_id)

    approval_url = None
    for link in paypal_result.get("links", []):
        if link.get("rel") in ("approve", "payer-action"):
            approval_url = link.get("href")
            break

    if not approval_url:
        set_capture(order["id"], "", "FAILED")
        raise HTTPException(status_code=502, detail="PayPal did not return an approval link.")

    return {
        "order_id": order["id"],
        "paypal_order_id": paypal_order_id,
        "approval_url": approval_url,
        "total": order["total"],
        "currency": currency,
        "status": order["payment_status"],
    }


@app.post("/api/checkout/orders/{order_id}/capture")
def capture_checkout_order(order_id: str, payload: dict):
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    # Idempotency: already captured orders return without calling PayPal again.
    if order.get("payment_status") in ("PAID", "CAPTURED"):
        # Ensure shipment exists for this paid order (retry recovery if payment succeeded but shipment failed)
        existing_shipment = get_shipment_by_checkout_order_id(order_id)
        if not existing_shipment and order.get("paypal_capture_id"):
            existing_shipment = create_shipment_for_order(
                checkout_order_id=order["id"],
                paypal_order_id=order.get("paypal_order_id") or "",
                paypal_capture_id=order.get("paypal_capture_id"),
                amount=order.get("total", "0.00"),
                currency=order.get("currency", "USD"),
                shipping_address=order.get("shipping_address") or {},
                buyer_name=order.get("buyer_name", ""),
            )

        existing_manifest = (
            create_manifest_from_checkout_order(existing_shipment["order_id"], order["id"])
            if existing_shipment
            else None
        )
        return {
            "order_id": order["id"],
            "paypal_order_id": order.get("paypal_order_id"),
            "paypal_capture_id": order.get("paypal_capture_id"),
            "shipment_id": existing_shipment.get("id") if existing_shipment else None,
            "shipment_order_id": existing_shipment.get("order_id") if existing_shipment else None,
            "manifest_id": existing_manifest.get("id") if existing_manifest else None,
            "buyer_name": order.get("buyer_name", ""),
            "shipping_address": order.get("shipping_address") or {},
            "items": order.get("items", []),
            "total": order.get("total", "0.00"),
            "currency": order.get("currency", "USD"),
            "payment_status": order.get("payment_status"),
            "already_captured": True,
        }

    paypal_order_id = order.get("paypal_order_id")
    if not paypal_order_id:
        raise HTTPException(
            status_code=400, detail="Order has no associated PayPal order."
        )

    token = get_access_token()
    request_id = f"capture-{order_id}"

    try:
        capture_result = capture_paypal_order(token, paypal_order_id, request_id)
    except RuntimeError as exc:
        # Failed payment: mark local order as failed.
        set_capture(order_id, "", "FAILED")
        raise HTTPException(status_code=502, detail=str(exc))

    capture_status = None
    capture_id = None
    captured_amount = None
    captured_currency = None

    # Verify the PayPal order ID in the capture response matches the local order.
    paypal_response_order_id = capture_result.get("id")
    if not paypal_response_order_id or paypal_response_order_id != paypal_order_id:
        set_capture(order_id, "", "FAILED")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "PayPal order ID mismatch or missing in capture response.",
            },
        )

    # Verify top-level PayPal order status is COMPLETED
    paypal_order_status = capture_result.get("status")
    if paypal_order_status != "COMPLETED":
        set_capture(order_id, "", "FAILED")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "PayPal order status is not COMPLETED.",
                "order_status": paypal_order_status,
            },
        )

    purchase_units = capture_result.get("purchase_units", [])
    for pu in purchase_units:
        payments = pu.get("payments", {})
        captures = payments.get("captures", [])
        if captures:
            capture = captures[0]
            capture_id = capture.get("id")
            capture_status = capture.get("status")
            capture_amount = capture.get("amount", {})
            captured_amount = capture_amount.get("value")
            captured_currency = capture_amount.get("currency_code")
            break

    # Require a non-empty string capture ID before persisting.
    if not isinstance(capture_id, str) or not capture_id.strip():
        set_capture(order_id, "", "FAILED")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "PayPal capture ID is missing or invalid.",
            },
        )

    # Never mark PAID if capture details are missing or malformed.
    if capture_status != "COMPLETED":
        set_capture(order_id, capture_id, "FAILED")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "PayPal capture did not complete.",
                "capture_status": capture_status,
            },
        )

    if captured_currency != order.get("currency", "USD"):
        set_capture(order_id, capture_id, "FAILED")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "PayPal capture currency does not match the checkout order currency.",
                "captured_currency": captured_currency,
            },
        )

    if captured_amount is None:
        set_capture(order_id, capture_id, "FAILED")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "PayPal capture is missing an amount.",
            },
        )

    try:
        captured_decimal = Decimal(str(captured_amount))
    except Exception:
        set_capture(order_id, capture_id, "FAILED")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "PayPal capture amount is malformed.",
            },
        )

    if captured_decimal != Decimal(order["total"]):
        set_capture(order_id, capture_id, "FAILED")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Captured amount does not match order total.",
                "expected": order["total"],
                "captured": captured_amount,
            },
        )

    # Persist the actual nested capture ID, not the top-level order ID.
    set_capture(order_id, capture_id, "PAID")

    # Only create a shipment after PayPal capture is verified.
    # Persist the local checkout order ID and PayPal capture ID against the shipment.
    shipment = create_shipment_for_order(
        checkout_order_id=order["id"],
        paypal_order_id=paypal_order_id,
        paypal_capture_id=capture_id,
        amount=order["total"],
        currency=order.get("currency", "USD"),
        shipping_address=order.get("shipping_address") or {},
        buyer_name=order.get("buyer_name", ""),
    )
    manifest = create_manifest_from_checkout_order(shipment["order_id"], order["id"])

    return {
        "order_id": order["id"],
        "paypal_order_id": paypal_order_id,
        "paypal_capture_id": capture_id,
        "shipment_id": shipment["id"],
        "shipment_order_id": shipment["order_id"],
        "manifest_id": manifest["id"],
        "buyer_name": order.get("buyer_name", ""),
        "shipping_address": order.get("shipping_address") or {},
        "items": order.get("items", []),
        "total": order.get("total", "0.00"),
        "currency": order.get("currency", "USD"),
        "payment_status": "PAID",
        "already_captured": False,
    }


@app.post("/api/validate")
def validate(payload: dict):
    return validate_order(payload)


@app.post("/api/analyze-evidence")
def analyze_evidence(payload: dict):
    return analyze_shipment_evidence(payload)


@app.get("/api/paypal/status")
def paypal_status():
    return {
        "provider": "PayPal Sandbox",
        "configured": paypal_configured(),
        "submission_enabled": paypal_submissions_enabled(),
        "base_url": "https://api-m.sandbox.paypal.com",
        "note": "Sandbox only. Credentials can be verified via OAuth. Tracking writes require an explicit local opt-in.",
    }


@app.post("/api/paypal/verify-connection")
def paypal_verify_connection():
    try:
        get_access_token()
        return {
            "success": True,
            "status": "AUTHENTICATED",
            "message": "Successfully authenticated with PayPal Sandbox OAuth 2.0 (client_credentials).",
            "provider": "PayPal Sandbox",
            "submission_enabled": paypal_submissions_enabled(),
            "safety_gate": "Tracking write gate is safely locked (PAYPAL_TRACKING_SUBMISSION_ENABLED=false). No tracking data was sent.",
        }
    except PayPalConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PayPal Sandbox OAuth failed: {str(exc)}")


@app.post("/api/inspections/{inspection_id}/review")
def review_packing_inspection(inspection_id: str, payload: dict):
    """Record an explicit human decision; Gemini output is never approval."""
    inspection = get_inspection(inspection_id)
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    manifest = get_manifest(inspection["manifest_id"])
    if manifest is None:
        raise HTTPException(status_code=404, detail="Inspection manifest not found.")
    inspections = list_inspections_for_manifest(manifest["id"])
    if not inspections or inspections[0]["id"] != inspection_id:
        raise HTTPException(
            status_code=409,
            detail="Only the latest packing inspection can receive a human review decision.",
        )
    if manifest["status"] != "FINALIZED":
        raise HTTPException(
            status_code=409,
            detail="The manifest is not finalized; this inspection cannot be reviewed.",
        )

    try:
        reviewed = record_inspection_review(
            inspection_id=inspection_id,
            decision=payload.get("decision", ""),
            reviewer_label=payload.get("reviewer_label", ""),
            notes=payload.get("notes", ""),
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if message.startswith("Inspection not found:") else 409 if "already been reviewed" in message else 422
        raise HTTPException(status_code=status_code, detail=message)

    return {
        "inspection_id": reviewed["id"],
        "manifest_id": reviewed["manifest_id"],
        "inspection_status": reviewed["inspection_status"],
        "review_history": reviewed["review_history"],
        "reviewed_at": reviewed["updated_at"],
    }


@app.post("/api/shipments/{shipment_order_id}/submit-tracking")
def submit_shipment_tracking(shipment_order_id: str, payload: dict):
    """Submit a stored paid shipment's carrier tracking after human inspection approval."""
    shipment = get_shipment_by_order_id(shipment_order_id)
    if shipment is None:
        raise HTTPException(
            status_code=404,
            detail="Persistent PayPal-paid shipment not found. Sample shipments cannot be submitted.",
        )

    if not paypal_submissions_enabled():
        raise HTTPException(
            status_code=503,
            detail="PayPal tracking submission is disabled. The Sandbox write gate is still locked.",
        )

    # Confirm the payment linkage using the local paid order, not client-supplied IDs.
    checkout_order = get_order(shipment["checkout_order_id"])
    if not checkout_order or checkout_order.get("payment_status") != "PAID":
        raise HTTPException(status_code=409, detail="A verified paid checkout is required.")
    if (
        checkout_order.get("paypal_order_id") != shipment.get("paypal_order_id")
        or checkout_order.get("paypal_capture_id") != shipment.get("paypal_capture_id")
    ):
        raise HTTPException(status_code=409, detail="Stored PayPal order/capture linkage does not match.")

    manifest = get_manifest_for_shipment(shipment_order_id)
    if not manifest or manifest.get("status") != "FINALIZED":
        raise HTTPException(status_code=409, detail="Finalize the shipment manifest before dispatch.")

    inspections = list_inspections_for_manifest(manifest["id"])
    if not inspections or inspections[0].get("inspection_status") != "APPROVED":
        raise HTTPException(
            status_code=409,
            detail="The latest packing inspection must be approved by a human reviewer before tracking can be submitted.",
        )

    tracking_number = str(payload.get("tracking_number", "")).strip()
    carrier = str(payload.get("carrier", "")).strip().upper()
    carrier_name_other = str(payload.get("carrier_name_other", "")).strip()
    notify_payer = payload.get("notify_payer", False)
    if not isinstance(notify_payer, bool):
        raise HTTPException(status_code=422, detail="notify_payer must be true or false.")

    if shipment.get("tracking_submission_status") == "SUBMITTED":
        same_tracking = (
            shipment.get("tracking_number") == tracking_number
            and shipment.get("carrier") == carrier
            and (carrier != "OTHER" or shipment.get("carrier_name_other") == carrier_name_other)
        )
        if same_tracking:
            return {
                "submitted": True,
                "already_submitted": True,
                "provider": "PayPal Sandbox",
                "shipment_order_id": shipment_order_id,
                "tracking_number": shipment["tracking_number"],
                "carrier": shipment["carrier"],
                "submitted_at": shipment.get("paypal_tracking_submitted_at"),
            }
        raise HTTPException(
            status_code=409,
            detail="Tracking has already been submitted for this shipment and cannot be replaced in this demo workflow.",
        )

    if shipment.get("tracking_submission_status") == "FAILED":
        previous_carrier_name = (
            str(shipment.get("carrier_name_other") or "").strip()
            if shipment.get("carrier") == "OTHER"
            else ""
        )
        requested_carrier_name = carrier_name_other if carrier == "OTHER" else ""
        if (
            shipment.get("tracking_number") != tracking_number
            or shipment.get("carrier") != carrier
            or previous_carrier_name != requested_carrier_name
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "The previous tracking request has an uncertain result. Retry with the same "
                    "tracking number and carrier before attempting a different tracking update."
                ),
            )

    validation_payload = {
        "order_id": shipment_order_id,
        "transaction_id": shipment["paypal_capture_id"],
        "tracking_number": tracking_number,
        "carrier": carrier,
        "carrier_name_other": carrier_name_other,
        "status": "SHIPPED",
    }
    validation = validate_order(validation_payload)
    if validation["result"] == "BLOCKED":
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Tracking details failed ShipProof's basic data checks. Nothing was sent to PayPal.",
                "validation": validation,
            },
        )

    try:
        response = submit_tracking({
            "paypal_order_id": shipment["paypal_order_id"],
            "paypal_capture_id": shipment["paypal_capture_id"],
            "tracking_number": tracking_number,
            "carrier": carrier,
            "carrier_name_other": carrier_name_other,
            "notify_payer": notify_payer,
            "items": checkout_order.get("items", []),
        })
    except PayPalConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        # Preserve the exact tracker details; the result may be uncertain if the request timed out.
        update_shipment(
            shipment_order_id,
            tracking_number=tracking_number,
            carrier=carrier,
            carrier_name_other=carrier_name_other or "UNASSIGNED",
            tracking_submission_status="FAILED",
        )
        raise HTTPException(status_code=502, detail=str(exc))

    if not isinstance(response, dict) or response.get("id") != shipment.get("paypal_order_id"):
        update_shipment(
            shipment_order_id,
            tracking_number=tracking_number,
            carrier=carrier,
            carrier_name_other=carrier_name_other or "UNASSIGNED",
            tracking_submission_status="FAILED",
        )
        raise HTTPException(
            status_code=502,
            detail="PayPal returned a successful response that did not match the stored order ID. Verify the order in Sandbox before retrying.",
        )

    submitted_at = datetime.now(timezone.utc).isoformat()
    update_shipment(
        shipment_order_id,
        tracking_number=tracking_number,
        carrier=carrier,
        carrier_name_other=carrier_name_other or "UNASSIGNED",
        status="SHIPPED",
        shipped_date=datetime.now(timezone.utc).date().isoformat(),
        tracking_submission_status="SUBMITTED",
        paypal_tracking_submitted_at=submitted_at,
    )
    return {
        "submitted": True,
        "already_submitted": False,
        "provider": "PayPal Sandbox",
        "shipment_order_id": shipment_order_id,
        "paypal_order_id": shipment["paypal_order_id"],
        "paypal_capture_id": shipment["paypal_capture_id"],
        "tracking_number": tracking_number,
        "carrier": carrier,
        "submitted_at": submitted_at,
        "validation": validation,
        "paypal_response": response,
    }


# ---------------------------------------------------------------------------
# Shipment manifest endpoints
# These operate on actual merchant shipment records, not on checkout orders.
# ---------------------------------------------------------------------------

def _load_shipment_orders() -> dict:
    """Return a dict keyed by order_id combining persistent DB shipments and sample orders."""
    orders = {}
    with DATA_FILE.open("r", encoding="utf-8-sig") as fh:
        sample_orders = json.load(fh)
    for o in sample_orders:
        orders[o["order_id"]] = o

    for s in list_shipments():
        orders[s["order_id"]] = s

    return orders


def _require_shipment_order(shipment_order_id: str) -> dict:
    """Return the shipment record or raise 404.

    Checks persistent SQLite shipment records and sample orders.
    """
    # Check persistent DB shipments first
    db_shipment = get_shipment_by_order_id(shipment_order_id)
    if db_shipment:
        return db_shipment

    orders = _load_shipment_orders()
    record = orders.get(shipment_order_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Shipment record '{shipment_order_id}' not found.",
        )
    return record


@app.post("/api/shipments/{shipment_order_id}/manifest", status_code=201)
def create_shipment_manifest(shipment_order_id: str, payload: dict):
    """Create a DRAFT manifest for an existing shipment evidence record."""
    _require_shipment_order(shipment_order_id)

    # Paid checkouts already have a manifest generated from the actual items
    # purchased. Return it on repeat requests instead of creating a duplicate.
    existing_manifest = get_manifest_for_shipment(shipment_order_id)
    if existing_manifest is not None:
        return existing_manifest

    items = payload.get("items")
    if not isinstance(items, list):
        raise HTTPException(status_code=422, detail="'items' must be a list.")

    notes = payload.get("notes")
    if notes is not None:
        notes = str(notes).strip() or None

    try:
        manifest = create_manifest(shipment_order_id, items, notes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return manifest


@app.get("/api/shipments/{shipment_order_id}/manifest")
def get_shipment_manifest(shipment_order_id: str):
    """Return the most recent manifest for a shipment evidence record."""
    _require_shipment_order(shipment_order_id)

    manifest = get_manifest_for_shipment(shipment_order_id)
    if manifest is None:
        raise HTTPException(
            status_code=404,
            detail=f"No manifest found for shipment '{shipment_order_id}'.",
        )
    return manifest


@app.get("/api/manifests/{manifest_id}")
def get_manifest_by_id(manifest_id: str):
    """Return a manifest by its own UUID."""
    manifest = get_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Manifest not found.")
    return manifest


@app.put("/api/manifests/{manifest_id}")
def update_manifest_by_id(manifest_id: str, payload: dict):
    """Replace all items on a DRAFT manifest."""
    manifest = get_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Manifest not found.")

    items = payload.get("items")
    if not isinstance(items, list):
        raise HTTPException(status_code=422, detail="'items' must be a list.")

    notes = payload.get("notes")
    if notes is not None:
        notes = str(notes).strip() or None

    try:
        updated = update_manifest(manifest_id, items, notes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return updated


@app.post("/api/manifests/{manifest_id}/finalize")
def finalize_manifest_by_id(manifest_id: str):
    """Finalize a DRAFT manifest and compute its SHA-256 fingerprint."""
    manifest = get_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Manifest not found.")

    try:
        finalized = finalize_manifest(manifest_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return finalized


# ---------------------------------------------------------------------------
# Packing inspection endpoints
# ---------------------------------------------------------------------------

from app.packing_inspector import (
    validate_and_store_photo,
    run_inspection,
    MAX_PHOTOS_PER_INSPECTION,
    MAX_PHOTO_BYTES,
    GeminiUnavailableError,
)


@app.post("/api/manifests/{manifest_id}/inspections", status_code=201)
async def create_packing_inspection(
    manifest_id: str,
    photos: list[UploadFile] = File(...),
):
    """Upload packing photographs and run a Gemini visual inspection.

    Accepts 1–5 JPEG, PNG, or WebP photographs. Validates file content by
    magic bytes — filename and MIME header are not trusted.

    The manifest must exist and be FINALIZED before an inspection can be
    submitted. Inspection status is always PENDING_HUMAN_REVIEW.
    """
    # 1. Resolve and validate manifest.
    manifest = get_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Manifest not found.")
    if manifest["status"] != "FINALIZED":
        raise HTTPException(
            status_code=422,
            detail="Inspections can only be submitted for FINALIZED manifests.",
        )

    linked_shipment = (
        get_shipment_by_order_id(manifest["shipment_order_id"])
        if manifest.get("shipment_order_id")
        else None
    )
    if linked_shipment and linked_shipment.get("tracking_submission_status") == "SUBMITTED":
        raise HTTPException(
            status_code=409,
            detail="Tracking has already been submitted. Packing inspections for this shipment are closed.",
        )

    # 2. Enforce photo count limits.
    if not photos:
        raise HTTPException(status_code=422, detail="At least one photograph is required.")
    if len(photos) > MAX_PHOTOS_PER_INSPECTION:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum {MAX_PHOTOS_PER_INSPECTION} photographs per inspection.",
        )

    # 3. Read each upload in bounded chunks, validate, and store.
    # Track stored paths so we can delete them if any later step fails.
    photo_metas: list[dict] = []
    stored_paths: list = []

    async def _cleanup_stored():
        """Delete every photo file stored so far in this request."""
        for p in stored_paths:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass

    for upload in photos:
        # Read in chunks, enforcing the per-file size cap before buffering.
        chunks: list[bytes] = []
        total = 0
        chunk_size = 64 * 1024  # 64 KB
        while True:
            chunk = await upload.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_PHOTO_BYTES:
                await upload.close()
                await _cleanup_stored()
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Photo '{upload.filename or 'upload'}' exceeds the "
                        f"10 MB per-file limit."
                    ),
                )
            chunks.append(chunk)
        raw = b"".join(chunks)

        try:
            meta = validate_and_store_photo(raw, upload.filename or "upload")
        except ValueError as exc:
            await _cleanup_stored()
            raise HTTPException(status_code=422, detail=str(exc))

        photo_metas.append(meta)
        stored_paths.append(meta["path"])

    # 4. Run Gemini inspection; clean up photos on failure.
    try:
        result = run_inspection(manifest, photo_metas)
    except GeminiUnavailableError as exc:
        await _cleanup_stored()
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        await _cleanup_stored()
        raise HTTPException(status_code=502, detail=f"Gemini inspection failed: {str(exc)}")

    # 5. Build photo records for persistence (no internal paths).
    photo_records = [
        {
            "id": m["id"],
            "sha256": m["sha256"],
            "mime_type": m["mime_type"],
            "size_bytes": m["size_bytes"],
        }
        for m in photo_metas
    ]

    # 6. Persist; clean up photos if the DB write fails.
    try:
        inspection = create_inspection(
            manifest_id=manifest_id,
            manifest_hash=manifest["manifest_hash"],
            model_used=result["model_used"],
            ai_result={
                **result["ai_result"],
                "engine_metadata": result["engine_metadata"],
            },
            photo_records=photo_records,
        )
    except Exception:
        await _cleanup_stored()
        raise

    # Photos are now safely referenced in the DB — do not delete them.
    # Strip any internal fields before returning.
    return {
        "inspection_id": inspection["id"],
        "manifest_id": manifest_id,
        "inspection_status": inspection["inspection_status"],
        "manifest_hash_at_inspection": inspection["manifest_hash_at_inspection"],
        "photo_count": inspection["photo_count"],
        "photos": [
            {
                "id": p["id"],
                "sha256": p["sha256"],
                "mime_type": p["mime_type"],
                "size_bytes": p["size_bytes"],
            }
            for p in inspection["photos"]
        ],
        "ai_result": inspection["ai_result"],
        "review_history": inspection.get("review_history", []),
        "model_used": inspection["model_used"],
        "created_at": inspection["created_at"],
    }


@app.get("/api/manifests/{manifest_id}/inspections")
def list_manifest_inspections(manifest_id: str):
    """List all inspections for a manifest, most recent first."""
    manifest = get_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Manifest not found.")
    inspections = list_inspections_for_manifest(manifest_id)
    return {
        "manifest_id": manifest_id,
        "inspections": [
            {
                "inspection_id": i["id"],
                "inspection_status": i["inspection_status"],
                "photo_count": i["photo_count"],
                "model_used": i["model_used"],
                "manifest_hash_at_inspection": i["manifest_hash_at_inspection"],
                "created_at": i["created_at"],
            }
            for i in inspections
        ],
    }


@app.get("/api/inspections/{inspection_id}")
def get_inspection_by_id(inspection_id: str):
    """Retrieve a single inspection by its UUID."""
    inspection = get_inspection(inspection_id)
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    return {
        "inspection_id": inspection["id"],
        "manifest_id": inspection["manifest_id"],
        "inspection_status": inspection["inspection_status"],
        "manifest_hash_at_inspection": inspection["manifest_hash_at_inspection"],
        "photo_count": inspection["photo_count"],
        "photos": [
            {
                "id": p["id"],
                "sha256": p["sha256"],
                "mime_type": p["mime_type"],
                "size_bytes": p["size_bytes"],
            }
            for p in inspection["photos"]
        ],
        "ai_result": inspection["ai_result"],
        "model_used": inspection["model_used"],
        "created_at": inspection["created_at"],
        "updated_at": inspection["updated_at"],
    }
