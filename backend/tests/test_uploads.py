"""Tests for POST /api/uploads/temp (img2img reference uploads)."""

from __future__ import annotations

import struct

import pytest
from fastapi.testclient import TestClient

from app.config import AppConfig, DefaultsConfig
from app.main import create_app


# ---------- helpers ----------


def _png_bytes() -> bytes:
    """Smallest possible valid-ish PNG: signature + IHDR + IDAT + IEND.

    The header sniffer in ``app.api.uploads`` only checks the 8-byte PNG
    signature, so we don't need a fully-decodable file.
    """
    return (
        b"\x89PNG\r\n\x1a\n"  # signature
        + b"\x00" * 32  # padding so we have >= 12 bytes
    )


def _jpeg_bytes() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00" * 32


def _webp_bytes(payload: bytes = b"\x00" * 32) -> bytes:
    body = b"WEBP" + payload
    size = struct.pack("<I", len(body))
    return b"RIFF" + size + body


@pytest.fixture
def upload_client(app_config: AppConfig):
    """A minimal TestClient that exercises uploads only."""
    app = create_app(config=app_config)
    with TestClient(app) as c:
        yield c


# ---------- happy path ----------


def test_upload_png_success(upload_client: TestClient, app_config: AppConfig):
    content = _png_bytes()
    r = upload_client.post(
        "/api/uploads/temp",
        files={"file": ("a.png", content, "image/png")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["input_image_path"].startswith("temp/")
    assert body["input_image_path"].endswith(".png")
    assert body["url"].startswith("/images/temp/")
    assert body["url"].endswith(".png")
    assert body["url"] == f"/images/{body['input_image_path']}"
    # File actually landed on disk under images_temp_dir.
    sha1_name = body["input_image_path"].removeprefix("temp/")
    on_disk = app_config.images_temp_dir / sha1_name
    assert on_disk.exists()
    assert on_disk.read_bytes() == content


def test_upload_jpeg_success(upload_client: TestClient):
    r = upload_client.post(
        "/api/uploads/temp",
        files={"file": ("photo.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["input_image_path"].endswith(".jpg")


def test_upload_webp_success(upload_client: TestClient):
    r = upload_client.post(
        "/api/uploads/temp",
        files={"file": ("x.webp", _webp_bytes(), "image/webp")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["input_image_path"].endswith(".webp")


# ---------- validation failures ----------


def test_upload_text_rejected(upload_client: TestClient):
    r = upload_client.post(
        "/api/uploads/temp",
        files={"file": ("note.txt", b"hello world", "text/plain")},
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["code"] == "invalid_upload"
    assert "reason" in body


def test_upload_bytes_with_image_mime_but_bad_header(upload_client: TestClient):
    """MIME claims png, body isn't — must reject (header check is authoritative)."""
    r = upload_client.post(
        "/api/uploads/temp",
        files={"file": ("a.png", b"not-an-image-actually-just-text-bytes", "image/png")},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_upload"


def test_upload_empty_rejected(upload_client: TestClient):
    r = upload_client.post(
        "/api/uploads/temp",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_upload"


def test_upload_too_large_returns_413(app_config: AppConfig):
    """Set a tiny ``max_upload_bytes`` and verify 413 is raised."""
    config = app_config.model_copy(
        update={"defaults": DefaultsConfig(request_timeout_seconds=5, max_upload_bytes=128)}
    )
    app = create_app(config=config)
    with TestClient(app) as c:
        # 200 bytes of png signature + padding > 128 limit
        big = _png_bytes() + b"\x00" * 200
        r = c.post(
            "/api/uploads/temp",
            files={"file": ("big.png", big, "image/png")},
        )
    assert r.status_code == 413, r.text
    body = r.json()
    assert body["code"] == "upload_too_large"
    assert body["max_bytes"] == 128
    assert body["actual_bytes"] > 128


def test_upload_dedup_same_content(upload_client: TestClient, app_config: AppConfig):
    """Uploading identical bytes twice must yield the same path and one file on disk."""
    content = _png_bytes()
    r1 = upload_client.post(
        "/api/uploads/temp",
        files={"file": ("first.png", content, "image/png")},
    )
    r2 = upload_client.post(
        "/api/uploads/temp",
        files={"file": ("second.png", content, "image/png")},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    p1 = r1.json()["input_image_path"]
    p2 = r2.json()["input_image_path"]
    assert p1 == p2
    # Only one file on disk.
    files = list(app_config.images_temp_dir.iterdir())
    assert len(files) == 1


def test_upload_temp_dir_created(upload_client: TestClient, app_config: AppConfig):
    """``images_temp_dir`` is created at startup (and persists after upload)."""
    assert app_config.images_temp_dir.exists()
    upload_client.post(
        "/api/uploads/temp",
        files={"file": ("a.png", _png_bytes(), "image/png")},
    )
    assert app_config.images_temp_dir.exists()
    assert app_config.images_temp_dir.is_dir()
