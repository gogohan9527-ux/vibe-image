"""Generator success / failure / cancellation tests with mocked HTTP."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from app.core.generator import GeneratorConfig, GeneratorTask, generate_image
from app.errors import CancelledError, ProviderCapabilityError, UpstreamError
from app.providers.momo import MomoProvider


def _gen_config(tmp_path: Path) -> GeneratorConfig:
    return GeneratorConfig(
        provider=MomoProvider(),
        creds={"api_key": "sk-test-..."},
        base_url="https://example.invalid/v1",
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

    def request(method, url, headers, json, timeout):
        return _mock_post_response({"data": [{"url": "https://img.invalid/x.jpeg"}]})

    def get(url, timeout):
        return _mock_get_response(content=b"PNG-PAYLOAD")

    monkeypatch.setattr(requests, "request", request)
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
        "request",
        lambda *a, **kw: _mock_post_response({"error": "bad"}, status_code=400, text="bad request"),
    )
    with pytest.raises(UpstreamError):
        generate_image(_gen_task(), _gen_config(tmp_path))


def test_generate_image_no_url_in_response(tmp_path, monkeypatch):
    monkeypatch.setattr(
        requests, "request", lambda *a, **kw: _mock_post_response({"data": []})
    )
    with pytest.raises(UpstreamError):
        generate_image(_gen_task(), _gen_config(tmp_path))


def test_generate_image_cancelled_before_post(tmp_path, monkeypatch):
    cancel = threading.Event()
    cancel.set()
    # Should raise BEFORE making any request.
    monkeypatch.setattr(
        requests, "request", lambda *a, **kw: pytest.fail("should not be called")
    )
    with pytest.raises(CancelledError):
        generate_image(_gen_task(), _gen_config(tmp_path), cancel_event=cancel)


def test_generate_image_cancelled_between_phases(tmp_path, monkeypatch):
    cancel = threading.Event()

    def request(method, url, headers, json, timeout):
        # Set cancel after the POST returns; the generator should raise before download.
        cancel.set()
        return _mock_post_response({"data": [{"url": "https://img.invalid/x.jpeg"}]})

    monkeypatch.setattr(requests, "request", request)
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **kw: pytest.fail("download should not be called after cancel"),
    )

    with pytest.raises(CancelledError):
        generate_image(_gen_task(), _gen_config(tmp_path), cancel_event=cancel)


# ---------- 2026-05-09 Addendum (II) — img2img dispatch ----------


def _gen_task_with_image(input_path: Path) -> GeneratorTask:
    return GeneratorTask(
        task_id="abc-img",
        prompt="redraw",
        model="t8-/gpt-image-2",
        size="1024x1024",
        quality="low",
        format="jpeg",
        input_image_path=input_path,
    )


def test_generate_image_img2img_success(tmp_path, monkeypatch):
    img = tmp_path / "ref.png"
    img.write_bytes(b"PNGBYTES")
    captured = {}

    def request(**kwargs):
        captured.update(kwargs)
        return _mock_post_response({"data": [{"url": "https://img.invalid/x.jpeg"}]})

    monkeypatch.setattr(requests, "request", request)
    monkeypatch.setattr(
        requests, "get", lambda url, timeout: _mock_get_response(b"OUTPUT")
    )

    out = generate_image(_gen_task_with_image(img), _gen_config(tmp_path))
    assert out.exists()
    assert out.read_bytes() == b"OUTPUT"
    # multipart path: files= present, json= NOT used.
    assert "files" in captured
    assert "json" not in captured or captured.get("json") is None
    assert captured["files"]["image"][1] == b"PNGBYTES"
    assert captured["url"].endswith("/images/edits")
    assert captured["data"]["prompt"] == "redraw"


def test_generate_image_img2img_unsupported_provider_raises(tmp_path, monkeypatch):
    img = tmp_path / "ref.png"
    img.write_bytes(b"PNGBYTES")

    class FakeProvider:
        id = "fake"
        display_name = "Fake"
        default_base_url = "https://fake.invalid/v1"
        supports_image_input = False
        credential_fields: list = []

        def list_models(self, creds, base_url, timeout):  # pragma: no cover
            return []

        def build_request(self, task, creds, base_url, model):  # pragma: no cover
            from app.providers.base import HttpCall

            return HttpCall(url=base_url, method="POST", json_body={})

        def parse_response(self, resp_json):  # pragma: no cover
            from app.providers.base import ParsedResult

            return ParsedResult()

    config = GeneratorConfig(
        provider=FakeProvider(),  # type: ignore[arg-type]
        creds={},
        base_url="https://fake.invalid/v1",
        request_timeout_seconds=5,
        images_dir=tmp_path,
    )

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kw: pytest.fail("must not call upstream when capability missing"),
    )

    with pytest.raises(ProviderCapabilityError) as exc:
        generate_image(_gen_task_with_image(img), config)
    assert exc.value.capability == "image_input"
    assert exc.value.provider_id == "fake"


def test_generate_image_img2img_uses_multipart_not_json(tmp_path, monkeypatch):
    img = tmp_path / "x.jpg"
    img.write_bytes(b"\xff\xd8\xff jpeg")
    seen = {}

    def request(**kwargs):
        seen.update(kwargs)
        return _mock_post_response({"data": [{"url": "https://img.invalid/x.jpeg"}]})

    monkeypatch.setattr(requests, "request", request)
    monkeypatch.setattr(
        requests, "get", lambda url, timeout: _mock_get_response(b"OUT")
    )

    generate_image(_gen_task_with_image(img), _gen_config(tmp_path))
    assert seen.get("json") is None
    assert seen["files"]["image"][2] == "image/jpeg"
