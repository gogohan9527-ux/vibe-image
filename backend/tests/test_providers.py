"""Unit tests for the MomoProvider implementation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from app.errors import UpstreamError
from app.providers import PROVIDER_REGISTRY
from app.providers.momo import MomoProvider


def _resp(json_body, status_code=200, text="ok"):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_body
    m.text = text
    return m


def test_registry_has_momo():
    assert "momo" in PROVIDER_REGISTRY
    assert PROVIDER_REGISTRY["momo"].id == "momo"


def test_credential_fields():
    p = MomoProvider()
    assert len(p.credential_fields) == 1
    assert p.credential_fields[0].name == "api_key"
    assert p.credential_fields[0].secret is True


def test_list_models_success(monkeypatch):
    p = MomoProvider()

    captured = {}

    def fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _resp(
            {"data": [{"id": "t8-/gpt-image-2"}, {"id": "dall-e-3"}, {"foo": "bar"}]}
        )

    monkeypatch.setattr(requests, "get", fake_get)
    out = p.list_models(
        creds={"api_key": "sk-test-..."},
        base_url="https://momoapi.top/v1",
        timeout=5,
    )
    assert [m.id for m in out] == ["t8-/gpt-image-2", "dall-e-3"]
    assert captured["url"] == "https://momoapi.top/v1/models"
    assert captured["headers"]["Authorization"] == "Bearer sk-test-..."


def test_list_models_401_raises_upstream(monkeypatch):
    p = MomoProvider()
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **kw: _resp({"error": "unauthorized"}, status_code=401, text="unauth"),
    )
    with pytest.raises(UpstreamError) as exc:
        p.list_models({"api_key": "sk-test-..."}, "https://m.invalid", 5)
    assert "401" in str(exc.value)


def test_list_models_request_exception(monkeypatch):
    p = MomoProvider()

    def boom(*a, **kw):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(requests, "get", boom)
    with pytest.raises(UpstreamError):
        p.list_models({"api_key": "sk-test-..."}, "https://m.invalid", 5)


def test_list_models_missing_api_key():
    p = MomoProvider()
    with pytest.raises(UpstreamError):
        p.list_models({}, "https://m.invalid", 5)


def test_build_request_body_shape():
    from app.core.generator import GeneratorTask

    p = MomoProvider()
    task = GeneratorTask(
        task_id="t-1",
        prompt="a cat",
        model="t8-/gpt-image-2",
        size="1024x1024",
        quality="low",
        format="jpeg",
    )
    call = p.build_request(
        task=task,
        creds={"api_key": "sk-test-..."},
        base_url="https://momoapi.top/v1",
        model="t8-/gpt-image-2",
    )
    assert call.method == "POST"
    assert call.url == "https://momoapi.top/v1/images/generations"
    assert call.headers["Authorization"] == "Bearer sk-test-..."
    assert call.headers["Content-Type"] == "application/json"
    assert call.json_body == {
        "model": "t8-/gpt-image-2",
        "prompt": "a cat",
        "n": 1,
        "size": "1024x1024",
        "quality": "low",
        "format": "jpeg",
    }


def test_parse_response_success():
    p = MomoProvider()
    out = p.parse_response(
        {"data": [{"url": "https://img.invalid/x.jpeg", "revised_prompt": "  cute   "}]}
    )
    assert out.image_url == "https://img.invalid/x.jpeg"
    assert out.revised_prompt == "cute"


def test_parse_response_empty_data_raises():
    p = MomoProvider()
    with pytest.raises(UpstreamError):
        p.parse_response({"data": []})


def test_parse_response_missing_url_raises():
    p = MomoProvider()
    with pytest.raises(UpstreamError):
        p.parse_response({"data": [{"foo": "bar"}]})


# ---------- 2026-05-09 Addendum (II) — img2img ----------


def test_supports_image_input_flag():
    assert MomoProvider().supports_image_input is True


def test_build_image_edit_request_shape(tmp_path):
    from app.core.generator import GeneratorTask, ReferenceImage

    img = tmp_path / "abc123.png"
    img.write_bytes(b"<bytes>")

    task = GeneratorTask(
        task_id="t-2",
        prompt="cute kitten",
        model="t8-/gpt-image-2",
        size="1024x1024",
        quality="low",
        format="jpeg",
        reference_images=[
            ReferenceImage(
                key="temp/abc123.png",
                url="/images/temp/abc123.png",
                filename="abc123.png",
                content_type="image/png",
                content=b"<bytes>",
            )
        ],
    )
    p = MomoProvider()
    call = p.build_image_edit_request(
        task=task,
        creds={"api_key": "sk-test-..."},
        base_url="https://momoapi.top/v1",
        model="t8-/gpt-image-2",
    )

    assert call.method == "POST"
    assert call.url.endswith("/images/edits")
    assert call.url == "https://momoapi.top/v1/images/edits"
    assert call.headers["Authorization"] == "Bearer sk-test-..."
    # multipart: Content-Type is left out so requests can set boundary.
    assert "Content-Type" not in call.headers
    assert call.json_body is None
    assert call.files is not None
    file_tuple = call.files[0][1]
    assert file_tuple[0].endswith(".png")
    assert file_tuple[1] == b"<bytes>"
    assert file_tuple[2] == "image/png"
    assert call.data == {
        "model": "t8-/gpt-image-2",
        "prompt": "cute kitten",
        "size": "1024x1024",
        "n": "1",
    }


def test_build_image_edit_request_jpeg_mime(tmp_path):
    from app.core.generator import GeneratorTask, ReferenceImage

    img = tmp_path / "x.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    task = GeneratorTask(
        task_id="t-3",
        prompt="x",
        model="m",
        size="1024x1024",
        quality="low",
        format="jpeg",
        reference_images=[
            ReferenceImage(
                key="temp/x.jpg",
                url="/images/temp/x.jpg",
                filename="x.jpg",
                content_type="image/jpeg",
                content=b"\xff\xd8\xff",
            )
        ],
    )
    call = MomoProvider().build_image_edit_request(
        task, {"api_key": "k"}, "https://m.invalid/v1", "m"
    )
    assert call.files is not None
    assert call.files[0][1][2] == "image/jpeg"


def test_build_image_edit_request_requires_input_image_path(tmp_path):
    from app.core.generator import GeneratorTask

    task = GeneratorTask(
        task_id="t-4",
        prompt="x",
        model="m",
        size="1024x1024",
        quality="low",
        format="jpeg",
    )
    with pytest.raises(ValueError):
        MomoProvider().build_image_edit_request(
            task, {"api_key": "k"}, "https://m.invalid/v1", "m"
        )
