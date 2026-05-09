"""POST /api/tasks routing: provider/key resolution and error paths."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(app_config, monkeypatch):
    def fake_runner(task, config, cancel_event=None, progress_cb=None, metadata_cb=None):
        out = Path(config.images_dir) / f"generated_{task.task_id}.{task.format}"
        out.write_bytes(b"FAKE")
        return out

    from app.core import task_manager as tm_module
    monkeypatch.setattr(tm_module, "generate_image", fake_runner)
    app = create_app(config=app_config)
    with TestClient(app) as c:
        yield c


def test_task_unknown_provider_400(client):
    r = client.post(
        "/api/tasks",
        json={
            "prompt": "x",
            "provider_id": "not_a_provider",
            "key_id": "anything",
            "model": "t8-/gpt-image-2",
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "unknown_provider"
    assert body["provider_id"] == "not_a_provider"


def test_task_provider_not_configured_400(client):
    r = client.post(
        "/api/tasks",
        json={
            "prompt": "x",
            "provider_id": "momo",
            "key_id": "anything",
            "model": "t8-/gpt-image-2",
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "provider_not_configured"
    assert body["provider_id"] == "momo"


def test_task_key_not_found_400(client):
    # Add a key with one id, then submit with a different one.
    store = client.app.state.provider_store
    store.add_key("momo", "default", {"api_key": "sk-test-..."})
    r = client.post(
        "/api/tasks",
        json={
            "prompt": "x",
            "provider_id": "momo",
            "key_id": "missing-key-id",
            "model": "t8-/gpt-image-2",
        },
    )
    assert r.status_code == 400
    assert r.json()["code"] == "key_not_found"


def test_task_happy_path_carries_provider_key_to_db(client):
    store = client.app.state.provider_store
    meta = store.add_key("momo", "default", {"api_key": "sk-test-..."})
    store.upsert_config("momo", base_url="https://example.invalid/v1")
    r = client.post(
        "/api/tasks",
        json={
            "prompt": "x",
            "provider_id": "momo",
            "key_id": meta.id,
            "model": "t8-/gpt-image-2",
        },
    )
    assert r.status_code == 201
    task = r.json()["tasks"][0]
    assert task["provider_id"] == "momo"
    assert task["key_id"] == meta.id


def test_config_status_normal_no_keys(client):
    r = client.get("/api/config/status")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "normal"
    assert body["any_provider_configured"] is False


def test_config_status_after_add_key(client):
    client.app.state.provider_store.add_key("momo", "default", {"api_key": "sk-test-..."})
    body = client.get("/api/config/status").json()
    assert body["any_provider_configured"] is True


# ---------- 2026-05-09 Addendum (II) — img2img validation ----------


def _seed_momo_key(client: TestClient) -> str:
    store = client.app.state.provider_store
    meta = store.add_key("momo", "default", {"api_key": "sk-test-..."})
    store.upsert_config("momo", base_url="https://example.invalid/v1")
    return meta.id


def _write_temp_image(config, content: bytes = b"PNG-PAYLOAD") -> str:
    """Drop a fake image under ``images_temp_dir`` and return its rel path."""
    config.images_temp_dir.mkdir(parents=True, exist_ok=True)
    name = "fake.png"
    (config.images_temp_dir / name).write_bytes(content)
    return f"temp/{name}"


def test_task_with_input_image_path_success(client):
    key_id = _seed_momo_key(client)
    rel = _write_temp_image(client.app.state.config)
    r = client.post(
        "/api/tasks",
        json={
            "prompt": "x",
            "provider_id": "momo",
            "key_id": key_id,
            "model": "t8-/gpt-image-2",
            "input_image_path": rel,
        },
    )
    assert r.status_code == 201, r.text
    task = r.json()["tasks"][0]
    assert task["input_image_path"] == rel
    assert task["input_image_url"] == f"/images/{rel}"


def test_task_input_image_path_traversal_rejected(client):
    key_id = _seed_momo_key(client)
    r = client.post(
        "/api/tasks",
        json={
            "prompt": "x",
            "provider_id": "momo",
            "key_id": key_id,
            "model": "t8-/gpt-image-2",
            # Anything not starting with "temp/" must be rejected.
            "input_image_path": "../etc/passwd",
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "input_image_not_found"


def test_task_input_image_path_temp_traversal_rejected(client):
    """Even with ``temp/`` prefix, ``..`` segments must escape detection."""
    key_id = _seed_momo_key(client)
    r = client.post(
        "/api/tasks",
        json={
            "prompt": "x",
            "provider_id": "momo",
            "key_id": key_id,
            "model": "t8-/gpt-image-2",
            "input_image_path": "temp/../../escape.txt",
        },
    )
    assert r.status_code == 400
    assert r.json()["code"] == "input_image_not_found"


def test_task_input_image_path_missing_file_rejected(client):
    key_id = _seed_momo_key(client)
    r = client.post(
        "/api/tasks",
        json={
            "prompt": "x",
            "provider_id": "momo",
            "key_id": key_id,
            "model": "t8-/gpt-image-2",
            "input_image_path": "temp/does-not-exist.png",
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "input_image_not_found"
    assert body["input_image_path"] == "temp/does-not-exist.png"


def test_task_input_image_path_capability_unsupported(client, monkeypatch):
    """If the provider's ``supports_image_input`` is False, surfaces 400."""
    key_id = _seed_momo_key(client)
    rel = _write_temp_image(client.app.state.config)

    # Flip the class attribute on the singleton just for this test, then restore.
    from app.providers import PROVIDER_REGISTRY

    momo = PROVIDER_REGISTRY["momo"]
    monkeypatch.setattr(momo, "supports_image_input", False, raising=False)

    r = client.post(
        "/api/tasks",
        json={
            "prompt": "x",
            "provider_id": "momo",
            "key_id": key_id,
            "model": "t8-/gpt-image-2",
            "input_image_path": rel,
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "provider_capability_unsupported"
    assert body["provider_id"] == "momo"
    assert body["capability"] == "image_input"
