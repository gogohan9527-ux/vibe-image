"""End-to-end route tests using FastAPI TestClient."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.core.storage import Storage
from app.core.task_manager import TaskManager
from app.main import create_app


def _build_app(config: AppConfig, generator_runner):
    """Mirror create_app but inject our generator runner into TaskManager."""
    app = create_app(config=config)
    # The TaskManager is built in lifespan startup. To inject our runner we
    # rely on the TestClient context manager triggering startup; we'll swap
    # the runner before the lifespan starts via a small hack: subclass app and
    # replace lifespan. Simpler: after startup, swap _generator_runner.
    return app


@pytest.fixture
def client(app_config, monkeypatch):
    # Stub out the actual generator: produce a tiny file and call progress callbacks.
    def fake_runner(task, config, cancel_event=None, progress_cb=None, metadata_cb=None):
        for p in (10, 50, 80, 100):
            if cancel_event is not None and cancel_event.is_set():
                from app.errors import CancelledError
                raise CancelledError("cancelled")
            if progress_cb is not None:
                progress_cb(p)
        out = Path(config.images_dir) / f"generated_{task.task_id}.{task.format}"
        out.write_bytes(b"FAKE")
        return out

    # Patch generator at module level so TaskManager picks it up.
    from app.core import task_manager as tm_module
    monkeypatch.setattr(tm_module, "generate_image", fake_runner)

    app = create_app(config=app_config)
    with TestClient(app) as c:
        yield c


def _wait_for_status(client: TestClient, task_id: str, target: str, timeout=5.0) -> Optional[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/tasks/{task_id}")
        if r.status_code == 200 and r.json()["status"] == target:
            return r.json()
        time.sleep(0.05)
    return None


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_create_and_list_task(client):
    r = client.post(
        "/api/tasks",
        json={"prompt": "a cat", "n": 1},
    )
    assert r.status_code == 201
    body = r.json()
    assert len(body["tasks"]) == 1
    task_id = body["tasks"][0]["id"]

    # Active list should eventually be empty after completion.
    history = _wait_for_status(client, task_id, "succeeded")
    assert history is not None
    assert history["image_path"]


def test_create_n_creates_multiple(client):
    r = client.post("/api/tasks", json={"prompt": "many", "n": 3})
    assert r.status_code == 201
    assert len(r.json()["tasks"]) == 3


def test_cancel_pending_task(client, app_config):
    # Lower concurrency to 1 to force queueing.
    client.put("/api/settings", json={"concurrency": 1})
    # Submit two; the second should be queued.
    r1 = client.post("/api/tasks", json={"prompt": "first"})
    r2 = client.post("/api/tasks", json={"prompt": "second"})
    second_id = r2.json()["tasks"][0]["id"]

    # Cancel the second while still pending.
    cancel = client.delete(f"/api/tasks/{second_id}")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"


def test_queue_full_returns_429(client, app_config):
    client.put("/api/settings", json={"concurrency": 1, "queue_cap": 2})
    client.post("/api/tasks", json={"prompt": "a"})
    client.post("/api/tasks", json={"prompt": "b"})
    r = client.post("/api/tasks", json={"prompt": "c"})
    assert r.status_code == 429
    body = r.json()
    assert body["code"] == "queue_full"
    assert body["cap"] == 2


def test_settings_get_and_put(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert "concurrency" in body
    assert "queue_cap" in body

    r = client.put("/api/settings", json={"concurrency": 4, "queue_cap": 50})
    assert r.status_code == 200
    assert r.json()["concurrency"] == 4
    assert r.json()["queue_cap"] == 50


def test_settings_out_of_range(client):
    r = client.put("/api/settings", json={"concurrency": 9999})
    assert r.status_code == 400
    assert r.json()["code"] == "out_of_range"


def test_prompts_crud(client):
    # Lifespan no longer auto-seeds; templates are created via the explicit
    # init script or by saving from the new-task flow.
    r = client.get("/api/prompts")
    assert r.status_code == 200

    # Create one.
    r = client.post(
        "/api/prompts", json={"title": "moonlit forest", "prompt": "moonlit forest with fireflies"}
    )
    assert r.status_code == 201
    new_id = r.json()["id"]

    r = client.get(f"/api/prompts/{new_id}")
    assert r.status_code == 200
    assert r.json()["prompt"] == "moonlit forest with fireflies"

    r = client.delete(f"/api/prompts/{new_id}")
    assert r.status_code == 204

    r = client.get(f"/api/prompts/{new_id}")
    assert r.status_code == 404


def test_history_pagination(client):
    for i in range(3):
        client.post("/api/tasks", json={"prompt": f"history-{i}"})
    # Wait for completion.
    deadline = time.time() + 5
    while time.time() < deadline:
        r = client.get("/api/history?page=1&page_size=10")
        if r.status_code == 200 and r.json()["total"] >= 3:
            break
        time.sleep(0.1)
    r = client.get("/api/history?page=1&page_size=10")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 3
    assert body["page_size"] == 10


def _insert_fake_task(
    client: TestClient,
    *,
    task_id: str,
    status: str,
    image_path: Optional[str],
) -> None:
    """Insert a raw task row via the live storage on the test app."""
    from app.core.storage import utcnow_iso

    storage = client.app.state.storage
    row = {
        "id": task_id,
        "prompt_template_id": None,
        "prompt": "fake history task",
        "model": "t8-/gpt-image-2",
        "size": "1024x1024",
        "quality": "low",
        "format": "jpeg",
        "status": status,
        "progress": 100 if status == "succeeded" else 0,
        "image_path": image_path,
        "error_message": None,
        "created_at": utcnow_iso(),
        "started_at": utcnow_iso(),
        "finished_at": utcnow_iso() if status not in ("queued", "running", "cancelling") else None,
        "priority": 0,
    }
    storage.insert_task(row)


def test_history_delete_succeeded_removes_row_and_file(client, app_config):
    images_dir = Path(app_config.images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    fname = "generated_history_delete_ok.jpeg"
    fpath = images_dir / fname
    fpath.write_bytes(b"FAKEIMG")

    task_id = "11111111-1111-1111-1111-111111111111"
    _insert_fake_task(
        client, task_id=task_id, status="succeeded", image_path=str(fpath)
    )

    r = client.delete(f"/api/history/{task_id}")
    assert r.status_code == 204
    # No body on 204.
    assert r.content == b""

    # DB row gone -> GET task returns 404.
    miss = client.get(f"/api/tasks/{task_id}")
    assert miss.status_code == 404

    # File deleted from disk.
    assert not fpath.exists()


def test_history_delete_unknown_returns_404(client):
    r = client.delete("/api/history/22222222-2222-2222-2222-222222222222")
    assert r.status_code == 404
    assert r.json()["code"] == "task_not_found"


def test_history_delete_active_returns_409(client):
    task_id = "33333333-3333-3333-3333-333333333333"
    _insert_fake_task(client, task_id=task_id, status="running", image_path=None)

    r = client.delete(f"/api/history/{task_id}")
    assert r.status_code == 409
    assert r.json()["code"] == "task_active"

    # Row still present.
    still_there = client.get(f"/api/tasks/{task_id}")
    assert still_there.status_code == 200
    assert still_there.json()["status"] == "running"


def test_history_delete_missing_file_still_succeeds(client, app_config):
    task_id = "44444444-4444-4444-4444-444444444444"
    bogus_path = str(Path(app_config.images_dir) / "does_not_exist.jpeg")
    _insert_fake_task(
        client, task_id=task_id, status="succeeded", image_path=bogus_path
    )

    r = client.delete(f"/api/history/{task_id}")
    assert r.status_code == 204

    miss = client.get(f"/api/tasks/{task_id}")
    assert miss.status_code == 404


def test_static_images_served(client, app_config):
    # Write a tiny fake JPEG into the configured images dir and fetch it.
    images_dir = Path(app_config.images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    fake_bytes = b"\xff\xd8\xff\xe0FAKEJPEG\xff\xd9"
    fname = "generated_test_static.jpeg"
    (images_dir / fname).write_bytes(fake_bytes)

    r = client.get(f"/images/{fname}")
    assert r.status_code == 200
    assert r.content == fake_bytes

    miss = client.get("/images/nonexistent.jpeg")
    assert miss.status_code == 404


def test_config_missing_exits(tmp_path, monkeypatch):
    """If config validation fails, create_app prints and sys.exits."""
    from app import config as cfg_module

    # Point CONFIG_PATH at a non-existent file.
    missing = tmp_path / "nope.yaml"
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", missing)
    cfg_module.reset_config_cache()

    with pytest.raises(SystemExit) as exc_info:
        create_app()
    assert exc_info.value.code == 1
