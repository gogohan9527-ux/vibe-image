"""Tests for DemoAuthMiddleware in demo and normal modes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import (
    AppConfig,
    DefaultsConfig,
    ExecutorConfig,
    PathsConfig,
    ServerConfig,
)
from app.main import create_app


def _make_demo_app(tmp_path, mode: str = "demo") -> AppConfig:
    images_dir = tmp_path / "images"
    prompts_dir = tmp_path / "prompts"
    db_path = tmp_path / "data" / "vibe.db"
    images_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        mode=mode,
        server=ServerConfig(host="127.0.0.1", port=8000, cors_origins=[]),
        executor=ExecutorConfig(
            default_concurrency=2,
            default_queue_size=10,
            max_concurrency=32,
            max_queue_size=10000,
        ),
        paths=PathsConfig(
            images_dir=str(images_dir),
            prompts_dir=str(prompts_dir),
            database_path=str(db_path),
        ),
        defaults=DefaultsConfig(request_timeout_seconds=5),
    )


TEST_TOKEN = "test-demo-token-abc123"


def _client_with_token(tmp_path, mode: str = "demo") -> TestClient:
    """Create a TestClient; if demo mode, manually set app.state.demo_token."""
    config = _make_demo_app(tmp_path, mode=mode)
    app = create_app(config=config)
    # Lifespan does not run in plain TestClient(app) (without context manager).
    # We manually set state so middleware can read it.
    app.state.demo_token = TEST_TOKEN if mode == "demo" else None
    return TestClient(app, raise_server_exceptions=True)


def test_normal_mode_no_token_required(tmp_path):
    """In normal mode, /api/health should return 200 without any token."""
    client = _client_with_token(tmp_path, mode="normal")
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_demo_mode_no_token_returns_401(tmp_path):
    """In demo mode, /api/health without a token returns 401 demo_required."""
    client = _client_with_token(tmp_path, mode="demo")
    r = client.get("/api/health")
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == "demo_required"


def test_demo_mode_correct_header_returns_200(tmp_path):
    """In demo mode, correct X-Demo-Token header allows the request."""
    client = _client_with_token(tmp_path, mode="demo")
    r = client.get("/api/health", headers={"X-Demo-Token": TEST_TOKEN})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_demo_mode_correct_query_param_returns_200(tmp_path):
    """In demo mode, correct ?demo_token= query param allows the request."""
    client = _client_with_token(tmp_path, mode="demo")
    r = client.get(f"/api/health?demo_token={TEST_TOKEN}")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_demo_mode_options_preflight_passthrough(tmp_path):
    """In demo mode, OPTIONS requests (CORS preflight) are not blocked."""
    client = _client_with_token(tmp_path, mode="demo")
    r = client.options("/api/health")
    # Should NOT be 401 — CORS preflight must pass through
    assert r.status_code != 401


def test_demo_mode_non_api_path_passthrough(tmp_path):
    """In demo mode, non-/api/ paths are not blocked by the middleware."""
    config = _make_demo_app(tmp_path, mode="demo")
    app = create_app(config=config)
    app.state.demo_token = TEST_TOKEN
    # Write a tiny fake image file so StaticFiles can serve it
    images_dir = config.images_dir
    fake_image = images_dir / "test.jpg"
    fake_image.write_bytes(b"\xff\xd8\xff\xe0FAKEJPEG\xff\xd9")

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/images/test.jpg")
    # The middleware should not return 401 demo_required for non-/api/ paths.
    # The actual response depends on StaticFiles — could be 200 or 404, but NOT
    # a 401 with code demo_required.
    if r.status_code == 401:
        body = r.json()
        assert body.get("code") != "demo_required", (
            "Middleware should not block non-/api/ paths"
        )
