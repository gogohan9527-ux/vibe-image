"""Route-level tests for the new PUT /api/prompts/{id} + save_as_template flow."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(app_config, monkeypatch):
    def fake_runner(task, config, cancel_event=None, progress_cb=None, metadata_cb=None):
        for p in (10, 50, 80, 100):
            if progress_cb is not None:
                progress_cb(p)
        out = Path(config.images_dir) / f"generated_{task.task_id}.{task.format}"
        out.write_bytes(b"FAKE")
        return out

    from app.core import task_manager as tm_module
    monkeypatch.setattr(tm_module, "generate_image", fake_runner)

    app = create_app(config=app_config)
    with TestClient(app) as c:
        store = c.app.state.provider_store
        meta = store.add_key("momo", "test", {"api_key": "sk-test-..."})
        store.upsert_config("momo", base_url="https://example.invalid/v1")
        c.test_provider_id = "momo"
        c.test_key_id = meta.id
        yield c


def _task_payload(client, **overrides):
    body = {
        "prompt": "a cat",
        "provider_id": client.test_provider_id,
        "key_id": client.test_key_id,
        "model": "t8-/gpt-image-2",
    }
    body.update(overrides)
    return body


def test_put_prompt_updates_title_and_returns_200(client):
    created = client.post(
        "/api/prompts", json={"title": "old", "prompt": "stuff"}
    ).json()
    pid = created["id"]
    r = client.put(f"/api/prompts/{pid}", json={"title": "new"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "new"
    assert body["prompt"] == "stuff"


def test_put_prompt_updates_prompt(client):
    created = client.post(
        "/api/prompts", json={"title": "n", "prompt": "old"}
    ).json()
    r = client.put(f"/api/prompts/{created['id']}", json={"prompt": "newer"})
    assert r.status_code == 200
    assert r.json()["prompt"] == "newer"


def test_put_prompt_empty_payload_returns_400(client):
    created = client.post(
        "/api/prompts", json={"title": "n", "prompt": "c"}
    ).json()
    r = client.put(f"/api/prompts/{created['id']}", json={})
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "prompt_update_invalid"


def test_put_prompt_not_found_returns_404(client):
    r = client.put("/api/prompts/does_not_exist", json={"title": "x"})
    assert r.status_code == 404
    assert r.json()["code"] == "prompt_not_found"


def test_post_task_with_save_as_template_writes_db(client):
    r = client.post(
        "/api/tasks",
        json=_task_payload(
            client,
            prompt="starry mountain at dusk",
            save_as_template=True,
        ),
    )
    assert r.status_code == 201
    # Saved template appears in list_prompts with auto-derived title.
    r = client.get("/api/prompts")
    assert r.status_code == 200
    prompts = r.json()["prompts"]
    assert any(p["title"] == "starry mountain at dusk" for p in prompts)


def test_post_task_returns_title_field(client):
    r = client.post("/api/tasks", json=_task_payload(client, prompt="a happy fox"))
    assert r.status_code == 201
    task = r.json()["tasks"][0]
    assert "title" in task
    assert task["title"] == "a happy fox"


def test_post_task_title_truncated_at_30(client):
    long_prompt = "x" * 50
    r = client.post("/api/tasks", json=_task_payload(client, prompt=long_prompt))
    assert r.status_code == 201
    task = r.json()["tasks"][0]
    assert task["title"] == "x" * 30
