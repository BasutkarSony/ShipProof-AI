 <div align="center">

# ShipProof AI

### Shipment Evidence Intelligence for PayPal Merchants

**Validate. Investigate. Remediate. Prepare with confidence.**

A shipment-evidence review assistant that helps merchants identify incomplete tracking records, inconsistent shipment information, and evidence gaps before preparing PayPal tracking submissions.

<br />

![Status](https://img.shields.io/badge/Status-Hackathon%20Prototype-2563EB?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-Vite-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PayPal](https://img.shields.io/badge/Integration-PayPal%20Sandbox-003087?style=for-the-badge&logo=paypal&logoColor=white)

<br />

**Built for the PayPal AI Hackathon 2026**

</div>

---

## The problem

Shipment information is often spread across order records, tracking numbers, carrier updates, delivery events, and payment transactions.

When this information is incomplete or inconsistent, merchants must manually investigate and correct records before preparing shipment evidence.

**ShipProof AI addresses this preparation gap.**

It provides a centralized workflow for reviewing shipment data, identifying evidence-quality issues, understanding potential risks, and preparing a PayPal tracking payload for review.

## What ShipProof AI does

| Capability | What it provides |
|---|---|
| Shipment validation | Checks required shipment, order, transaction, tracking, and carrier information. |
| Evidence analysis | Examines tracking patterns, delivery milestones, exceptions, and signature-related indicators. |
| Issue detection | Highlights missing information, invalid dates, inconsistencies, and evidence gaps. |
| Evidence remediation | Allows merchants to review and edit shipment information and recalculate validation. |
| Readiness assessment | Presents an advisory evidence-quality assessment with actionable findings. |
| PayPal integration | Supports Sandbox OAuth verification and tracking payload preparation. |
| Payment-to-shipment integration | Links verified PayPal checkout captures directly to persistent shipment records and manifests. |
| Submission safeguards | Keeps tracking writes disabled by default. |

## How it works

```mermaid
flowchart TD
    A["Select Shipment"] --> B["Validate Shipment Data"]
    B --> C["Analyze Evidence"]
    C --> D{"Issues Found?"}
    D -->|Yes| E["Review Findings"]
    E --> F["Correct or Confirm Evidence"]
    F --> G["Recalculate Validation"]
    D -->|No| G
    G --> H["Review Evidence Quality"]
    H --> I["Generate PayPal Payload Preview"]
    I --> J["Merchant Review"]
    J --> K["Tracking Submission Gate"]
    K --> L["Disabled by Default"]
```

## Core workflow

### 01 — Select a shipment

Review shipment records with their order references, tracking information, carrier, destination, and current status.

### 02 — Identify evidence issues

Analyze shipment information to identify:

- Missing tracking information.
- Invalid carrier and tracking-number combinations.
- Shipment and delivery date inconsistencies.
- Delivery exceptions and suspicious milestone sequences.
- Destination and address inconsistencies.
- Signature-related evidence gaps.

### 03 — Review and remediate

Open the evidence inspector, examine findings, edit available shipment information, and recalculate the assessment.

Merchant-provided statements are not equivalent to independently verified carrier evidence.

### 04 — Review the PayPal payload

Inspect the generated tracking payload before any external operation.

The standard workflow does not automatically submit tracking information.

### 05 — Packaging checkout & payment-to-shipment workflow

Merchants can order packaging supplies through the catalogue checkout:
- **Server-Calculated Orders**: Client-side prices and totals are never trusted; order totals are computed from the server catalog.
- **Strict Verification**: PayPal Sandbox order captures are strictly validated for completed status, USD currency, and exact amount matching before marking an order as `PAID`.
- **Persistent Shipment Linkage**: Upon successful verification, a persistent shipment record is automatically created and idempotently linked to the checkout order via `checkout_order_id` and `paypal_capture_id`.
- **Manifest Management**: Newly paid shipments appear in Shipment & Manifest Management. Merchants create and edit DRAFT manifests for the actual merchandise being shipped (purchased packaging supplies are not automatically treated as shipment contents).
- **Packing Station & AI Review**: Finalized manifests with deterministic SHA-256 fingerprints proceed to the Packing Station for photo upload and Gemini inspection (held at `PENDING_HUMAN_REVIEW`).

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, JavaScript, CSS |
| Backend | Python, FastAPI |
| Validation | Deterministic validation rules |
| Evidence analysis | Rule-based checks and NLP-style text heuristics |
| Payments integration | PayPal REST API – Sandbox |
| Testing | Python unittest, Oxlint, Vite build |

### Architecture

```mermaid
flowchart LR
    UI["React Frontend"] --> API["FastAPI Backend"]
    API --> V["Shipment Validator"]
    API --> A["Evidence Analyzer"]
    API --> P["PayPal Client"]
    V --> R["Validation Results"]
    A --> R
    P --> S["OAuth Verification"]
    P --> T["Payload Preview"]
    R --> UI
    S --> UI
    T --> UI
```

## Run locally

### Prerequisites

- Python 3.11 or compatible supported version.
- Node.js and npm.
- Git.

### 1. Clone the repository

```powershell
git clone https://github.com/BasutkarSony/ShipProof-AI.git
cd ShipProof-AI
```

Replace `BasutkarSony` with the GitHub repository owner.

### 2. Set up the backend

Open a PowerShell terminal:

```powershell
cd backend

python -m venv .venv

.\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
```

Start the backend:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend:

`http://127.0.0.1:8000`

### 3. Set up the frontend

Open a second terminal:

```powershell
cd frontend

npm ci

npm run dev
```

Frontend:

`http://localhost:5173`

### 4. Configure PayPal Sandbox

For Sandbox connection verification:

1. Create or use a PayPal Sandbox REST application.
2. Copy `backend/.env.example` to `backend/.env`.
3. Add the required Sandbox credentials using the variable names provided in the example file.
4. Restart the backend if necessary.

**Never commit or share your actual `.env` file or API credentials.**

## PayPal integration and safety

ShipProof AI includes a PayPal Sandbox authentication-verification workflow and a tracking payload preview.

The external tracking endpoint used for payload preparation is:

`POST /v1/shipping/trackers-batch`

Tracking writes are disabled by default:

```env
PAYPAL_TRACKING_SUBMISSION_ENABLED=false
```

The safeguards distinguish between:

- Successful Sandbox OAuth authentication.
- Tracking payload preparation.
- Actual tracking submission.

Successful authentication does not mean tracking data has been submitted.

A real PayPal transaction ID is required for an actual tracking operation. Sample identifiers such as `SANDBOX-TXN-1001` are demonstration data, not valid PayPal transactions.

Official documentation:

- [PayPal Add Tracking API](https://developer.paypal.com/api/tracking/track-orders/use/)
- [PayPal Supported Carriers](https://developer.paypal.com/track-orders/carriers/)

## Demo scenarios

The sample dataset contains shipment scenarios designed to demonstrate validation and evidence review.

| Order | Demonstration scenario |
|---|---|
| ORD-1001 | Standard shipment record |
| ORD-1002 | Missing tracking information |
| ORD-1003 | Delivery date earlier than shipment date |
| ORD-1004 | High-value shipment with signature-related evidence |
| ORD-1005 | High-value shipment with a signature-evidence concern |

### Suggested demonstration

1. Start the frontend and backend.
2. Open the shipment queue.
3. Run the available shipment checks.
4. Select `ORD-1002` to demonstrate missing tracking information.
5. Select `ORD-1003` to demonstrate a chronology issue.
6. Inspect `ORD-1005` to demonstrate evidence review and remediation.
7. Review the updated findings and PayPal payload preview.
8. Show that tracking submission remains disabled.

## Testing

### Backend tests

From the backend directory:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Frontend checks

From the frontend directory:

```powershell
npx oxlint src

npm run build
```

Use the project's installed dependencies and scripts when running the checks.

## Important limitations

ShipProof AI is a hackathon prototype, not an official PayPal product.

- Current evidence analysis uses deterministic rules and text-pattern heuristics; it should not be represented as verified generative AI inference.
- Text entered by a merchant is not independent proof from a carrier.
- A readiness assessment is an advisory evidence-quality indicator, not a prediction of dispute outcomes.
- ShipProof AI cannot guarantee PayPal Seller Protection or determine PayPal's final decision.
- Carrier verification depends on the availability of an authoritative verification source.
- Sample shipment records are for demonstration and testing.
- PayPal Sandbox authentication does not prove that tracking submission works.

## Project structure

```text
ShipProof-AI/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── ai_analyzer.py
│   │   ├── validator.py
│   │   └── paypal_client.py
│   │
│   ├── data/
│   │   └── sample_orders.json
│   │
│   ├── tests/
│   │   ├── test_ai_analyzer.py
│   │   └── test_validator.py
│   │
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── main.jsx
│   │   └── style.css
│   │
│   ├── package.json
│   └── vite.config.js
│
├── .gitignore
├── README.md
└── shipproof_paypal_setup.ps1
```

## Security

Do not commit:

- `.env` files or API credentials.
- Salesforce CLI state and `.sf` metadata.
- Python virtual environments.
- `node_modules` and generated build files.
- Access tokens, private keys, or other confidential configuration.

Review `.gitignore` before publishing changes.

---

<div align="center">

### ShipProof AI

**Better shipment evidence starts with better data.**

Built for the PayPal AI Hackathon 2026.

</div>

## Repository

[GitHub Repository](https://github.com/BasutkarSony/ShipProof-AI) · [MIT License](LICENSE)
