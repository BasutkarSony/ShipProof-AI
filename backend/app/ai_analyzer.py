import re
from datetime import date
from typing import Any, Dict, List, Optional


CARRIER_PATTERNS = {
    "UPS": re.compile(r"^1Z[0-9A-Z]{16}$", re.IGNORECASE),
    "FEDEX": re.compile(r"^(\d{12}|\d{15}|\d{20}|\d{22})$"),
    "USPS": re.compile(r"^(9[1-5]\d{20}|[A-Z]{2}\d{9}[A-Z]{2}|\d{20}|\d{22})$", re.IGNORECASE),
    "DHL": re.compile(r"^(\d{10}|\d{11})$"),
}

EXCEPTION_KEYWORDS = [
    "returned to sender",
    "delivery failed",
    "damaged in transit",
    "refused by recipient",
    "held at customs",
    "incorrect address",
    "undeliverable",
    "package lost",
]

SIGNATURE_KEYWORDS = [
    "signed by",
    "signature received",
    "signature on file",
    "adult signature",
    "direct signature",
    "customer signature",
    "signature confirmed",
]

NO_SIGNATURE_KEYWORDS = [
    "without signature",
    "no signature",
    "no signature requested",
    "signature waived",
    "waived signature",
    "left at front door",
    "left at doorstep",
    "left at front doorstep",
    "left on porch",
]


def _detect_probable_carrier(tracking_number: str) -> Optional[str]:
    cleaned = tracking_number.strip().replace(" ", "").replace("-", "")
    for carrier, pattern in CARRIER_PATTERNS.items():
        if pattern.match(cleaned):
            return carrier
    return None


def analyze_shipment_evidence(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    AI-assisted shipment-evidence and PayPal Seller Protection readiness analyzer.
    Analyzes shipment milestones, tracking consistency, delivery proofs,
    high-value signature compliance, and generates PayPal Add Tracking preview payloads.
    """
    order_id = str(order.get("order_id", "UNKNOWN")).strip()
    transaction_id = str(order.get("transaction_id", "")).strip()
    tracking_number = str(order.get("tracking_number", "")).strip()
    carrier = str(order.get("carrier", "")).strip().upper()
    carrier_other = str(order.get("carrier_name_other", "")).strip()
    status = str(order.get("status", "")).strip().upper()
    shipped_date = str(order.get("shipped_date", "") or "").strip()
    delivered_date = str(order.get("delivered_date", "") or "").strip()
    transaction_date = str(order.get("transaction_date", "") or "").strip()
    shipping_address = str(order.get("shipping_address", "") or "").strip()
    evidence_text = str(order.get("evidence_text", "") or "").strip()

    # Numerical order amount assessment for PayPal Seller Protection threshold
    raw_amount = order.get("amount", 0.0)
    try:
        amount = float(raw_amount)
    except (ValueError, TypeError):
        amount = 0.0
    currency = str(order.get("currency", "USD")).strip().upper() or "USD"

    # PayPal $750 signature policy effective date (August 2, 2023 per public PayPal UA4.0 changelog).
    # A transaction processed on or after this date is subject to the $750+ signature requirement.
    POLICY_EFFECTIVE_DATE = date(2023, 8, 2)

    # Determine policy applicability from the explicit transaction_date field only.
    # Do NOT use shipped_date or delivered_date as a proxy.
    parsed_transaction_date = None
    if transaction_date:
        try:
            parsed_transaction_date = date.fromisoformat(transaction_date)
            if parsed_transaction_date >= POLICY_EFFECTIVE_DATE:
                policy_applicability = "CONFIRMED"
            else:
                policy_applicability = "PRE_POLICY"
        except ValueError:
            policy_applicability = "REQUIRES_REVIEW"
    else:
        policy_applicability = "REQUIRES_REVIEW"

    strengths: List[str] = []
    risk_factors: List[str] = []
    recommendations: List[str] = []
    exceptions_detected: List[str] = []

    score = 100

    # 1. Transaction & Order ID baseline
    if not transaction_id:
        score -= 25
        risk_factors.append("Missing PayPal transaction ID.")
        recommendations.append("Attach the genuine PayPal transaction ID associated with this payment.")
    elif transaction_id.upper().startswith("SANDBOX-TXN-"):
        # Synthetic / demo ID
        score -= 5
        risk_factors.append("Sample transaction ID detected (SANDBOX-TXN-*).")
        recommendations.append("Replace with a genuine PayPal Sandbox capture ID before live testing.")

    # 2. Tracking number presence & carrier matching
    cleaned_tracking = tracking_number.replace(" ", "").replace("-", "")
    if not tracking_number:
        score -= 40
        risk_factors.append("No tracking number provided.")
        recommendations.append("Obtain an official carrier tracking number before submitting evidence.")
    else:
        strengths.append(f"Tracking number provided: {tracking_number}")
        probable_carrier = _detect_probable_carrier(tracking_number)

        if carrier in CARRIER_PATTERNS:
            if CARRIER_PATTERNS[carrier].match(cleaned_tracking):
                strengths.append(f"Tracking number matches standard {carrier} format.")
            elif probable_carrier and probable_carrier != carrier:
                score -= 15
                risk_factors.append(
                    f"Format mismatch: tracking number matches {probable_carrier} format, but carrier is set to {carrier}."
                )
                recommendations.append(f"Verify whether this package was actually shipped via {probable_carrier}.")
            elif tracking_number.upper().startswith(("DEMO", "TRACK", "TEST")):
                strengths.append(f"Demonstration/simulated tracking number provided for testing.")
        elif carrier == "OTHER":
            if not carrier_other:
                score -= 20
                risk_factors.append("Carrier is set to 'OTHER' but no carrier name was specified.")
                recommendations.append("Provide the specific carrier name (carrier_name_other) required by PayPal.")
            else:
                strengths.append(f"Custom carrier documented: {carrier_other}")

    # 3. PayPal Seller Protection High-Value ($750+) Signature Check
    high_value_threshold = 750.0
    is_high_value = amount >= high_value_threshold
    signature_explicit = bool(order.get("signature_obtained", False))
    evidence_lower = evidence_text.lower()
    has_sig_proof = any(kw in evidence_lower for kw in SIGNATURE_KEYWORDS)
    has_no_sig_keyword = any(kw in evidence_lower for kw in NO_SIGNATURE_KEYWORDS)

    if has_no_sig_keyword and not has_sig_proof:
        carrier_signature_state = "EXPLICITLY_MISSING"
    elif has_sig_proof and not has_no_sig_keyword:
        carrier_signature_state = "CARRIER_VERIFIED"
    elif has_sig_proof and has_no_sig_keyword:
        carrier_signature_state = "AMBIGUOUS"
    else:
        carrier_signature_state = "NOT_IN_CARRIER_LOG"

    if is_high_value:
        # Note policy applicability in risk factors when transaction date is unknown
        if policy_applicability == "REQUIRES_REVIEW":
            risk_factors.append(
                f"Transaction processing date is unavailable. PayPal $750+ signature confirmation "
                f"policy applicability (effective {POLICY_EFFECTIVE_DATE.isoformat()}) cannot be "
                f"confirmed without the actual transaction date."
            )
            recommendations.append(
                "Record the PayPal transaction processing date (transaction_date) to confirm "
                "whether the $750+ signature confirmation requirement applies to this order."
            )

        if carrier_signature_state == "CARRIER_VERIFIED":
            signature_satisfied = True
            signature_status = "SATISFIED"
            strengths.append(
                f"High-value order ({currency} {amount:.2f} >= {high_value_threshold:.2f}): Verifiable carrier delivery record confirms recipient signature."
            )
        elif carrier_signature_state == "EXPLICITLY_MISSING":
            signature_satisfied = False
            signature_status = "MISSING_REQUIRED"
            score -= 25
            risk_factors.append(
                f"High-value order ({currency} {amount:.2f} >= {high_value_threshold:.2f}): Carrier delivery log explicitly records package was left without signature. Ineligible for Item Not Received protection under PayPal policy."
            )
            recommendations.append(
                f"Obtain official carrier proof-of-delivery documenting recipient signature confirmation from {carrier or 'the carrier'} before submitting evidence."
            )
        elif signature_explicit and carrier_signature_state == "NOT_IN_CARRIER_LOG":
            signature_satisfied = False
            signature_status = "MERCHANT_ATTESTED_UNVERIFIED"
            score -= 15
            risk_factors.append(
                f"High-value order ({currency} {amount:.2f} >= {high_value_threshold:.2f}): Merchant indicates signature on file, but carrier tracking scan has not confirmed signature."
            )
            recommendations.append(
                f"Attach official carrier electronic proof of delivery (ePOD) with signature confirmation from {carrier or 'the carrier'}."
            )
        else:
            signature_satisfied = False
            signature_status = "MISSING_REQUIRED"
            score -= 25
            risk_factors.append(
                f"High-value order ({currency} {amount:.2f} >= {high_value_threshold:.2f}): PayPal requires verifiable proof of signature confirmation for Item Not Received disputes."
            )
            recommendations.append(
                f"Request signature confirmation documentation from {carrier or 'the carrier'} before submitting to PayPal."
            )
    else:
        if carrier_signature_state == "CARRIER_VERIFIED" or signature_explicit:
            signature_satisfied = True
            signature_status = "SATISFIED"
            if amount > 0:
                strengths.append(f"Standard value transaction ({currency} {amount:.2f}); signature confirmation documented.")
        else:
            signature_satisfied = False
            signature_status = "NOT_REQUIRED"
            if amount > 0:
                strengths.append(f"Standard value transaction ({currency} {amount:.2f}); signature confirmation is optional.")

    # 4. Dates & Chronology Consistency
    parsed_shipped = None
    parsed_delivered = None
    today = date.today()

    if shipped_date:
        try:
            parsed_shipped = date.fromisoformat(shipped_date)
            if parsed_shipped > today:
                score -= 30
                risk_factors.append(f"Shipment date ({shipped_date}) is in the future.")
                recommendations.append("Correct the shipment date to reflect actual carrier dispatch.")
            else:
                strengths.append(f"Dispatch date documented ({shipped_date}).")
        except ValueError:
            score -= 15
            risk_factors.append(f"Shipment date format invalid: '{shipped_date}'. Must be YYYY-MM-DD.")

    if delivered_date:
        try:
            parsed_delivered = date.fromisoformat(delivered_date)
            if parsed_delivered > today:
                score -= 30
                risk_factors.append(f"Delivery date ({delivered_date}) is in the future.")
                recommendations.append("Delivery cannot be recorded in the future.")
            elif parsed_shipped and parsed_delivered < parsed_shipped:
                score -= 35
                risk_factors.append("Delivery date precedes shipment date.")
                recommendations.append("Resolve chronological conflict between shipping and delivery records.")
            else:
                strengths.append(f"Confirmed delivery date ({delivered_date}).")
        except ValueError:
            score -= 15
            risk_factors.append(f"Delivery date format invalid: '{delivered_date}'. Must be YYYY-MM-DD.")

    if status == "DELIVERED" and not delivered_date:
        score -= 10
        risk_factors.append("Status is marked DELIVERED but no delivery date is recorded.")
        recommendations.append("Include the delivery date from carrier tracking to substantiate delivery proof.")

    # 5. Evidence Text & Carrier Exception Analysis
    if evidence_text:
        for kw in EXCEPTION_KEYWORDS:
            if kw in evidence_lower:
                exceptions_detected.append(kw)
                score -= 25
                risk_factors.append(f"Carrier scan alert: '{kw}' found in tracking log.")
                recommendations.append("Investigate delivery failure or carrier exception with the logistics provider.")

        # Address verification against shipping address
        if shipping_address:
            # Extract postal code or city tokens
            addr_tokens = [t.strip().lower() for t in re.split(r"[, ]+", shipping_address) if len(t.strip()) >= 3]
            matched_tokens = [t for t in addr_tokens if t in evidence_lower]
            if matched_tokens:
                strengths.append(f"Carrier scan destination matches shipping address ({', '.join(set(matched_tokens[:2]))}).")
            else:
                recommendations.append("Ensure carrier tracking log explicitly confirms delivery to the buyer's destination city/zip.")
        else:
            recommendations.append("Record buyer's destination shipping address to ensure matching with PayPal transaction details.")
    else:
        recommendations.append("Attach carrier tracking milestones or delivery log notes to strengthen evidence defense.")

    # Calculate final score and protection tier
    final_score = max(0, min(100, score))

    if final_score >= 85:
        tier = "FULL_PROTECTION_READY"
        readiness_label = "High Readiness - Strong Evidence"
    elif final_score >= 70:
        tier = "CONDITIONAL_PROTECTION"
        readiness_label = "Moderate Readiness - Minor Review Needed"
    elif final_score >= 45:
        tier = "EVIDENCE_INCOMPLETE"
        readiness_label = "Low Readiness - Key Evidence Missing"
    else:
        tier = "CRITICAL_DEFECT"
        readiness_label = "Blocked - Incompatible for Submission"

    # Seller Protection Eligibility Matrix
    inr_eligible = (
        final_score >= 70
        and bool(tracking_number)
        and (not is_high_value or signature_satisfied)
        and status in ("SHIPPED", "DELIVERED")
    )
    unauthorized_eligible = final_score >= 70 and bool(tracking_number) and bool(shipped_date)

    # PayPal Orders v2 Add Tracking preview.
    paypal_tracking_request_body: Dict[str, Any] = {
        "capture_id": transaction_id,
        "tracking_number": tracking_number,
        "carrier": carrier or "OTHER",
        "notify_payer": False,
    }
    if carrier == "OTHER" and carrier_other:
        paypal_tracking_request_body["carrier_name_other"] = carrier_other

    paypal_payload_preview = {
        "endpoint": "POST /v2/checkout/orders/{paypal_order_id}/track",
        "request_body": paypal_tracking_request_body,
        "submission_safety_status": "DISABLED_BY_DEFAULT",
        "safety_gate_note": (
            "Tracking submission requires a verified paid checkout, the latest finalized-manifest "
            "inspection to be human-approved, and PAYPAL_TRACKING_SUBMISSION_ENABLED=true."
        ),
    }

    return {
        "order_id": order_id,
        "readiness_score": final_score,
        "protection_tier": tier,
        "readiness_label": readiness_label,
        "seller_protection": {
            "item_not_received_eligible": inr_eligible,
            "unauthorized_transaction_eligible": unauthorized_eligible,
            "signature_confirmation": {
                "required": is_high_value,
                "threshold": high_value_threshold,
                "order_amount": amount,
                "currency": currency,
                "detected": signature_satisfied,
                "status": signature_status,
                "verification_source": "CARRIER_SCAN" if carrier_signature_state == "CARRIER_VERIFIED" else ("MERCHANT_ATTESTATION" if signature_explicit else "NONE"),
                "policy_applicability": policy_applicability,
                "policy_effective_date": POLICY_EFFECTIVE_DATE.isoformat(),
            },
            "disclaimer": "Preliminary evidence assessment only. Official Seller Protection eligibility is determined exclusively by PayPal during dispute adjudication.",
        },
        "carrier_analysis": {
            "carrier": carrier,
            "probable_detected_carrier": _detect_probable_carrier(tracking_number) if tracking_number else None,
            "format_valid": bool(
                carrier in CARRIER_PATTERNS and CARRIER_PATTERNS[carrier].match(cleaned_tracking)
            ) if tracking_number and carrier in CARRIER_PATTERNS else None,
        },
        "evidence_summary": {
            "exceptions_detected": exceptions_detected,
            "signature_detected": signature_satisfied,
            "evidence_provided": bool(evidence_text),
        },
        "engine_metadata": {
            "type": "DETERMINISTIC_RULES_NLP",
            "name": "Deterministic Policy & NLP Heuristics Engine",
            "auditable": True,
            "zero_hallucination": True,
            "description": "Deterministic rule-based expert system with NLP pattern extraction. Evaluates carrier tracking patterns, milestone chronology, and PayPal Seller Protection criteria without external LLM hallucinations.",
        },
        "strengths": strengths,
        "risk_factors": risk_factors,
        "recommendations": recommendations,
        "paypal_payload_preview": paypal_payload_preview,
    }
