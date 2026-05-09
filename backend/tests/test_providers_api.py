"""End-to-end tests for /api/providers/* using FastAPI TestClient."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi.testclient import TestClient

from app.main import create_app


def _encrypt(public_pem: str, plaintext: str) -> str:
    pub = serialization.load_pem_public_key(public_pem.encode("ascii"))
    ct = pub.encrypt(
        plaintext.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ct).decode("ascii")


def _resp(json_body, status_code=200, text="ok"):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_body
    m.text = text
    return m


@pytest.fixture
def client(app_config, monkeypatch):
    # Point the master key file at the per-test tmp_path via a config override.
    app = create_app(config=app_config)
    with TestClient(app) as c:
        yield c


def test_list_providers_initial(client):
    r = client.get("/api/providers")
    assert r.status_code == 200
    body = r.json()
    assert len(body["providers"]) == 1
    p = body["providers"][0]
    assert p["id"] == "momo"
    assert p["display_name"] == "MOMO"
    assert p["default_base_url"] == "https://momoapi.top/v1"
    assert p["config"] is None
    assert p["key_count"] == 0
    assert p["credential_fields"][0]["name"] == "api_key"


def test_list_providers_includes_supports_image_input(client):
    """2026-05-09 Addendum (II) — momo opts in to img2img."""
    r = client.get("/api/providers")
    assert r.status_code == 200
    p = r.json()["providers"][0]
    assert p["supports_image_input"] is True


def test_unknown_provider_400(client):
    r = client.get("/api/providers/nope/keys")
    assert r.status_code == 400
    assert r.json()["code"] == "unknown_provider"


def _add_test_key(client: TestClient, monkeypatch) -> str:
    """Helper: encrypt + POST a test key. Returns the new key_id."""
    pem = client.get("/api/config/public-key").json()["public_key_pem"]
    enc = _encrypt(pem, "sk-test-...")

    # Stub upstream so the auto-refresh in add_key returns 1 model.
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **kw: _resp({"data": [{"id": "t8-/gpt-image-2"}]}),
    )

    r = client.post(
        "/api/providers/momo/keys",
        json={"label": "default", "encrypted_credentials": {"api_key": enc}},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["key"]["label"] == "default"
    assert any(m["id"] == "t8-/gpt-image-2" for m in body["models"])
    return body["key"]["id"]


def test_add_key_then_list_keys(client, monkeypatch):
    key_id = _add_test_key(client, monkeypatch)
    r = client.get("/api/providers/momo/keys")
    assert r.status_code == 200
    keys = r.json()["keys"]
    assert len(keys) == 1
    assert keys[0]["id"] == key_id


def test_add_key_invalid_credentials(client, monkeypatch):
    pem = client.get("/api/config/public-key").json()["public_key_pem"]
    # Send the wrong field name.
    enc = _encrypt(pem, "sk-test-...")
    r = client.post(
        "/api/providers/momo/keys",
        json={"label": "x", "encrypted_credentials": {"wrong_name": enc}},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_credentials"
    assert "api_key" in r.json()["missing_fields"]


def test_add_key_refresh_failure_keeps_key_with_error(client, monkeypatch):
    pem = client.get("/api/config/public-key").json()["public_key_pem"]
    enc = _encrypt(pem, "sk-test-...")

    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **kw: _resp({"error": "bad"}, status_code=401, text="unauthorized"),
    )
    r = client.post(
        "/api/providers/momo/keys",
        json={"label": "x", "encrypted_credentials": {"api_key": enc}},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["models"] == []
    assert body["models_refresh_error"] is not None
    # Key persisted in spite of upstream error.
    assert client.get("/api/providers/momo/keys").json()["keys"]


def test_delete_key(client, monkeypatch):
    key_id = _add_test_key(client, monkeypatch)
    r = client.delete(f"/api/providers/momo/keys/{key_id}")
    assert r.status_code == 204
    # Idempotent-ish: second delete returns 404.
    r = client.delete(f"/api/providers/momo/keys/{key_id}")
    assert r.status_code == 404
    assert r.json()["code"] == "key_not_found"


def test_get_models_unknown_key(client):
    r = client.get("/api/providers/momo/models?key_id=nope")
    assert r.status_code == 400
    assert r.json()["code"] == "key_not_found"


def test_refresh_models(client, monkeypatch):
    key_id = _add_test_key(client, monkeypatch)
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **kw: _resp({"data": [{"id": "new-model"}]}),
    )
    r = client.post(
        "/api/providers/momo/models/refresh", json={"key_id": key_id}
    )
    assert r.status_code == 200
    assert [m["id"] for m in r.json()["models"]] == ["new-model"]


def test_refresh_models_upstream_error(client, monkeypatch):
    key_id = _add_test_key(client, monkeypatch)
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **kw: _resp({}, status_code=500, text="server down"),
    )
    r = client.post(
        "/api/providers/momo/models/refresh", json={"key_id": key_id}
    )
    assert r.status_code == 502
    assert r.json()["code"] == "upstream_error"


def test_put_config(client, monkeypatch):
    key_id = _add_test_key(client, monkeypatch)
    r = client.put(
        "/api/providers/momo/config",
        json={"default_key_id": key_id, "default_model": "t8-/gpt-image-2"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["default_key_id"] == key_id
    assert body["default_model"] == "t8-/gpt-image-2"

    # Listing reflects the new config.
    summary = client.get("/api/providers").json()["providers"][0]
    assert summary["config"]["default_key_id"] == key_id


def test_put_config_at_least_one(client):
    r = client.put("/api/providers/momo/config", json={})
    assert r.status_code == 422
