"""Generator success / failure / cancellation tests with mocked HTTP."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from app.core.generator import GeneratorConfig, GeneratorTask, generate_image
from app.errors import CancelledError, UpstreamError


def _gen_config(tmp_path: Path) -> GeneratorConfig:
    return GeneratorConfig(
        base_url="https://example.invalid/v1/images/generations",
        api_key="sk-test",
        request_timeout_seconds=5,
        images_dir=tmp_path,
    )


def _gen_task() -> GeneratorTask:
    return GeneratorTask(
        task_id="abc-123",
        prompt="a cat",
        model="t8-/gpt-image-2",
        size="1024x1024",
        quality="low",
        format="jpeg",
    )


def _mock_post_response(json_body, status_code=200, text="ok"):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_body
    m.text = text
    return m


def _mock_get_response(content=b"\xff\xd8imagebytes", status_code=200):
    m = MagicMock()
    m.status_code = status_code
    m.content = content
    m.text = "ok"
    return m


def test_generate_image_success(tmp_path, monkeypatch):
    progress = []

    def post(url, headers, data, timeout):
        return _mock_post_response({"data": [{"url": "https://img.invalid/x.jpeg"}]})

    def get(url, timeout):
        return _mock_get_response(content=b"PNG-PAYLOAD")

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)

    out = generate_image(
        _gen_task(),
        _gen_config(tmp_path),
        cancel_event=None,
        progress_cb=progress.append,
    )

    assert out.exists()
    assert out.read_bytes() == b"PNG-PAYLOAD"
    assert out.name == "generated_abc-123.jpeg"
    assert 100 in progress
    assert 10 in progress


def test_generate_image_upstream_4xx(tmp_path, monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **kw: _mock_post_response({"error": "bad"}, status_code=400, text="bad request"),
    )
    with pytest.raises(UpstreamError):
        generate_image(_gen_task(), _gen_config(tmp_path))


def test_generate_image_no_url_in_response(tmp_path, monkeypatch):
    monkeypatch.setattr(
        requests, "post", lambda *a, **kw: _mock_post_response({"data": []})
    )
    with pytest.raises(UpstreamError):
        generate_image(_gen_task(), _gen_config(tmp_path))


def test_generate_image_cancelled_before_post(tmp_path, monkeypatch):
    cancel = threading.Event()
    cancel.set()
    # Should raise BEFORE making any request.
    monkeypatch.setattr(
        requests, "post", lambda *a, **kw: pytest.fail("should not be called")
    )
    with pytest.raises(CancelledError):
        generate_image(_gen_task(), _gen_config(tmp_path), cancel_event=cancel)


def test_generate_image_cancelled_between_phases(tmp_path, monkeypatch):
    cancel = threading.Event()

    def post(url, headers, data, timeout):
        # Set cancel after the POST returns; the generator should raise before download.
        cancel.set()
        return _mock_post_response({"data": [{"url": "https://img.invalid/x.jpeg"}]})

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **kw: pytest.fail("download should not be called after cancel"),
    )

    with pytest.raises(CancelledError):
        generate_image(_gen_task(), _gen_config(tmp_path), cancel_event=cancel)
