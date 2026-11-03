"""Tests for the Gemini packing inspection feature.

Conventions:
- Plain unittest.TestCase, no pytest-specific features.
- Temporary SQLite file via store.DB_PATH (same pattern as other store tests).
- FastAPI handlers called directly (same pattern as test_paypal_checkout.py).
- All Gemini API calls are mocked; no real network traffic is made.
- Photo storage uses a temporary directory so test files are not mixed with
  production data.
"""

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.store as store
from app.store import (
    create_manifest,
    finalize_manifest,
    get_inspection,
    get_manifest,
    init_db,
    list_inspections_for_manifest,
)

# ---------------------------------------------------------------------------
# Synthetic image helpers — real magic bytes, minimal payload.
# ---------------------------------------------------------------------------

def _make_jpeg() -> bytes:
    """Return the smallest valid JPEG-like byte stream (SOI + EOI markers)."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 8 + b"\xff\xd9"


def _make_png() -> bytes:
    """Return a minimal 1×1 px white PNG."""
    # PNG signature
    sig = b"\x89PNG\r\n\x1a\n"

    def _chunk(name: bytes, data: bytes) -> bytes:
        length = len(data).to_bytes(4, "big")
        crc = zlib.crc32(name + data).to_bytes(4, "big")
        return length + name + data + crc

    ihdr = _chunk(b"IHDR", b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00")
    raw_row = b"\x00\xff\xff\xff"  # filter byte + RGB white pixel
    compressed = zlib.compress(raw_row, 9)
    idat = _chunk(b"IDAT", compressed)
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _make_webp() -> bytes:
    """Return minimal WebP magic bytes (RIFF????WEBP prefix)."""
    payload = b"VP8 " + b"\x00" * 20  # minimal VP8 chunk stub
    size = len(payload).to_bytes(4, "little")
    return b"RIFF" + size + b"WEBP" + payload


def _make_pdf() -> bytes:
    """Return PDF magic bytes — should be rejected."""
    return b"%PDF-1.4 fake content"


# ---------------------------------------------------------------------------
# Minimal valid Gemini AI result fixture
# ---------------------------------------------------------------------------

def _ai_result_fixture(item_ids: list[str] | None = None) -> dict:
    item_ids = item_ids or []
    return {
        "image_quality": {
            "overall": "GOOD",
            "photo_assessments": [{"photo_index": 0, "useful": True, "notes": "Clear photo"}],
            "limitations": [],
        },
        "item_checks": [
            {
                "manifest_item_id": iid,
                "sku": "TEST-SKU",
                "description": "Test item",
                "expected_qty": 1,
                "observed_qty": 1,
                "result": "MATCH",
                "visual_evidence": "Item visible in photo 1.",
                "confidence": "HIGH",
            }
            for iid in item_ids
        ],
        "additional_observations": {
            "possible_extra_items": [],
            "visible_product_damage": [],
            "visible_packaging_damage": [],
            "uncertainty_notes": [],
        },
        "human_review_required": True,
        "inspection_summary": "All declared items appear to be present.",
    }


# ---------------------------------------------------------------------------
# Helper to build and finalize a manifest in one call
# ---------------------------------------------------------------------------

def _finalized_manifest(shipment_order_id: str = "ORD-1004") -> dict:
    m = create_manifest(
        shipment_order_id,
        [{"description": "Wireless headphones", "expected_qty": 1, "sku": "WH-001"}],
    )
    return finalize_manifest(m["id"])


# ---------------------------------------------------------------------------
# Packing inspector unit tests (no DB, no HTTP)
# ---------------------------------------------------------------------------

class PhotoValidationTests(unittest.TestCase):
    """Tests for validate_and_store_photo — isolated from DB and HTTP."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        # Redirect the photo storage dir for the duration of each test.
        import app.packing_inspector as pi
        self._original_photo_dir = pi.PHOTO_DIR
        pi.PHOTO_DIR = Path(self._tmpdir.name)
        self._pi = pi

    def tearDown(self):
        self._pi.PHOTO_DIR = self._original_photo_dir
        self._tmpdir.cleanup()

    def test_jpeg_accepted(self):
        result = self._pi.validate_and_store_photo(_make_jpeg(), "photo.jpg")
        self.assertEqual(result["mime_type"], "image/jpeg")
        self.assertIsNotNone(result["sha256"])
        self.assertGreater(result["size_bytes"], 0)
        self.assertTrue(Path(result["path"]).exists())

    def test_png_accepted(self):
        result = self._pi.validate_and_store_photo(_make_png(), "photo.png")
        self.assertEqual(result["mime_type"], "image/png")

    def test_webp_accepted(self):
        result = self._pi.validate_and_store_photo(_make_webp(), "photo.webp")
        self.assertEqual(result["mime_type"], "image/webp")

    def test_pdf_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self._pi.validate_and_store_photo(_make_pdf(), "doc.pdf")
        self.assertIn("not a supported image type", str(ctx.exception))

    def test_arbitrary_bytes_rejected(self):
        with self.assertRaises(ValueError):
            self._pi.validate_and_store_photo(b"\x00\x01\x02\x03" * 100, "data.bin")

    def test_oversized_file_rejected(self):
        big = b"\xff\xd8\xff" + b"\x00" * (10 * 1024 * 1024 + 1)
        with self.assertRaises(ValueError) as ctx:
            self._pi.validate_and_store_photo(big, "huge.jpg")
        self.assertIn("10 MB", str(ctx.exception))

    def test_mime_type_ignores_filename_extension(self):
        # JPEG bytes disguised as .png — should still be accepted as JPEG.
        result = self._pi.validate_and_store_photo(_make_jpeg(), "trick.png")
        self.assertEqual(result["mime_type"], "image/jpeg")

    def test_sha256_is_correct(self):
        data = _make_png()
        result = self._pi.validate_and_store_photo(data, "photo.png")
        expected = hashlib.sha256(data).hexdigest()
        self.assertEqual(result["sha256"], expected)

    def test_server_side_uuid_filename(self):
        r1 = self._pi.validate_and_store_photo(_make_jpeg(), "a.jpg")
        r2 = self._pi.validate_and_store_photo(_make_jpeg(), "a.jpg")
        self.assertNotEqual(r1["id"], r2["id"])
        self.assertNotEqual(r1["path"], r2["path"])

    def test_storage_path_not_original_filename(self):
        result = self._pi.validate_and_store_photo(_make_jpeg(), "../../evil.jpg")
        # The stored path must be inside the photo dir, never an attacker path.
        self.assertEqual(Path(result["path"]).parent, self._pi.PHOTO_DIR)

    def test_gemini_unavailable_error_when_no_api_key(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            with self.assertRaises(self._pi.GeminiUnavailableError):
                self._pi.run_inspection({"id": "x", "manifest_hash": "h",
                                         "shipment_order_id": "o", "items": []}, [])

    def test_human_review_hardcoded_true(self):
        """Even if Gemini somehow returns false, the flag must be forced True."""
        import app.packing_inspector as pi

        # Build a fake Gemini response that claims human_review_required=False.
        fake_response = MagicMock()
        fake_response.text = json.dumps({
            **_ai_result_fixture(),
            "human_review_required": False,  # model tries to bypass safety gate
        })
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response

        mock_types = MagicMock()
        mock_types.GenerateContentConfig.return_value = MagicMock()
        mock_types.Part.from_bytes.return_value = MagicMock()

        mock_genai = MagicMock()
        mock_genai.Client.return_value = mock_client

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=False):
            # Patch the lazy import targets inside run_inspection's local scope.
            with patch("google.genai.Client", return_value=mock_client):
                with patch("google.genai.types.GenerateContentConfig",
                           mock_types.GenerateContentConfig):
                    with patch("google.genai.types.Part", mock_types.Part):
                        # Directly invoke the function after monkey-patching
                        # the internal import at the google.genai level.
                        import google.genai as real_genai
                        import google.genai.types as real_types
                        original_generate = real_genai.Client
                        try:
                            real_genai.Client = lambda **kw: mock_client
                            result = pi.run_inspection(
                                {"id": "m1", "manifest_hash": "abc",
                                 "shipment_order_id": "ORD-1004",
                                 "items": []},
                                [],
                            )
                        finally:
                            real_genai.Client = original_generate
        self.assertTrue(result["ai_result"]["human_review_required"])


# ---------------------------------------------------------------------------
# Store-layer inspection tests
# ---------------------------------------------------------------------------

class InspectionStoreTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._tmp_path = self._tmp.name
        store.DB_PATH = Path(self._tmp_path)
        init_db()

    def tearDown(self):
        store.DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shipproof.db"
        os.unlink(self._tmp_path)

    def _photo_record(self, idx: int = 0) -> dict:
        import uuid
        data = _make_jpeg()
        return {
            "id": str(uuid.uuid4()),
            "sha256": hashlib.sha256(data).hexdigest(),
            "mime_type": "image/jpeg",
            "size_bytes": len(data),
        }

    def test_create_inspection_persists_pending_status(self):
        manifest = _finalized_manifest()
        ai = _ai_result_fixture([manifest["items"][0]["id"]])
        record = store.create_inspection(
            manifest_id=manifest["id"],
            manifest_hash=manifest["manifest_hash"],
            model_used="gemini-flash-latest",
            ai_result=ai,
            photo_records=[self._photo_record()],
        )
        self.assertEqual(record["inspection_status"], "PENDING_HUMAN_REVIEW")
        self.assertEqual(record["manifest_id"], manifest["id"])
        self.assertIsNotNone(record["id"])

    def test_inspection_stores_manifest_hash_snapshot(self):
        manifest = _finalized_manifest()
        ai = _ai_result_fixture()
        record = store.create_inspection(
            manifest_id=manifest["id"],
            manifest_hash=manifest["manifest_hash"],
            model_used="gemini-flash-latest",
            ai_result=ai,
            photo_records=[self._photo_record()],
        )
        self.assertEqual(
            record["manifest_hash_at_inspection"],
            manifest["manifest_hash"],
        )

    def test_inspection_ai_result_round_trips(self):
        manifest = _finalized_manifest()
        ai = _ai_result_fixture()
        record = store.create_inspection(
            manifest_id=manifest["id"],
            manifest_hash=manifest["manifest_hash"],
            model_used="gemini-flash-latest",
            ai_result=ai,
            photo_records=[self._photo_record()],
        )
        self.assertEqual(
            record["ai_result"]["image_quality"]["overall"], "GOOD"
        )

    def test_photo_records_persisted(self):
        manifest = _finalized_manifest()
        photos = [self._photo_record(i) for i in range(3)]
        record = store.create_inspection(
            manifest_id=manifest["id"],
            manifest_hash=manifest["manifest_hash"],
            model_used="gemini-flash-latest",
            ai_result=_ai_result_fixture(),
            photo_records=photos,
        )
        self.assertEqual(record["photo_count"], 3)
        self.assertEqual(len(record["photos"]), 3)
        stored_hashes = {p["sha256"] for p in record["photos"]}
        expected_hashes = {p["sha256"] for p in photos}
        self.assertEqual(stored_hashes, expected_hashes)

    def test_get_inspection_returns_none_for_unknown(self):
        self.assertIsNone(get_inspection("00000000-0000-0000-0000-000000000000"))

    def test_list_inspections_for_manifest(self):
        manifest = _finalized_manifest()
        for _ in range(2):
            store.create_inspection(
                manifest_id=manifest["id"],
                manifest_hash=manifest["manifest_hash"],
                model_used="gemini-flash-latest",
                ai_result=_ai_result_fixture(),
                photo_records=[self._photo_record()],
            )
        results = list_inspections_for_manifest(manifest["id"])
        self.assertEqual(len(results), 2)

    def test_list_inspections_empty_for_unknown_manifest(self):
        self.assertEqual(
            list_inspections_for_manifest("00000000-0000-0000-0000-000000000000"),
            [],
        )

    def test_inspection_status_cannot_be_overridden_to_approved(self):
        """The store layer hardcodes PENDING_HUMAN_REVIEW; no approve path exists."""
        manifest = _finalized_manifest()
        record = store.create_inspection(
            manifest_id=manifest["id"],
            manifest_hash=manifest["manifest_hash"],
            model_used="gemini-flash-latest",
            ai_result=_ai_result_fixture(),
            photo_records=[self._photo_record()],
        )
        # Confirm no update function exists that could set an approved status.
        self.assertFalse(hasattr(store, "approve_inspection"))
        self.assertEqual(record["inspection_status"], "PENDING_HUMAN_REVIEW")

    def test_inspection_tables_created_by_init_db(self):
        conn = store._connect()
        try:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertIn("packing_inspections", tables)
            self.assertIn("inspection_photos", tables)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# FastAPI endpoint handler tests (mocked Gemini, no real API calls)
# ---------------------------------------------------------------------------

class InspectionAPITests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._tmp_path = self._tmp.name
        store.DB_PATH = Path(self._tmp_path)
        init_db()

        # Redirect photo storage to a temp dir.
        import app.packing_inspector as pi
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_photo_dir = pi.PHOTO_DIR
        pi.PHOTO_DIR = Path(self._tmpdir.name)

        from app.main import (
            create_packing_inspection,
            list_manifest_inspections,
            get_inspection_by_id,
            create_shipment_manifest,
            finalize_manifest_by_id,
        )
        self.create_packing_inspection = create_packing_inspection
        self.list_manifest_inspections = list_manifest_inspections
        self.get_inspection_by_id = get_inspection_by_id
        self.create_shipment_manifest = create_shipment_manifest
        self.finalize_manifest_by_id = finalize_manifest_by_id

    def tearDown(self):
        import app.packing_inspector as pi
        pi.PHOTO_DIR = self._original_photo_dir
        store.DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shipproof.db"
        os.unlink(self._tmp_path)
        self._tmpdir.cleanup()

    def _mock_run_inspection(self, manifest, photo_metas):
        """Replacement for run_inspection that never calls Gemini."""
        item_ids = [item["id"] for item in manifest.get("items", [])]
        return {
            "ai_result": _ai_result_fixture(item_ids),
            "model_used": "gemini-flash-latest-mock",
            "engine_metadata": {
                "type": "GEMINI_VISION_LLM",
                "model": "gemini-flash-latest-mock",
                "auditable": False,
                "zero_hallucination": False,
                "disclaimer": "Mock inspection.",
            },
        }

    def _make_upload(self, data: bytes, filename: str = "photo.jpg"):
        """Create a minimal UploadFile-like object for handler tests.

        Supports both upload.read() and upload.read(n) — the latter is used
        by the chunked bounded-read implementation in create_packing_inspection.
        """
        upload = MagicMock()
        upload.filename = filename
        # Simulate a stream: successive read(n) calls return successive chunks,
        # then b"" to signal EOF. read() with no argument returns all data.
        state = {"offset": 0}

        import asyncio

        async def _read(n: int = -1):
            if n == -1 or n is None:
                state["offset"] = len(data)
                return data
            chunk = data[state["offset"]: state["offset"] + n]
            state["offset"] += len(chunk)
            return chunk

        async def _close():
            pass

        upload.read = _read
        upload.close = _close
        return upload

    def _finalized_manifest_via_api(self, shipment_order_id: str = "ORD-1004") -> dict:
        created = self.create_shipment_manifest(
            shipment_order_id,
            {"items": [{"description": "Laptop", "expected_qty": 1, "sku": "LAP-001"}]},
        )
        return self.finalize_manifest_by_id(created["id"])

    def _run_async(self, coro):
        import asyncio

        # Give each synchronous unittest invocation its own event loop.
        # Do not depend on a loop left behind by another test module.
        return asyncio.run(coro)

    # -- POST /api/manifests/{manifest_id}/inspections -----------------------

    def test_create_inspection_returns_pending_status(self):
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_jpeg())]

        with patch("app.main.run_inspection", side_effect=self._mock_run_inspection):
            result = self._run_async(
                self.create_packing_inspection(manifest["id"], photos)
            )

        self.assertEqual(result["inspection_status"], "PENDING_HUMAN_REVIEW")
        self.assertEqual(result["manifest_id"], manifest["id"])
        self.assertIsNotNone(result["inspection_id"])
        self.assertEqual(result["photo_count"], 1)

    def test_create_inspection_snapshot_matches_manifest_hash(self):
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_jpeg())]

        with patch("app.main.run_inspection", side_effect=self._mock_run_inspection):
            result = self._run_async(
                self.create_packing_inspection(manifest["id"], photos)
            )

        self.assertEqual(
            result["manifest_hash_at_inspection"],
            manifest["manifest_hash"],
        )

    def test_create_inspection_no_photos_raises_422(self):
        from fastapi import HTTPException
        manifest = self._finalized_manifest_via_api()

        with self.assertRaises(HTTPException) as ctx:
            self._run_async(self.create_packing_inspection(manifest["id"], []))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_create_inspection_too_many_photos_raises_422(self):
        from fastapi import HTTPException
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_jpeg()) for _ in range(6)]

        with self.assertRaises(HTTPException) as ctx:
            self._run_async(self.create_packing_inspection(manifest["id"], photos))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_create_inspection_invalid_file_type_raises_422(self):
        from fastapi import HTTPException
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_pdf(), "bad.pdf")]

        with self.assertRaises(HTTPException) as ctx:
            self._run_async(self.create_packing_inspection(manifest["id"], photos))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_create_inspection_unknown_manifest_raises_404(self):
        from fastapi import HTTPException
        photos = [self._make_upload(_make_jpeg())]

        with self.assertRaises(HTTPException) as ctx:
            self._run_async(
                self.create_packing_inspection(
                    "00000000-0000-0000-0000-000000000000", photos
                )
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_create_inspection_draft_manifest_raises_422(self):
        from fastapi import HTTPException
        draft = self.create_shipment_manifest(
            "ORD-1004",
            {"items": [{"description": "Item", "expected_qty": 1}]},
        )
        photos = [self._make_upload(_make_jpeg())]

        with self.assertRaises(HTTPException) as ctx:
            self._run_async(
                self.create_packing_inspection(draft["id"], photos)
            )
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("FINALIZED", str(ctx.exception.detail))

    def test_create_inspection_gemini_unavailable_raises_503(self):
        from fastapi import HTTPException
        from app.packing_inspector import GeminiUnavailableError
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_jpeg())]

        with patch(
            "app.main.run_inspection",
            side_effect=GeminiUnavailableError("no key"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                self._run_async(
                    self.create_packing_inspection(manifest["id"], photos)
                )
        self.assertEqual(ctx.exception.status_code, 503)

    def test_run_inspection_server_error_503_raises_gemini_unavailable(self):
        """Simulate google.genai.errors.ServerError(503, '503 UNAVAILABLE') and ensure mapping to GeminiUnavailableError."""
        from app.packing_inspector import run_inspection, GeminiUnavailableError
        from google.genai import errors as genai_errors
        import tempfile

        manifest = {
            "id": "man-1",
            "shipment_order_id": "ORD-TEST-1",
            "manifest_hash": "a" * 64,
            "notes": None,
            "items": [{"id": "item-1", "description": "Test Item", "expected_qty": 1, "sku": "SKU-1", "fragile": False}],
        }
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            tf.write(_make_jpeg())
            tf_path = tf.name

        try:
            photo_metas = [{"id": "p-1", "path": tf_path, "mime_type": "image/jpeg"}]
            with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-api-key"}):
                with patch("google.genai.Client") as mock_client_cls:
                    mock_client = MagicMock()
                    mock_client_cls.return_value = mock_client
                    server_error = genai_errors.ServerError(503, "503 UNAVAILABLE")
                    mock_client.models.generate_content.side_effect = server_error

                    with self.assertRaises(GeminiUnavailableError) as ctx:
                        run_inspection(manifest, photo_metas)

                    self.assertIn("temporarily unavailable", str(ctx.exception))
                    self.assertIn("503 UNAVAILABLE", str(ctx.exception))
                    # Ensure no secret key or stack trace is in message
                    self.assertNotIn("fake-api-key", str(ctx.exception))
        finally:
            if os.path.exists(tf_path):
                os.unlink(tf_path)

    def test_inspection_api_503_server_error_cleans_up_photos(self):
        """Test end-to-end 503 ServerError during inspection API call: returns 503 and deletes uploaded files."""
        from fastapi import HTTPException
        from app.packing_inspector import run_inspection, GeminiUnavailableError, PHOTO_DIR
        from google.genai import errors as genai_errors

        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_jpeg())]

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-api-key"}):
            with patch("google.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value = mock_client
                mock_client.models.generate_content.side_effect = genai_errors.ServerError(503, "503 UNAVAILABLE")

                # Before request, count existing files in storage
                before_files = set(PHOTO_DIR.iterdir()) if PHOTO_DIR.exists() else set()

                with self.assertRaises(HTTPException) as ctx:
                    self._run_async(
                        self.create_packing_inspection(manifest["id"], photos)
                    )

                self.assertEqual(ctx.exception.status_code, 503)
                self.assertIn("temporarily unavailable", str(ctx.exception.detail))
                self.assertNotIn("fake-api-key", str(ctx.exception.detail))

                # After request, verify no leaked photo files remain
                after_files = set(PHOTO_DIR.iterdir()) if PHOTO_DIR.exists() else set()
                new_files = after_files - before_files
                self.assertEqual(len(new_files), 0, "Uploaded photos were not cleaned up on 503")

    def test_create_inspection_gemini_runtime_error_raises_502(self):
        from fastapi import HTTPException
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_jpeg())]

        with patch(
            "app.main.run_inspection",
            side_effect=RuntimeError("Gemini network error"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                self._run_async(
                    self.create_packing_inspection(manifest["id"], photos)
                )
        self.assertEqual(ctx.exception.status_code, 502)

    def test_create_inspection_accepts_multiple_photos(self):
        manifest = self._finalized_manifest_via_api()
        photos = [
            self._make_upload(_make_jpeg(), "photo1.jpg"),
            self._make_upload(_make_png(), "photo2.png"),
            self._make_upload(_make_webp(), "photo3.webp"),
        ]

        with patch("app.main.run_inspection", side_effect=self._mock_run_inspection):
            result = self._run_async(
                self.create_packing_inspection(manifest["id"], photos)
            )

        self.assertEqual(result["photo_count"], 3)
        mime_types = {p["mime_type"] for p in result["photos"]}
        self.assertIn("image/jpeg", mime_types)
        self.assertIn("image/png", mime_types)
        self.assertIn("image/webp", mime_types)

    def test_response_does_not_expose_storage_paths(self):
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_jpeg())]

        with patch("app.main.run_inspection", side_effect=self._mock_run_inspection):
            result = self._run_async(
                self.create_packing_inspection(manifest["id"], photos)
            )

        result_str = json.dumps(result)
        self.assertNotIn("inspection_photos", result_str)
        self.assertNotIn("data\\", result_str)
        self.assertNotIn("data/", result_str)

    def test_photo_sha256_present_in_response(self):
        data = _make_jpeg()
        expected_hash = hashlib.sha256(data).hexdigest()
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(data)]

        with patch("app.main.run_inspection", side_effect=self._mock_run_inspection):
            result = self._run_async(
                self.create_packing_inspection(manifest["id"], photos)
            )

        self.assertEqual(result["photos"][0]["sha256"], expected_hash)

    def test_ai_result_human_review_always_true(self):
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_jpeg())]

        with patch("app.main.run_inspection", side_effect=self._mock_run_inspection):
            result = self._run_async(
                self.create_packing_inspection(manifest["id"], photos)
            )

        self.assertTrue(result["ai_result"]["human_review_required"])

    # -- GET /api/manifests/{manifest_id}/inspections ------------------------

    def test_list_inspections_empty_initially(self):
        manifest = self._finalized_manifest_via_api()
        result = self.list_manifest_inspections(manifest["id"])
        self.assertEqual(result["manifest_id"], manifest["id"])
        self.assertEqual(result["inspections"], [])

    def test_list_inspections_after_creation(self):
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_jpeg())]

        with patch("app.main.run_inspection", side_effect=self._mock_run_inspection):
            self._run_async(
                self.create_packing_inspection(manifest["id"], photos)
            )

        result = self.list_manifest_inspections(manifest["id"])
        self.assertEqual(len(result["inspections"]), 1)
        self.assertEqual(
            result["inspections"][0]["inspection_status"], "PENDING_HUMAN_REVIEW"
        )

    def test_list_inspections_unknown_manifest_raises_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.list_manifest_inspections("00000000-0000-0000-0000-000000000000")
        self.assertEqual(ctx.exception.status_code, 404)

    # -- GET /api/inspections/{inspection_id} --------------------------------

    def test_get_inspection_by_id(self):
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_jpeg())]

        with patch("app.main.run_inspection", side_effect=self._mock_run_inspection):
            created = self._run_async(
                self.create_packing_inspection(manifest["id"], photos)
            )

        fetched = self.get_inspection_by_id(created["inspection_id"])
        self.assertEqual(fetched["inspection_id"], created["inspection_id"])
        self.assertEqual(fetched["inspection_status"], "PENDING_HUMAN_REVIEW")

    def test_get_inspection_unknown_raises_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.get_inspection_by_id("00000000-0000-0000-0000-000000000000")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_get_inspection_manifest_hash_snapshot_preserved(self):
        manifest = self._finalized_manifest_via_api()
        photos = [self._make_upload(_make_jpeg())]

        with patch("app.main.run_inspection", side_effect=self._mock_run_inspection):
            created = self._run_async(
                self.create_packing_inspection(manifest["id"], photos)
            )

        fetched = self.get_inspection_by_id(created["inspection_id"])
        self.assertEqual(
            fetched["manifest_hash_at_inspection"],
            manifest["manifest_hash"],
        )


# ---------------------------------------------------------------------------
# New tests for audit fixes
# ---------------------------------------------------------------------------

class BoundedUploadTests(unittest.TestCase):
    """Tests for the chunked bounded-read upload fix."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._tmp_path = self._tmp.name
        store.DB_PATH = Path(self._tmp_path)
        init_db()

        import app.packing_inspector as pi
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_photo_dir = pi.PHOTO_DIR
        pi.PHOTO_DIR = Path(self._tmpdir.name)

        from app.main import (
            create_packing_inspection,
            create_shipment_manifest,
            finalize_manifest_by_id,
        )
        self.create_packing_inspection = create_packing_inspection
        self.create_shipment_manifest = create_shipment_manifest
        self.finalize_manifest_by_id = finalize_manifest_by_id

    def tearDown(self):
        import app.packing_inspector as pi
        pi.PHOTO_DIR = self._original_photo_dir
        store.DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shipproof.db"
        os.unlink(self._tmp_path)
        self._tmpdir.cleanup()

    def _run_async(self, coro):
        import asyncio

        # Give each synchronous unittest invocation its own event loop.
        # Do not depend on a loop left behind by another test module.
        return asyncio.run(coro)

    def _make_upload_chunked(self, data: bytes, filename: str = "photo.jpg"):
        """Streaming upload that returns data in 64 KB chunks."""
        upload = MagicMock()
        upload.filename = filename
        state = {"offset": 0}

        async def _read(n: int = -1):
            if n == -1 or n is None:
                state["offset"] = len(data)
                return data
            chunk = data[state["offset"]: state["offset"] + n]
            state["offset"] += len(chunk)
            return chunk

        async def _close():
            pass

        upload.read = _read
        upload.close = _close
        return upload

    def _finalized_manifest(self) -> dict:
        created = self.create_shipment_manifest(
            "ORD-1004",
            {"items": [{"description": "Laptop", "expected_qty": 1, "sku": "LAP-001"}]},
        )
        return self.finalize_manifest_by_id(created["id"])

    def test_oversized_file_rejected_during_chunked_read(self):
        """A file exceeding 10 MB must be rejected without buffering all data."""
        from fastapi import HTTPException
        # Construct a file that's just over the limit.
        oversized = b"\xff\xd8\xff" + b"\x00" * (10 * 1024 * 1024 + 1)
        manifest = self._finalized_manifest()
        upload = self._make_upload_chunked(oversized, "huge.jpg")

        with self.assertRaises(HTTPException) as ctx:
            self._run_async(
                self.create_packing_inspection(manifest["id"], [upload])
            )
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("10 MB", str(ctx.exception.detail))

    def test_oversized_file_leaves_no_orphaned_files(self):
        """After an oversized-file rejection, no photo files must remain."""
        from fastapi import HTTPException
        import app.packing_inspector as pi
        oversized = b"\xff\xd8\xff" + b"\x00" * (10 * 1024 * 1024 + 1)
        manifest = self._finalized_manifest()
        upload = self._make_upload_chunked(oversized, "huge.jpg")

        try:
            self._run_async(
                self.create_packing_inspection(manifest["id"], [upload])
            )
        except HTTPException:
            pass

        remaining = list(pi.PHOTO_DIR.iterdir())
        self.assertEqual(remaining, [], f"Orphaned files: {remaining}")


class CleanupOnFailureTests(unittest.TestCase):
    """Tests that photo files are deleted on Gemini or DB failure."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._tmp_path = self._tmp.name
        store.DB_PATH = Path(self._tmp_path)
        init_db()

        import app.packing_inspector as pi
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_photo_dir = pi.PHOTO_DIR
        pi.PHOTO_DIR = Path(self._tmpdir.name)
        self._pi = pi

        from app.main import (
            create_packing_inspection,
            create_shipment_manifest,
            finalize_manifest_by_id,
        )
        self.create_packing_inspection = create_packing_inspection
        self.create_shipment_manifest = create_shipment_manifest
        self.finalize_manifest_by_id = finalize_manifest_by_id

    def tearDown(self):
        self._pi.PHOTO_DIR = self._original_photo_dir
        store.DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shipproof.db"
        os.unlink(self._tmp_path)
        self._tmpdir.cleanup()

    def _run_async(self, coro):
        import asyncio

        # Give each synchronous unittest invocation its own event loop.
        # Do not depend on a loop left behind by another test module.
        return asyncio.run(coro)

    def _finalized_manifest(self) -> dict:
        created = self.create_shipment_manifest(
            "ORD-1004",
            {"items": [{"description": "Laptop", "expected_qty": 1, "sku": "LAP-001"}]},
        )
        return self.finalize_manifest_by_id(created["id"])

    def _make_upload(self, data: bytes, filename: str = "photo.jpg"):
        upload = MagicMock()
        upload.filename = filename
        state = {"offset": 0}

        async def _read(n: int = -1):
            if n == -1 or n is None:
                state["offset"] = len(data)
                return data
            chunk = data[state["offset"]: state["offset"] + n]
            state["offset"] += len(chunk)
            return chunk

        async def _close():
            pass

        upload.read = _read
        upload.close = _close
        return upload

    def test_cleanup_after_gemini_failure(self):
        """Photos stored before Gemini fails must be deleted."""
        from fastapi import HTTPException
        manifest = self._finalized_manifest()
        photos = [self._make_upload(_make_jpeg())]

        with patch(
            "app.main.run_inspection",
            side_effect=RuntimeError("Gemini timeout"),
        ):
            try:
                self._run_async(
                    self.create_packing_inspection(manifest["id"], photos)
                )
            except HTTPException:
                pass

        remaining = list(self._pi.PHOTO_DIR.iterdir())
        self.assertEqual(remaining, [], f"Orphaned files after Gemini failure: {remaining}")

    def test_cleanup_after_gemini_unavailable(self):
        """Photos stored before GeminiUnavailableError must be deleted."""
        from fastapi import HTTPException
        from app.packing_inspector import GeminiUnavailableError
        manifest = self._finalized_manifest()
        photos = [self._make_upload(_make_jpeg())]

        with patch(
            "app.main.run_inspection",
            side_effect=GeminiUnavailableError("no key"),
        ):
            try:
                self._run_async(
                    self.create_packing_inspection(manifest["id"], photos)
                )
            except HTTPException:
                pass

        remaining = list(self._pi.PHOTO_DIR.iterdir())
        self.assertEqual(remaining, [], f"Orphaned files after unavailable error: {remaining}")

    def test_cleanup_after_db_failure(self):
        """Photos stored before a DB write failure must be deleted."""
        from fastapi import HTTPException

        def _mock_run(manifest, photo_metas):
            return {
                "ai_result": _ai_result_fixture([item["id"]
                                                 for item in manifest["items"]]),
                "model_used": "mock",
                "engine_metadata": {"type": "GEMINI_VISION_LLM", "model": "mock",
                                    "auditable": False, "zero_hallucination": False,
                                    "disclaimer": "mock"},
            }

        manifest = self._finalized_manifest()
        photos = [self._make_upload(_make_jpeg())]

        with patch("app.main.run_inspection", side_effect=_mock_run):
            with patch(
                "app.main.create_inspection",
                side_effect=RuntimeError("DB full"),
            ):
                try:
                    self._run_async(
                        self.create_packing_inspection(manifest["id"], photos)
                    )
                except Exception:
                    pass

        remaining = list(self._pi.PHOTO_DIR.iterdir())
        self.assertEqual(remaining, [], f"Orphaned files after DB failure: {remaining}")

    def test_successful_inspection_preserves_files(self):
        """After a fully successful inspection, photo files must NOT be deleted."""
        manifest = self._finalized_manifest()
        photos = [self._make_upload(_make_jpeg())]

        def _mock_run(m, pm):
            return {
                "ai_result": _ai_result_fixture([item["id"] for item in m["items"]]),
                "model_used": "mock",
                "engine_metadata": {"type": "GEMINI_VISION_LLM", "model": "mock",
                                    "auditable": False, "zero_hallucination": False,
                                    "disclaimer": "mock"},
            }

        with patch("app.main.run_inspection", side_effect=_mock_run):
            self._run_async(
                self.create_packing_inspection(manifest["id"], photos)
            )

        remaining = list(self._pi.PHOTO_DIR.iterdir())
        self.assertEqual(len(remaining), 1, "Photo file must be preserved after success.")


class GeminiResponseValidationTests(unittest.TestCase):
    """Tests for the new _validate_ai_result function in packing_inspector.py."""

    def setUp(self):
        import app.packing_inspector as pi
        self._pi = pi
        # Use a real finalized manifest dict (no DB needed for these unit tests).
        self._manifest = {
            "id": "manifest-uuid-1",
            "manifest_hash": "abc123",
            "shipment_order_id": "ORD-1004",
            "items": [{"id": "item-uuid-1", "sku": "LAP-001",
                       "description": "Laptop", "expected_qty": 1, "fragile": False}],
        }

    def _valid_result(self, **overrides) -> dict:
        base = _ai_result_fixture(["item-uuid-1"])
        base.update(overrides)
        return base

    def test_valid_result_passes(self):
        self._pi._validate_ai_result(self._valid_result(), self._manifest)

    def test_missing_top_level_key_raises(self):
        result = self._valid_result()
        del result["image_quality"]
        with self.assertRaises(RuntimeError) as ctx:
            self._pi._validate_ai_result(result, self._manifest)
        self.assertIn("image_quality", str(ctx.exception))

    def test_missing_inspection_summary_raises(self):
        result = self._valid_result()
        del result["inspection_summary"]
        with self.assertRaises(RuntimeError):
            self._pi._validate_ai_result(result, self._manifest)

    def test_invalid_image_quality_overall_raises(self):
        result = self._valid_result()
        result["image_quality"]["overall"] = "EXCELLENT"  # not a valid enum value
        with self.assertRaises(RuntimeError) as ctx:
            self._pi._validate_ai_result(result, self._manifest)
        self.assertIn("overall", str(ctx.exception))

    def test_unknown_manifest_item_id_raises(self):
        result = self._valid_result()
        result["item_checks"][0]["manifest_item_id"] = "hallucinated-uuid"
        with self.assertRaises(RuntimeError) as ctx:
            self._pi._validate_ai_result(result, self._manifest)
        self.assertIn("hallucinated-uuid", str(ctx.exception))

    def test_invalid_result_enum_raises(self):
        result = self._valid_result()
        result["item_checks"][0]["result"] = "APPROVED"  # invalid value
        with self.assertRaises(RuntimeError) as ctx:
            self._pi._validate_ai_result(result, self._manifest)
        self.assertIn("result", str(ctx.exception))

    def test_invalid_confidence_enum_raises(self):
        result = self._valid_result()
        result["item_checks"][0]["confidence"] = "VERY_HIGH"
        with self.assertRaises(RuntimeError) as ctx:
            self._pi._validate_ai_result(result, self._manifest)
        self.assertIn("confidence", str(ctx.exception))

    def test_float_observed_qty_raises(self):
        result = self._valid_result()
        result["item_checks"][0]["observed_qty"] = 1.5
        with self.assertRaises(RuntimeError) as ctx:
            self._pi._validate_ai_result(result, self._manifest)
        self.assertIn("observed_qty", str(ctx.exception))

    def test_null_observed_qty_is_valid(self):
        """None (null) observed_qty must pass — it expresses honest uncertainty."""
        result = self._valid_result()
        result["item_checks"][0]["observed_qty"] = None
        # Should not raise.
        self._pi._validate_ai_result(result, self._manifest)

    def test_missing_additional_observations_list_raises(self):
        result = self._valid_result()
        del result["additional_observations"]["possible_extra_items"]
        with self.assertRaises(RuntimeError) as ctx:
            self._pi._validate_ai_result(result, self._manifest)
        self.assertIn("possible_extra_items", str(ctx.exception))

    def test_item_checks_not_list_raises(self):
        result = self._valid_result()
        result["item_checks"] = "not a list"
        with self.assertRaises(RuntimeError) as ctx:
            self._pi._validate_ai_result(result, self._manifest)
        self.assertIn("item_checks", str(ctx.exception))

    def test_malformed_item_check_entry_raises(self):
        result = self._valid_result()
        result["item_checks"] = ["this should be a dict"]
        with self.assertRaises(RuntimeError):
            self._pi._validate_ai_result(result, self._manifest)

    def test_item_check_non_string_result_field_raises(self):
        result = self._valid_result()
        result["item_checks"][0]["result"] = 42
        with self.assertRaises(RuntimeError) as ctx:
            self._pi._validate_ai_result(result, self._manifest)
        self.assertIn("result", str(ctx.exception))

    def test_empty_manifest_items_skips_id_check(self):
        """If manifest has no items, Gemini returning item checks is not validated."""
        result = self._valid_result()
        result["item_checks"] = []
        manifest_no_items = {**self._manifest, "items": []}
        # Should not raise — an empty manifest may legitimately have no checks.
        self._pi._validate_ai_result(result, manifest_no_items)


if __name__ == "__main__":
    unittest.main()
