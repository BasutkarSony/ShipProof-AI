"""Gemini-powered packing inspection service.

This module is the only place in the codebase that calls the Gemini API.
It is intentionally isolated from the deterministic shipment evidence engine
(ai_analyzer.py) and must not be imported by it.

Safety guarantees enforced here:
- inspection_status is always PENDING_HUMAN_REVIEW; the model never approves
  or rejects a shipment.
- The prompt explicitly instructs the model not to invent unseen contents, not
  to claim sealed-parcel contents are verified, and to express uncertainty
  explicitly.
- engine_metadata is honestly labelled as an LLM (zero_hallucination: False).
- The GEMINI_API_KEY is read from the environment and is never logged, echoed,
  or included in any response body.
- Gemini responses are validated for structure before persistence; malformed
  responses raise RuntimeError.
- manifest_item_id values in Gemini output are cross-checked against the
  actual finalized manifest items before the result is trusted.
"""

import hashlib
import os
import uuid as _uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Photo storage
# ---------------------------------------------------------------------------

PHOTO_DIR = Path(__file__).resolve().parent.parent / "data" / "inspection_photos"

# Magic-byte signatures for supported image types.
_ALLOWED_SIGNATURES: dict[bytes, str] = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}
_WEBP_RIFF = b"RIFF"
_WEBP_MARKER = b"WEBP"

MAX_PHOTOS_PER_INSPECTION = 5
MAX_PHOTO_BYTES = 10 * 1024 * 1024  # 10 MB


def _detect_mime(data: bytes) -> str | None:
    """Return the MIME type from magic bytes, or None if unsupported."""
    for sig, mime in _ALLOWED_SIGNATURES.items():
        if data[: len(sig)] == sig:
            return mime
    # WebP: bytes 0-3 == RIFF, bytes 8-11 == WEBP
    if len(data) >= 12 and data[:4] == _WEBP_RIFF and data[8:12] == _WEBP_MARKER:
        return "image/webp"
    return None


def validate_and_store_photo(raw_bytes: bytes, original_filename: str) -> dict:
    """Validate image magic bytes, persist to private storage, return metadata.

    Returns a dict with keys:
        id, path (internal Path — never expose in API responses),
        sha256, mime_type, size_bytes.

    Raises ValueError for oversized files, wrong magic bytes, or unsupported
    format.  Only JPEG, PNG, and WebP are accepted; the decision is based
    entirely on the file's magic bytes, not the caller-supplied filename or
    Content-Type header.
    """
    if len(raw_bytes) > MAX_PHOTO_BYTES:
        raise ValueError(
            f"Photo exceeds the 10 MB limit ({len(raw_bytes):,} bytes)."
        )

    mime = _detect_mime(raw_bytes)
    if mime is None:
        raise ValueError(
            f"'{original_filename}' is not a supported image type. "
            "Accepted formats: JPEG, PNG, WebP."
        )

    photo_id = str(_uuid.uuid4())
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[mime]

    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    dest = PHOTO_DIR / f"{photo_id}{ext}"
    dest.write_bytes(raw_bytes)

    digest = hashlib.sha256(raw_bytes).hexdigest()
    return {
        "id": photo_id,
        "path": dest,        # internal use only
        "sha256": digest,
        "mime_type": mime,
        "size_bytes": len(raw_bytes),
    }


# ---------------------------------------------------------------------------
# Gemini inspection schema
# ---------------------------------------------------------------------------

_VALID_RESULTS = {"MATCH", "POSSIBLE_MISSING", "POSSIBLE_EXTRA", "UNCERTAIN", "NOT_VISIBLE"}
_VALID_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}
_VALID_QUALITY = {"GOOD", "FAIR", "POOR", "UNUSABLE"}

_INSPECTION_SCHEMA = {
    "type": "OBJECT",
    "required": [
        "image_quality",
        "item_checks",
        "additional_observations",
        "human_review_required",
        "inspection_summary",
    ],
    "properties": {
        "image_quality": {
            "type": "OBJECT",
            "required": ["overall", "photo_assessments", "limitations"],
            "properties": {
                "overall": {
                    "type": "STRING",
                    "description": "GOOD, FAIR, POOR, or UNUSABLE",
                },
                "photo_assessments": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "required": ["photo_index", "useful", "notes"],
                        "properties": {
                            "photo_index": {"type": "INTEGER"},
                            "useful": {"type": "BOOLEAN"},
                            "notes": {"type": "STRING"},
                        },
                    },
                },
                "limitations": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
            },
        },
        "item_checks": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": [
                    "manifest_item_id",
                    "sku",
                    "description",
                    "expected_qty",
                    "result",
                    "visual_evidence",
                    "confidence",
                ],
                "properties": {
                    "manifest_item_id": {"type": "STRING"},
                    "sku": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "expected_qty": {"type": "INTEGER"},
                    # observed_qty is nullable: null means genuinely uncertain.
                    # The google-genai SDK supports "nullable": true on leaf fields.
                    "observed_qty": {"type": "INTEGER", "nullable": True},
                    "result": {
                        "type": "STRING",
                        "description": (
                            "One of: MATCH, POSSIBLE_MISSING, POSSIBLE_EXTRA, "
                            "UNCERTAIN, NOT_VISIBLE"
                        ),
                    },
                    "visual_evidence": {"type": "STRING"},
                    "confidence": {
                        "type": "STRING",
                        "description": "One of: LOW, MEDIUM, HIGH",
                    },
                },
            },
        },
        "additional_observations": {
            "type": "OBJECT",
            "required": [
                "possible_extra_items",
                "visible_product_damage",
                "visible_packaging_damage",
                "uncertainty_notes",
            ],
            "properties": {
                "possible_extra_items": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "visible_product_damage": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "visible_packaging_damage": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "uncertainty_notes": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
            },
        },
        "human_review_required": {
            "type": "BOOLEAN",
            "description": "Always true. Set to true unconditionally.",
        },
        "inspection_summary": {"type": "STRING"},
    },
}


def _build_prompt(manifest: dict) -> str:
    """Build the structured inspection prompt for Gemini."""
    items_text = "\n".join(
        "  - Item ID: {id} | SKU: {sku} | Description: {desc} | "
        "Expected qty: {qty} | Fragile: {fragile}".format(
            id=item["id"],
            sku=item.get("sku") or "N/A",
            desc=item["description"],
            qty=item["expected_qty"],
            fragile="Yes" if item["fragile"] else "No",
        )
        for item in manifest["items"]
    )
    return (
        "You are a packing verification assistant. Compare the contents visible "
        "in the provided photographs against the declared shipment manifest below.\n\n"
        f"SHIPMENT MANIFEST\n"
        f"  manifest_id     : {manifest['id']}\n"
        f"  fingerprint     : {manifest['manifest_hash']}\n"
        f"  shipment_ref    : {manifest['shipment_order_id']}\n\n"
        f"DECLARED ITEMS:\n{items_text}\n\n"
        "MANDATORY INSTRUCTIONS — follow exactly:\n"
        "1. Only describe what is VISIBLY PRESENT in the photographs. Do not "
        "   invent or assume unseen contents under any circumstances.\n"
        "2. Do NOT claim that the contents of sealed boxes, bags, or parcels "
        "   have been verified. If a container is sealed or closed, state that "
        "   its contents are NOT VISIBLE.\n"
        "3. Do NOT assign a specific SKU to an item unless a label, marking, or "
        "   text visible in the photograph directly supports it.\n"
        "4. Clearly distinguish between 'not visible in these photos' and "
        "   'definitely absent'. Use result=NOT_VISIBLE when an item simply "
        "   cannot be seen; use result=POSSIBLE_MISSING only when photos show "
        "   the box contents fully enough that absence is plausible.\n"
        "5. Set human_review_required to true unconditionally. Never return "
        "   false. Shipment approval or rejection is a human decision.\n"
        "6. Express uncertainty honestly. Use confidence=LOW when unsure.\n"
        "7. Do not state that a shipment is approved, compliant, or ready to "
        "   ship. That determination is made by a human reviewer.\n\n"
        "Return a JSON object matching the supplied schema exactly."
    )


# ---------------------------------------------------------------------------
# Public inspection entry point
# ---------------------------------------------------------------------------

class GeminiUnavailableError(RuntimeError):
    """Raised when the Gemini API key is not configured."""


def _validate_ai_result(ai_result: dict, manifest: dict) -> None:
    """Validate the structure of a Gemini response before persistence.

    Raises RuntimeError with a descriptive message on any violation.
    Does not modify ai_result.
    """
    _REQUIRED_TOP = {
        "image_quality", "item_checks", "additional_observations",
        "human_review_required", "inspection_summary",
    }
    missing_top = _REQUIRED_TOP - ai_result.keys()
    if missing_top:
        raise RuntimeError(
            f"Gemini response is missing required fields: {sorted(missing_top)}"
        )

    # image_quality
    iq = ai_result["image_quality"]
    if not isinstance(iq, dict):
        raise RuntimeError("Gemini response: image_quality must be an object.")
    if iq.get("overall") not in _VALID_QUALITY:
        raise RuntimeError(
            f"Gemini response: image_quality.overall must be one of "
            f"{sorted(_VALID_QUALITY)}, got {iq.get('overall')!r}."
        )

    # item_checks
    item_checks = ai_result["item_checks"]
    if not isinstance(item_checks, list):
        raise RuntimeError("Gemini response: item_checks must be an array.")

    valid_item_ids = {item["id"] for item in manifest.get("items", [])}
    for idx, check in enumerate(item_checks):
        if not isinstance(check, dict):
            raise RuntimeError(f"Gemini response: item_checks[{idx}] must be an object.")

        for field in ("manifest_item_id", "description", "result",
                      "visual_evidence", "confidence"):
            if not isinstance(check.get(field), str):
                raise RuntimeError(
                    f"Gemini response: item_checks[{idx}].{field} must be a string."
                )

        item_id = check["manifest_item_id"]
        if valid_item_ids and item_id not in valid_item_ids:
            raise RuntimeError(
                f"Gemini response: item_checks[{idx}].manifest_item_id "
                f"{item_id!r} does not match any item in the finalized manifest."
            )

        result_val = check["result"]
        if result_val not in _VALID_RESULTS:
            raise RuntimeError(
                f"Gemini response: item_checks[{idx}].result must be one of "
                f"{sorted(_VALID_RESULTS)}, got {result_val!r}."
            )

        confidence = check["confidence"]
        if confidence not in _VALID_CONFIDENCE:
            raise RuntimeError(
                f"Gemini response: item_checks[{idx}].confidence must be one of "
                f"{sorted(_VALID_CONFIDENCE)}, got {confidence!r}."
            )

        # observed_qty is nullable; None is valid (honest uncertainty).
        # Non-null values must be integers.
        obs_qty = check.get("observed_qty")
        if obs_qty is not None and not isinstance(obs_qty, int):
            raise RuntimeError(
                f"Gemini response: item_checks[{idx}].observed_qty must be an "
                f"integer or null, got {type(obs_qty).__name__!r}."
            )

    # additional_observations
    ao = ai_result["additional_observations"]
    if not isinstance(ao, dict):
        raise RuntimeError("Gemini response: additional_observations must be an object.")
    for list_field in ("possible_extra_items", "visible_product_damage",
                       "visible_packaging_damage", "uncertainty_notes"):
        if not isinstance(ao.get(list_field), list):
            raise RuntimeError(
                f"Gemini response: additional_observations.{list_field} must be an array."
            )


def run_inspection(manifest: dict, photo_metas: list[dict]) -> dict:
    """Call Gemini to inspect packing photographs against the manifest.

    Parameters
    ----------
    manifest:
        Finalized manifest dict as returned by store.get_manifest().
    photo_metas:
        List of dicts from validate_and_store_photo(), each containing
        at least 'path' (Path) and 'mime_type' (str).

    Returns
    -------
    dict with keys:
        ai_result (structured inspection JSON),
        model_used (str),
        engine_metadata (dict).

    Raises
    ------
    GeminiUnavailableError  — API key not set.
    RuntimeError            — Gemini API call failed.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiUnavailableError(
            "GEMINI_API_KEY is not set. Add it to backend/.env to enable "
            "Gemini-powered packing inspections."
        )

    model = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip() or "gemini-flash-latest"

    # Import here so the module can be imported without google-genai installed
    # in environments where only tests run (they mock this call).
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    # Build content list: prompt text + one Part per photo.
    prompt_text = _build_prompt(manifest)
    contents: list = [prompt_text]
    for meta in photo_metas:
        raw = Path(meta["path"]).read_bytes()
        contents.append(
            types.Part.from_bytes(data=raw, mime_type=meta["mime_type"])
        )

    import json as _json
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_INSPECTION_SCHEMA,
        ),
    )

    try:
        ai_result = _json.loads(response.text)
    except (ValueError, AttributeError) as exc:
        raise RuntimeError(
            "Gemini returned an unexpected response format."
        ) from exc

    # Validate structure and cross-check manifest item IDs before trusting any value.
    _validate_ai_result(ai_result, manifest)

    # Hard-enforce the safety invariant regardless of what the model returned.
    ai_result["human_review_required"] = True

    return {
        "ai_result": ai_result,
        "model_used": model,
        "engine_metadata": {
            "type": "GEMINI_VISION_LLM",
            "model": model,
            "auditable": False,
            "zero_hallucination": False,
            "disclaimer": (
                "Visual inspection only. Sealed container contents are not "
                "verified. This result requires human review before any "
                "shipment approval or rejection decision is made."
            ),
        },
    }
