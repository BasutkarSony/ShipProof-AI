from datetime import date


def validate_order(order: dict) -> dict:
    """Deterministic checks; never invent or certify delivery evidence."""
    issues = []
    warnings = []

    required = ["order_id", "transaction_id", "tracking_number", "carrier", "status"]

    for field in required:
        if not str(order.get(field, "")).strip():
            issues.append({
                "code": f"missing_{field}",
                "field": field,
                "message": f"Missing required field: {field.replace('_', ' ')}.",
            })

    parsed_dates = {}
    for field in ("shipped_date", "delivered_date"):
        value = order.get(field)
        if not value:
            continue
        try:
            parsed_dates[field] = date.fromisoformat(str(value))
        except ValueError:
            issues.append({
                "code": "invalid_date",
                "field": field,
                "message": f"{field.replace('_', ' ').capitalize()} must use YYYY-MM-DD format.",
            })

    shipped = parsed_dates.get("shipped_date")
    delivered = parsed_dates.get("delivered_date")
    if shipped and shipped > date.today():
        issues.append({"code": "shipment_date_in_future", "field": "shipped_date", "message": "Shipment date cannot be in the future."})
    if delivered and delivered > date.today():
        issues.append({"code": "delivery_date_in_future", "field": "delivered_date", "message": "Delivery date cannot be in the future."})
    if shipped and delivered and delivered < shipped:
        issues.append({"code": "delivery_before_shipment", "field": "delivered_date", "message": "Delivery date is earlier than shipment date."})

    status = str(order.get("status", "")).upper()
    if status == "DELIVERED" and not delivered:
        warnings.append({
            "code": "missing_delivery_date",
            "field": "delivered_date",
            "message": "Status says delivered, but no delivery date was supplied.",
        })

    if status not in {"SHIPPED", "ON_HOLD", "DELIVERED", "CANCELLED", ""}:
        issues.append({
            "code": "unsupported_status",
            "field": "status",
            "message": "Status must be SHIPPED, ON_HOLD, DELIVERED, or CANCELLED.",
        })

    carrier = str(order.get("carrier", "")).strip().upper()
    if carrier == "OTHER" and not str(order.get("carrier_name_other", "")).strip():
        issues.append({"code": "missing_carrier_name_other", "field": "carrier_name_other", "message": "Provide the carrier name when carrier is OTHER."})

    return {
        "order_id": order.get("order_id"),
        "result": "BLOCKED" if issues else ("WARNING" if warnings else "PASS"),
        "issues": issues,
        "warnings": warnings,
        "note": "This is a preliminary data-quality check, not a guarantee of PayPal Seller Protection eligibility.",
    }
