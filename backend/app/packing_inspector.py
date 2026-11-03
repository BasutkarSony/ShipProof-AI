"""AI vision packing inspection service with Gemini primary and OpenAI fallback.

This module isolates external vision-model calls from the deterministic shipment evidence engine (ai_analyzer.py).

Safety guarantees enforced here:
- inspection_status is always PENDING_HUMAN_REVIEW; the model never approves
  or rejects a shipment.
- The prompt explicitly instructs the model not to invent unseen contents, not
  to claim sealed-parcel contents are verified, and to express uncertainty
  explicitly.
- engine_metadata is honestly labelled as an LLM (zero_hallucination: False).
- Provider API keys are read from the environment and are never logged, echoed,
  or included in any response body.
- Provider responses are validated for structure before persistence; malformed
  responses raise RuntimeError.
- manifest_item_id values in Gemini output are cross-checked against the
  actual finalized manifest items before the result is trusted.
"""

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid as _uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Photo storage
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.getenv("PARCELPROOF_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
PHOTO_DIR = DATA_DIR / "inspection_photos"

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
# Optional OpenAI Vision fallback
# ---------------------------------------------------------------------------

def _openai_response_schema() -> dict:
    """Return a strict JSON Schema supported by OpenAI Structured Outputs."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "image_quality",
            "item_checks",
            "additional_observations",
            "human_review_required",
            "inspection_summary",
        ],
        "properties": {
            "image_quality": {
                "type": "object",
                "additionalProperties": False,
                "required": ["overall", "photo_assessments", "limitations"],
                "properties": {
                    "overall": {"type": "string", "enum": sorted(_VALID_QUALITY)},
                    "photo_assessments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["photo_index", "useful", "notes"],
                            "properties": {
                                "photo_index": {"type": "integer"},
                                "useful": {"type": "boolean"},
                                "notes": {"type": "string"},
                            },
                        },
                    },
                    "limitations": {"type": "array", "items": {"type": "string"}},
                },
            },
            "item_checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "manifest_item_id", "sku", "description", "expected_qty",
                        "observed_qty", "result", "visual_evidence", "confidence",
                    ],
                    "properties": {
                        "manifest_item_id": {"type": "string"},
                        "sku": {"type": "string"},
                        "description": {"type": "string"},
                        "expected_qty": {"type": "integer"},
                        "observed_qty": {"type": ["integer", "null"]},
                        "result": {"type": "string", "enum": sorted(_VALID_RESULTS)},
                        "visual_evidence": {"type": "string"},
                        "confidence": {"type": "string", "enum": sorted(_VALID_CONFIDENCE)},
                    },
                },
            },
            "additional_observations": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "possible_extra_items", "visible_product_damage",
                    "visible_packaging_damage", "uncertainty_notes",
                ],
                "properties": {
                    "possible_extra_items": {"type": "array", "items": {"type": "string"}},
                    "visible_product_damage": {"type": "array", "items": {"type": "string"}},
                    "visible_packaging_damage": {"type": "array", "items": {"type": "string"}},
                    "uncertainty_notes": {"type": "array", "items": {"type": "string"}},
                },
            },
            "human_review_required": {"type": "boolean"},
            "inspection_summary": {"type": "string"},
        },
    }


def _run_openai_inspection(manifest: dict, photo_metas: list[dict], api_key: str) -> dict:
    """Run the same manifest/photo task through the optional OpenAI vision fallback."""
    model = os.getenv("OPENAI_VISION_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"
    image_parts = []
    for meta in photo_metas:
        raw = Path(meta["path"]).read_bytes()
        encoded = base64.b64encode(raw).decode("ascii")
        image_parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{meta['mime_type']};base64,{encoded}",
                "detail": "high",
            },
        })

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": _build_prompt(manifest)}] + image_parts,
        }],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "packing_inspection",
                "strict": True,
                "schema": _openai_response_schema(),
            },
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        timeout = max(15, min(int(os.getenv("OPENAI_VISION_TIMEOUT_SECONDS", "90")), 180))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Report the HTTP status only; never echo credentials or provider response bodies.
        raise RuntimeError(
            f"OpenAI vision fallback request failed (HTTP {exc.code})."
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise RuntimeError(
            "OpenAI vision fallback could not complete the request."
        ) from None

    try:
        message = response_data["choices"][0]["message"]
        if message.get("refusal"):
            raise RuntimeError("OpenAI declined the packing inspection request.")
        ai_result = json.loads(message["content"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError(
            "OpenAI vision fallback returned an unexpected response format."
        ) from None

    _validate_ai_result(ai_result, manifest)
    ai_result["human_review_required"] = True

    return {
        "ai_result": ai_result,
        "model_used": model,
        "engine_metadata": {
            "type": "OPENAI_VISION_LLM",
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


def _is_retryable_gemini_error(exc: Exception) -> bool:
    """Identify transient Gemini errors without exposing provider internals."""
    code = getattr(exc, "code", None)
    message = str(exc).upper()
    return code in (429, 500, 502, 503, 504) or any(
        token in message for token in (
            "429", "500", "502", "503", "504",
            "RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL",
        )
    )


def _is_gemini_unavailable(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    message = str(exc).upper()
    return code in (429, 500, 502, 503, 504) or any(
        token in message for token in (
            "429", "500", "502", "503", "504",
            "RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL",
        )
    )


# ---------------------------------------------------------------------------
# Public inspection entry point
# ---------------------------------------------------------------------------

class GeminiUnavailableError(RuntimeError):
    """Raised when no usable vision provider is configured or available."""


def _validate_ai_result(ai_result: dict, manifest: dict) -> None:
    """Validate the structure of a vision-model response before persistence.

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
            f"Vision response is missing required fields: {sorted(missing_top)}"
        )

    # image_quality
    iq = ai_result["image_quality"]
    if not isinstance(iq, dict):
        raise RuntimeError("Vision response: image_quality must be an object.")
    if iq.get("overall") not in _VALID_QUALITY:
        raise RuntimeError(
            f"Vision response: image_quality.overall must be one of "
            f"{sorted(_VALID_QUALITY)}, got {iq.get('overall')!r}."
        )

    # item_checks
    item_checks = ai_result["item_checks"]
    if not isinstance(item_checks, list):
        raise RuntimeError("Vision response: item_checks must be an array.")

    valid_item_ids = {item["id"] for item in manifest.get("items", [])}
    for idx, check in enumerate(item_checks):
        if not isinstance(check, dict):
            raise RuntimeError(f"Vision response: item_checks[{idx}] must be an object.")

        for field in ("manifest_item_id", "description", "result",
                      "visual_evidence", "confidence"):
            if not isinstance(check.get(field), str):
                raise RuntimeError(
                    f"Vision response: item_checks[{idx}].{field} must be a string."
                )

        item_id = check["manifest_item_id"]
        if valid_item_ids and item_id not in valid_item_ids:
            raise RuntimeError(
                f"Vision response: item_checks[{idx}].manifest_item_id "
                f"{item_id!r} does not match any item in the finalized manifest."
            )

        result_val = check["result"]
        if result_val not in _VALID_RESULTS:
            raise RuntimeError(
                f"Vision response: item_checks[{idx}].result must be one of "
                f"{sorted(_VALID_RESULTS)}, got {result_val!r}."
            )

        confidence = check["confidence"]
        if confidence not in _VALID_CONFIDENCE:
            raise RuntimeError(
                f"Vision response: item_checks[{idx}].confidence must be one of "
                f"{sorted(_VALID_CONFIDENCE)}, got {confidence!r}."
            )

        # observed_qty is nullable; None is valid (honest uncertainty).
        # Non-null values must be integers.
        obs_qty = check.get("observed_qty")
        if obs_qty is not None and not isinstance(obs_qty, int):
            raise RuntimeError(
                f"Vision response: item_checks[{idx}].observed_qty must be an "
                f"integer or null, got {type(obs_qty).__name__!r}."
            )

    # additional_observations
    ao = ai_result["additional_observations"]
    if not isinstance(ao, dict):
        raise RuntimeError("Vision response: additional_observations must be an object.")
    for list_field in ("possible_extra_items", "visible_product_damage",
                       "visible_packaging_damage", "uncertainty_notes"):
        if not isinstance(ao.get(list_field), list):
            raise RuntimeError(
                f"Vision response: additional_observations.{list_field} must be an array."
            )


def run_inspection(manifest: dict, photo_metas: list[dict]) -> dict:
    """Run a packing inspection with Gemini primary and optional OpenAI fallback.

    Gemini is attempted first. A single short retry is made for transient server
    errors. If Gemini remains unavailable, OPENAI_API_KEY enables a vision
    fallback. The same photos, manifest prompt, schema checks and human-review
    invariant are applied to both providers.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key:
        if openai_key:
            return _run_openai_inspection(manifest, photo_metas, openai_key)
        raise GeminiUnavailableError(
            "No vision provider is configured. Add GEMINI_API_KEY or OPENAI_API_KEY to backend/.env."
        )

    model = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip() or "gemini-flash-latest"

    # Import here so unit tests can run without a live provider connection.
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
    try:
        from google.genai import errors as genai_errors
    except ImportError:
        genai_errors = None

    response = None
    final_error = None
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_INSPECTION_SCHEMA,
                ),
            )
            break
        except Exception as exc:
            final_error = exc
            if attempt == 0 and _is_retryable_gemini_error(exc):
                time.sleep(0.5)
                continue
            break

    if response is None:
        if final_error and _is_gemini_unavailable(final_error):
            if openai_key:
                try:
                    return _run_openai_inspection(manifest, photo_metas, openai_key)
                except RuntimeError:
                    raise RuntimeError(
                        "Gemini is temporarily unavailable and the configured OpenAI vision fallback also failed. Check the fallback model and API access, then retry."
                    ) from None
            raise GeminiUnavailableError(
                "Gemini service is temporarily unavailable after a retry (503/429). Add OPENAI_API_KEY to enable the optional vision fallback, or retry later."
            ) from None
        raise RuntimeError("Gemini visual inspection API request failed.") from None

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

