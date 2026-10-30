$ErrorActionPreference = "Stop"

$root = (Get-Location).Path
$backend = Join-Path $root "backend"
$mainPath = Join-Path $backend "app\main.py"
$envExample = Join-Path $backend ".env.example"
$gitignorePath = Join-Path $backend ".gitignore"
$envPath = Join-Path $backend ".env"

if (!(Test-Path $mainPath)) {
    throw "Run this script from D:\Hackathon\ShipProof-AI (the project root). Could not find backend\app\main.py."
}

$paypalClient = @'
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"


class PayPalConfigurationError(RuntimeError):
    pass


def configured() -> bool:
    return bool(
        os.getenv("PAYPAL_CLIENT_ID", "").strip()
        and os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    )


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
    token = get_access_token()
    tracker = {
        "transaction_id": str(order.get("transaction_id", "")).strip(),
        "tracking_number": str(order.get("tracking_number", "")).strip(),
        "status": str(order.get("status", "SHIPPED")).strip().upper(),
        "carrier": str(order.get("carrier", "")).strip().upper(),
    }
    if tracker["carrier"] == "OTHER":
        carrier_name = str(order.get("carrier_name_other", "")).strip()
        if not carrier_name:
            raise ValueError(
                "When carrier is OTHER, provide carrier_name_other (the carrier's name)."
            )
        tracker["carrier_name_other"] = carrier_name

    response = requests.post(
        f"{SANDBOX_BASE}/v1/shipping/trackers-batch",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"trackers": [tracker]},
        timeout=30,
    )
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
'@

$main = @'
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.validator import validate_order
from app.paypal_client import (
    configured as paypal_configured,
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


@app.get("/api/paypal/status")
def paypal_status():
    return {
        "provider": "PayPal Sandbox",
        "configured": paypal_configured(),
        "base_url": "https://api-m.sandbox.paypal.com",
        "note": "Sandbox only. This status does not verify credentials until an API call is made.",
    }


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
'@

$envTemplate = @'
# PayPal Developer Dashboard > Apps & Credentials > Sandbox > your REST app
# Use the REST app Client ID and Secret, not legacy NVP/SOAP credentials.
PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
'@

$gitignore = @'
__pycache__/
.venv/
.env
*.pyc
'@

Set-Content -LiteralPath (Join-Path $backend "app\paypal_client.py") -Value $paypalClient -Encoding utf8
Set-Content -LiteralPath $mainPath -Value $main -Encoding utf8
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($envExample, $envTemplate, $utf8NoBom)
[System.IO.File]::WriteAllText($gitignorePath, $gitignore, $utf8NoBom)

if (!(Test-Path $envPath)) {
    [System.IO.File]::WriteAllText($envPath, $envTemplate, $utf8NoBom)
    Write-Host "Created backend\.env with blank credential fields."
} else {
    Write-Host "Kept your existing backend\.env unchanged."
}

Write-Host ""
Write-Host "PayPal Sandbox backend integration files are installed."
Write-Host "No API call was made and no credentials were read or displayed."
Write-Host "Next: add your Sandbox REST app Client ID and Secret to backend\.env."
Write-Host "Do not paste either value into chat or commit backend\.env."
Write-Host ""
Write-Host "Restart the backend server after updating files (Ctrl+C, then rerun your existing uvicorn command)."
