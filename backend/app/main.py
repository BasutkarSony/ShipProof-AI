from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.validator import validate_order
from app.ai_analyzer import analyze_shipment_evidence
from app.paypal_client import (
    configured as paypal_configured,
    submissions_enabled as paypal_submissions_enabled,
    get_access_token,
    submit_tracking,
    PayPalConfigurationError,
)
import json
from pathlib import Path

app = FastAPI(
    title="ShipProof AI API",
    description="Pre-submission shipment evidence validation and PayPal Sandbox tracking",
    version="0.2.0",
)

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
    with DATA_FILE.open("r", encoding="utf-8-sig") as file:
        orders = json.load(file)
    return {"orders": orders}


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


@app.post("/api/paypal/submit-tracking")
def paypal_submit_tracking(payload: dict):
    # Validate before any external write.
    result = validate_order(payload)
    if result["result"] != "PASS":
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Shipment did not pass ShipProof data-quality checks. Nothing was sent to PayPal.",
                "validation": result,
            },
        )

    transaction_id = str(payload.get("transaction_id", "")).strip()
    if not transaction_id or transaction_id.upper().startswith("SANDBOX-TXN-"):
        raise HTTPException(
            status_code=422,
            detail="This looks like a sample transaction ID. Use a genuine PayPal Sandbox transaction/capture ID before submitting.",
        )

    try:
        response = submit_tracking(payload)
        return {
            "submitted": True,
            "provider": "PayPal Sandbox",
            "validation": result,
            "paypal_response": response,
        }
    except PayPalConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
