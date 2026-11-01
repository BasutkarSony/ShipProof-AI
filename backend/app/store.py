import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shipproof.db"

TWO_PLACES = Decimal("0.01")


def _money(cents: int) -> str:
    return str((Decimal(cents) / 100).quantize(TWO_PLACES))

CATALOGUE = [
    {
        "sku": "SHIP-STD-001",
        "name": "Standard Shipping Box",
        "description": "Sturdy corrugated box for standard parcels.",
        "price": Decimal("12.99"),
    },
    {
        "sku": "SHIP-HEV-002",
        "name": "Heavy Duty Mailer",
        "description": "Reinforced mailer for heavy items up to 20 kg.",
        "price": Decimal("24.50"),
    },
    {
        "sku": "SHIP-FRA-003",
        "name": "Fragile Item Packaging",
        "description": "Double-walled box with padding for fragile goods.",
        "price": Decimal("18.75"),
    },
]


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                sku TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                price_cents INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                paypal_order_id TEXT UNIQUE,
                paypal_capture_id TEXT UNIQUE,
                payment_status TEXT NOT NULL DEFAULT 'CREATED',
                currency TEXT NOT NULL DEFAULT 'USD',
                total_cents INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_sku TEXT NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price_cents INTEGER NOT NULL,
                line_total_cents INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_orders_paypal_order_id ON orders(paypal_order_id);
            CREATE INDEX IF NOT EXISTS idx_orders_paypal_capture_id ON orders(paypal_capture_id);
            CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
            CREATE TABLE IF NOT EXISTS shipment_manifests (
                id TEXT PRIMARY KEY,
                shipment_order_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                notes TEXT,
                manifest_hash TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_shipment_manifests_order_id
                ON shipment_manifests(shipment_order_id);
            CREATE TABLE IF NOT EXISTS manifest_items (
                id TEXT PRIMARY KEY,
                manifest_id TEXT NOT NULL REFERENCES shipment_manifests(id) ON DELETE CASCADE,
                sku TEXT,
                description TEXT NOT NULL,
                expected_qty INTEGER NOT NULL,
                unit_value_cents INTEGER,
                fragile INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_manifest_items_manifest_id
                ON manifest_items(manifest_id);
            CREATE TABLE IF NOT EXISTS packing_inspections (
                id TEXT PRIMARY KEY,
                manifest_id TEXT NOT NULL REFERENCES shipment_manifests(id),
                inspection_status TEXT NOT NULL DEFAULT 'PENDING_HUMAN_REVIEW',
                photo_count INTEGER NOT NULL DEFAULT 0,
                model_used TEXT,
                ai_result TEXT,
                manifest_hash_at_inspection TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_packing_inspections_manifest_id
                ON packing_inspections(manifest_id);
            CREATE TABLE IF NOT EXISTS inspection_photos (
                id TEXT PRIMARY KEY,
                inspection_id TEXT NOT NULL REFERENCES packing_inspections(id) ON DELETE CASCADE,
                sha256 TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_inspection_photos_inspection_id
                ON inspection_photos(inspection_id);
            CREATE TABLE IF NOT EXISTS shipments (
                id TEXT PRIMARY KEY,
                order_id TEXT UNIQUE NOT NULL,
                checkout_order_id TEXT UNIQUE NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                paypal_order_id TEXT NOT NULL,
                paypal_capture_id TEXT UNIQUE NOT NULL,
                tracking_number TEXT NOT NULL DEFAULT '',
                carrier TEXT NOT NULL DEFAULT 'OTHER',
                carrier_name_other TEXT NOT NULL DEFAULT 'UNASSIGNED',
                status TEXT NOT NULL DEFAULT 'ON_HOLD',
                shipped_date TEXT,
                delivered_date TEXT,
                transaction_date TEXT,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                shipping_address TEXT NOT NULL DEFAULT '',
                evidence_text TEXT NOT NULL DEFAULT '',
                signature_obtained INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_shipments_checkout_order_id
                ON shipments(checkout_order_id);
            CREATE INDEX IF NOT EXISTS idx_shipments_paypal_capture_id
                ON shipments(paypal_capture_id);
            """
        )
        for product in CATALOGUE:
            price_cents = int((product["price"] * 100))
            conn.execute(
                """
                INSERT OR REPLACE INTO products (sku, name, description, price_cents)
                VALUES (?, ?, ?, ?)
                """,
                (product["sku"], product["name"], product["description"], price_cents),
            )
        conn.commit()
    finally:
        conn.close()


def get_catalogue() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT sku, name, description, price_cents FROM products ORDER BY sku"
        ).fetchall()
        return [
            {
                "sku": row["sku"],
                "name": row["name"],
                "description": row["description"],
                "price": _money(row["price_cents"]),
                "currency": "USD",
            }
            for row in rows
        ]
    finally:
        conn.close()


def create_order(items: list[dict], currency: str = "USD") -> dict:
    """Create a persistent order with server-calculated totals.

    items: list of {"sku": str, "quantity": int}
    """
    order_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    if currency != "USD":
        raise ValueError(f"Unsupported currency: {currency}; only USD is supported.")

    if not items:
        raise ValueError("Order must contain at least one item.")

    conn = _connect()
    try:
        catalogue = {}
        for row in conn.execute("SELECT sku, price_cents FROM products"):
            catalogue[row["sku"]] = row["price_cents"]

        total_cents = 0
        order_items = []
        for item in items:
            sku = str(item["sku"]).strip()
            quantity = item["quantity"]
            if isinstance(quantity, bool) or not isinstance(quantity, int):
                raise ValueError(f"Quantity must be a positive integer for SKU: {sku}")
            if sku not in catalogue:
                raise ValueError(f"Unknown product SKU: {sku}")
            if quantity <= 0:
                raise ValueError(f"Quantity must be positive for SKU: {sku}")
            unit_price_cents = catalogue[sku]
            line_total_cents = unit_price_cents * quantity
            total_cents += line_total_cents
            product_row = conn.execute(
                "SELECT name FROM products WHERE sku = ?", (sku,)
            ).fetchone()
            order_items.append(
                {
                    "id": str(uuid.uuid4()),
                    "order_id": order_id,
                    "product_sku": sku,
                    "product_name": product_row["name"],
                    "quantity": quantity,
                    "unit_price_cents": unit_price_cents,
                    "line_total_cents": line_total_cents,
                }
            )

        conn.execute(
            """
            INSERT INTO orders (id, paypal_order_id, paypal_capture_id, payment_status,
                                currency, total_cents, created_at, updated_at)
            VALUES (?, NULL, NULL, 'CREATED', ?, ?, ?, ?)
            """,
            (order_id, currency, total_cents, now, now),
        )
        for oi in order_items:
            conn.execute(
                """
                INSERT INTO order_items (id, order_id, product_sku, product_name,
                                         quantity, unit_price_cents, line_total_cents)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    oi["id"],
                    oi["order_id"],
                    oi["product_sku"],
                    oi["product_name"],
                    oi["quantity"],
                    oi["unit_price_cents"],
                    oi["line_total_cents"],
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return get_order(order_id)


def set_paypal_order_id(order_id: str, paypal_order_id: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE orders
            SET paypal_order_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (paypal_order_id, datetime.now(timezone.utc).isoformat(), order_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_capture(order_id: str, paypal_capture_id: str, payment_status: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE orders
            SET paypal_capture_id = ?, payment_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (paypal_capture_id, payment_status, datetime.now(timezone.utc).isoformat(), order_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_order(order_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            return None
        order = dict(row)
        items = conn.execute(
            """
            SELECT product_sku, product_name, quantity, unit_price_cents, line_total_cents
            FROM order_items WHERE order_id = ?
            """,
            (order_id,),
        ).fetchall()
        order["items"] = [
            {
                "sku": item["product_sku"],
                "name": item["product_name"],
                "quantity": item["quantity"],
                "unit_price": _money(item["unit_price_cents"]),
                "line_total": _money(item["line_total_cents"]),
            }
            for item in items
        ]
        order["total"] = _money(order["total_cents"])
        del order["total_cents"]
        return order
    finally:
        conn.close()


def list_orders() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC"
        ).fetchall()
        orders = []
        for row in rows:
            order = dict(row)
            order["total"] = _money(order["total_cents"])
            del order["total_cents"]
            orders.append(order)
        return orders
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Shipment manifest persistence
# These tables are completely separate from checkout orders and order_items.
# ---------------------------------------------------------------------------

def _validate_manifest_items(items: list) -> None:
    """Raise ValueError for any item that fails field-level validation."""
    if not items:
        raise ValueError("A manifest must contain at least one item.")
    for idx, item in enumerate(items):
        description = str(item.get("description", "")).strip()
        if not description:
            raise ValueError(f"Item {idx}: description must not be blank.")

        qty = item.get("expected_qty")
        if isinstance(qty, bool) or not isinstance(qty, int):
            raise ValueError(
                f"Item {idx}: expected_qty must be a positive integer, got {type(qty).__name__}."
            )
        if qty <= 0:
            raise ValueError(
                f"Item {idx}: expected_qty must be a positive integer, got {qty}."
            )

        uvc = item.get("unit_value_cents")
        if uvc is not None:
            if isinstance(uvc, bool) or not isinstance(uvc, int):
                raise ValueError(
                    f"Item {idx}: unit_value_cents must be a non-negative integer, "
                    f"got {type(uvc).__name__}."
                )
            if uvc < 0:
                raise ValueError(
                    f"Item {idx}: unit_value_cents must be non-negative, got {uvc}."
                )


def _compute_manifest_hash(
    manifest_id: str, shipment_order_id: str, items: list[dict]
) -> str:
    """Return a deterministic SHA-256 fingerprint for a finalized manifest.

    The canonical form is a sorted JSON object so that field ordering and
    Python dict insertion order never affect the digest.  The fingerprint
    covers manifest_id and shipment_order_id (binding the hash to this exact
    manifest and the shipment it belongs to) plus a canonically sorted, stable
    representation of all item fields.
    """
    canonical_items = []
    for item in items:
        canonical_items.append({
            "description": item["description"],
            "expected_qty": item["expected_qty"],
            "fragile": bool(item["fragile"]),
            "id": item["id"],
            "manifest_id": item["manifest_id"],
            "sku": item.get("sku"),
            "unit_value_cents": item.get("unit_value_cents"),
        })
    # Sort items by their stable id so identical content always produces the
    # same digest regardless of insertion order.
    canonical_items.sort(key=lambda i: i["id"])
    payload = json.dumps(
        {
            "manifest_id": manifest_id,
            "shipment_order_id": shipment_order_id,
            "items": canonical_items,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_manifest(shipment_order_id: str, items: list[dict], notes: str | None = None) -> dict:
    """Create a DRAFT manifest linked to a shipment evidence record.

    ``shipment_order_id`` must be validated against the shipment data source
    by the caller before this function is invoked.
    ``items`` must be a non-empty list; each dict may contain:
        description (str, required), expected_qty (int > 0, required),
        sku (str, optional), unit_value_cents (int >= 0, optional),
        fragile (bool, optional, default False).
    """
    _validate_manifest_items(items)

    manifest_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO shipment_manifests
                    (id, shipment_order_id, status, notes, manifest_hash, created_at, updated_at)
                VALUES (?, ?, 'DRAFT', ?, NULL, ?, ?)
                """,
                (manifest_id, shipment_order_id, notes or None, now, now),
            )
            for item in items:
                conn.execute(
                    """
                    INSERT INTO manifest_items
                        (id, manifest_id, sku, description, expected_qty,
                         unit_value_cents, fragile)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        manifest_id,
                        str(item["sku"]).strip() if item.get("sku") else None,
                        str(item["description"]).strip(),
                        int(item["expected_qty"]),
                        int(item["unit_value_cents"]) if item.get("unit_value_cents") is not None else None,
                        1 if item.get("fragile") else 0,
                    ),
                )
    finally:
        conn.close()

    return get_manifest(manifest_id)


def get_manifest(manifest_id: str) -> dict | None:
    """Return a manifest with its items, or None if not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM shipment_manifests WHERE id = ?", (manifest_id,)
        ).fetchone()
        if row is None:
            return None
        manifest = dict(row)
        item_rows = conn.execute(
            """
            SELECT id, manifest_id, sku, description, expected_qty,
                   unit_value_cents, fragile
            FROM manifest_items WHERE manifest_id = ?
            ORDER BY rowid
            """,
            (manifest_id,),
        ).fetchall()
        manifest["items"] = [
            {
                "id": r["id"],
                "manifest_id": r["manifest_id"],
                "sku": r["sku"],
                "description": r["description"],
                "expected_qty": r["expected_qty"],
                "unit_value_cents": r["unit_value_cents"],
                "fragile": bool(r["fragile"]),
            }
            for r in item_rows
        ]
        return manifest
    finally:
        conn.close()


def get_manifest_for_shipment(shipment_order_id: str) -> dict | None:
    """Return the most recent manifest for a given shipment_order_id, or None."""
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT id FROM shipment_manifests
            WHERE shipment_order_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (shipment_order_id,),
        ).fetchone()
        if row is None:
            return None
        return get_manifest(row["id"])
    finally:
        conn.close()


def update_manifest(manifest_id: str, items: list[dict], notes: str | None = None) -> dict:
    """Replace all items of a DRAFT manifest.

    Raises ValueError if the manifest does not exist, is not DRAFT, or if
    any item fails validation.
    """
    _validate_manifest_items(items)

    conn = _connect()
    try:
        row = conn.execute(
            "SELECT status FROM shipment_manifests WHERE id = ?", (manifest_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Manifest not found: {manifest_id}")
        if row["status"] != "DRAFT":
            raise ValueError(
                f"Manifest {manifest_id} is {row['status']} and cannot be edited. "
                "Create a new manifest revision instead."
            )

        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute(
                "DELETE FROM manifest_items WHERE manifest_id = ?", (manifest_id,)
            )
            for item in items:
                conn.execute(
                    """
                    INSERT INTO manifest_items
                        (id, manifest_id, sku, description, expected_qty,
                         unit_value_cents, fragile)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        manifest_id,
                        str(item["sku"]).strip() if item.get("sku") else None,
                        str(item["description"]).strip(),
                        int(item["expected_qty"]),
                        int(item["unit_value_cents"]) if item.get("unit_value_cents") is not None else None,
                        1 if item.get("fragile") else 0,
                    ),
                )
            conn.execute(
                "UPDATE shipment_manifests SET notes = ?, updated_at = ? WHERE id = ?",
                (notes or None, now, manifest_id),
            )
    finally:
        conn.close()

    return get_manifest(manifest_id)


def finalize_manifest(manifest_id: str) -> dict:
    """Transition a DRAFT manifest to FINALIZED and compute its hash.

    Raises ValueError if the manifest does not exist, is already FINALIZED,
    or has no items.
    """
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT status FROM shipment_manifests WHERE id = ?", (manifest_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Manifest not found: {manifest_id}")
        if row["status"] == "FINALIZED":
            raise ValueError(f"Manifest {manifest_id} is already FINALIZED.")

        item_count = conn.execute(
            "SELECT COUNT(*) FROM manifest_items WHERE manifest_id = ?", (manifest_id,)
        ).fetchone()[0]
        if item_count == 0:
            raise ValueError("Cannot finalize an empty manifest.")

        # Fetch items for hash computation before the transaction.
        manifest = get_manifest(manifest_id)
        digest = _compute_manifest_hash(
            manifest_id, manifest["shipment_order_id"], manifest["items"]
        )

        now = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute(
                """
                UPDATE shipment_manifests
                SET status = 'FINALIZED', manifest_hash = ?, updated_at = ?
                WHERE id = ?
                """,
                (digest, now, manifest_id),
            )
    finally:
        conn.close()

    return get_manifest(manifest_id)


# ---------------------------------------------------------------------------
# Packing inspection persistence
# ---------------------------------------------------------------------------

def create_inspection(
    manifest_id: str,
    manifest_hash: str,
    model_used: str,
    ai_result: dict,
    photo_records: list[dict],
) -> dict:
    """Persist a completed packing inspection and its photo records.

    photo_records: list of {id, sha256, mime_type, size_bytes}
    Always stores inspection_status = 'PENDING_HUMAN_REVIEW'.
    """
    inspection_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO packing_inspections
                    (id, manifest_id, inspection_status, photo_count,
                     model_used, ai_result, manifest_hash_at_inspection,
                     created_at, updated_at)
                VALUES (?, ?, 'PENDING_HUMAN_REVIEW', ?, ?, ?, ?, ?, ?)
                """,
                (
                    inspection_id,
                    manifest_id,
                    len(photo_records),
                    model_used,
                    json.dumps(ai_result),
                    manifest_hash,
                    now,
                    now,
                ),
            )
            for photo in photo_records:
                conn.execute(
                    """
                    INSERT INTO inspection_photos
                        (id, inspection_id, sha256, mime_type, size_bytes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        photo["id"],
                        inspection_id,
                        photo["sha256"],
                        photo["mime_type"],
                        photo["size_bytes"],
                        now,
                    ),
                )
    finally:
        conn.close()

    return get_inspection(inspection_id)


def get_inspection(inspection_id: str) -> dict | None:
    """Return an inspection record with its photo metadata, or None."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM packing_inspections WHERE id = ?", (inspection_id,)
        ).fetchone()
        if row is None:
            return None
        record = dict(row)
        # Deserialise stored JSON blob.
        if record.get("ai_result"):
            try:
                record["ai_result"] = json.loads(record["ai_result"])
            except (ValueError, TypeError):
                pass
        photo_rows = conn.execute(
            """
            SELECT id, sha256, mime_type, size_bytes, created_at
            FROM inspection_photos WHERE inspection_id = ?
            ORDER BY rowid
            """,
            (inspection_id,),
        ).fetchall()
        record["photos"] = [dict(r) for r in photo_rows]
        return record
    finally:
        conn.close()


def list_inspections_for_manifest(manifest_id: str) -> list[dict]:
    """Return all inspections for a manifest, most recent first."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id FROM packing_inspections
            WHERE manifest_id = ?
            ORDER BY created_at DESC
            """,
            (manifest_id,),
        ).fetchall()
        return [get_inspection(row["id"]) for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Persistent shipment records linked to checkout orders
# ---------------------------------------------------------------------------

def _row_to_shipment(row: sqlite3.Row) -> dict:
    rec = dict(row)
    rec["signature_obtained"] = bool(rec.get("signature_obtained", 0))
    # Make sure transaction_id maps to paypal_capture_id for validator/payload compatibility
    if "transaction_id" not in rec or not rec["transaction_id"]:
        rec["transaction_id"] = rec.get("paypal_capture_id", "")
    return rec


def create_shipment_for_order(
    checkout_order_id: str,
    paypal_order_id: str,
    paypal_capture_id: str,
    amount: Decimal | float | int | str,
    currency: str = "USD",
    shipping_address: str = "",
    carrier: str = "OTHER",
    carrier_name_other: str = "UNASSIGNED",
    tracking_number: str = "",
    status: str = "ON_HOLD",
    evidence_text: str = "",
) -> dict:
    """Create a persistent shipment linked to a verified paid checkout order.

    A verified PayPal payment does not mean goods have physically shipped.
    Defaults to status = 'ON_HOLD', shipped_date = None, tracking_number = '',
    shipping_address = '' (unless supplied), carrier = 'OTHER' and carrier_name_other = 'UNASSIGNED'.

    Strengthened validations:
    - Verifies checkout order is PAID.
    - Verifies supplied paypal_order_id matches stored order's paypal_order_id.
    - Verifies supplied paypal_capture_id matches stored order's paypal_capture_id.
    - Verifies supplied amount and currency match stored checkout order.
    - Rejects if capture ID already belongs to another checkout order.
    """
    conn = _connect()
    try:
        # 1. Fetch and perform ALL checkout order validations FIRST
        order_row = conn.execute(
            "SELECT id, paypal_order_id, paypal_capture_id, payment_status, currency, total_cents FROM orders WHERE id = ?",
            (checkout_order_id,),
        ).fetchone()
        if not order_row:
            raise ValueError(f"Checkout order not found: {checkout_order_id}")
        if order_row["payment_status"] != "PAID":
            raise ValueError(
                f"Cannot create shipment for unpaid order: status is {order_row['payment_status']}"
            )

        # Check if capture ID belongs to another checkout order first
        capture_owner = conn.execute(
            "SELECT * FROM shipments WHERE paypal_capture_id = ?",
            (paypal_capture_id,),
        ).fetchone()
        if capture_owner and capture_owner["checkout_order_id"] != checkout_order_id:
            raise ValueError(
                f"PayPal capture ID '{paypal_capture_id}' already belongs to another checkout order: {capture_owner['checkout_order_id']}"
            )

        # Verify PayPal order ID matches stored order
        if order_row["paypal_order_id"] != paypal_order_id:
            raise ValueError(
                f"PayPal order ID mismatch: expected '{order_row['paypal_order_id']}', got '{paypal_order_id}'"
            )

        # Verify PayPal capture ID matches stored order
        if order_row["paypal_capture_id"] != paypal_capture_id:
            raise ValueError(
                f"PayPal capture ID mismatch: expected '{order_row['paypal_capture_id']}', got '{paypal_capture_id}'"
            )

        # Verify currency matches stored order
        if order_row["currency"] != currency:
            raise ValueError(
                f"Currency mismatch: expected '{order_row['currency']}', got '{currency}'"
            )

        # Verify amount matches stored checkout order total
        stored_total_str = _money(order_row["total_cents"])
        if Decimal(str(amount)) != Decimal(stored_total_str):
            raise ValueError(
                f"Amount mismatch: expected {stored_total_str}, got {amount}"
            )

        # 2. If capture already belongs to this checkout order, return the existing shipment
        if capture_owner:
            return _row_to_shipment(capture_owner)

        # 3. Check if shipment already exists for this checkout order
        existing_order_shipment = conn.execute(
            "SELECT * FROM shipments WHERE checkout_order_id = ?",
            (checkout_order_id,),
        ).fetchone()
        if existing_order_shipment:
            if existing_order_shipment["paypal_capture_id"] != paypal_capture_id:
                raise ValueError(
                    f"Shipment already exists for checkout order '{checkout_order_id}' with different capture ID: {existing_order_shipment['paypal_capture_id']}"
                )
            return _row_to_shipment(existing_order_shipment)

        # 4. Generate unique shipment identifier and insert atomically
        shipment_uuid = str(uuid.uuid4())
        short_id = checkout_order_id.split("-")[0].upper()
        shipment_order_id = f"SHP-{short_id}"

        counter = 1
        test_id = shipment_order_id
        while conn.execute("SELECT 1 FROM shipments WHERE order_id = ?", (test_id,)).fetchone():
            test_id = f"{shipment_order_id}-{counter}"
            counter += 1
        shipment_order_id = test_id

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        today_date = now.strftime("%Y-%m-%d")

        amount_val = float(Decimal(str(amount)))
        if not evidence_text:
            evidence_text = f"Payment captured via PayPal ({paypal_capture_id}). Shipment created on hold awaiting merchant dispatch and carrier assignment."

        # Insert safely under concurrent execution
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO shipments (
                        id, order_id, checkout_order_id, paypal_order_id, paypal_capture_id,
                        tracking_number, carrier, carrier_name_other, status,
                        shipped_date, delivered_date, transaction_date, amount, currency,
                        shipping_address, evidence_text, signature_obtained, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        shipment_uuid,
                        shipment_order_id,
                        checkout_order_id,
                        paypal_order_id,
                        paypal_capture_id,
                        tracking_number,
                        carrier,
                        carrier_name_other,
                        status,
                        today_date,
                        amount_val,
                        currency,
                        shipping_address,
                        evidence_text,
                        now_iso,
                        now_iso,
                    ),
                )
        except sqlite3.IntegrityError:
            # Handle concurrent conflict safely: fetch and return existing row
            existing = conn.execute(
                "SELECT * FROM shipments WHERE checkout_order_id = ? OR paypal_capture_id = ?",
                (checkout_order_id, paypal_capture_id),
            ).fetchone()
            if existing:
                if existing["checkout_order_id"] != checkout_order_id:
                    raise ValueError(
                        f"PayPal capture ID '{paypal_capture_id}' already belongs to another checkout order: {existing['checkout_order_id']}"
                    )
                return _row_to_shipment(existing)
            raise

        return get_shipment_by_order_id(shipment_order_id)
    finally:
        conn.close()


def get_shipment_by_order_id(order_id: str) -> dict | None:
    """Return shipment record by order_id (e.g. 'SHP-XXXX')."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM shipments WHERE order_id = ?", (order_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_shipment(row)
    finally:
        conn.close()


def get_shipment_by_checkout_order_id(checkout_order_id: str) -> dict | None:
    """Return shipment record by checkout_order_id."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM shipments WHERE checkout_order_id = ?", (checkout_order_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_shipment(row)
    finally:
        conn.close()


def list_shipments() -> list[dict]:
    """Return all persistent shipment records, newest first."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM shipments ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_shipment(row) for row in rows]
    finally:
        conn.close()


def update_shipment(order_id: str, **updates) -> dict:
    """Update editable fields on a persistent shipment."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM shipments WHERE order_id = ?", (order_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Shipment not found: {order_id}")

        allowed = {
            "tracking_number",
            "carrier",
            "carrier_name_other",
            "status",
            "shipped_date",
            "delivered_date",
            "amount",
            "currency",
            "shipping_address",
            "evidence_text",
            "signature_obtained",
        }
        set_clauses = []
        vals = []
        for k, v in updates.items():
            if k in allowed:
                set_clauses.append(f"{k} = ?")
                if k == "signature_obtained":
                    vals.append(1 if v else 0)
                else:
                    vals.append(v)

        if not set_clauses:
            return _row_to_shipment(row)

        set_clauses.append("updated_at = ?")
        vals.append(datetime.now(timezone.utc).isoformat())
        vals.append(order_id)

        sql = f"UPDATE shipments SET {', '.join(set_clauses)} WHERE order_id = ?"
        with conn:
            conn.execute(sql, tuple(vals))
        return get_shipment_by_order_id(order_id)
    finally:
        conn.close()
