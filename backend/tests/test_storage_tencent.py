"""Unit tests for TencentCOSBackend (mocks qcloud_cos CosS3Client)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Skip the whole module when the optional SDK is not installed.
qcloud_cos = pytest.importorskip("qcloud_cos")
cos_exc = pytest.importorskip("qcloud_cos.cos_exception")
CosClientError = cos_exc.CosClientError
CosServiceError = cos_exc.CosServiceError

from app.config import TencentStorageConfig  # noqa: E402
from app.core.storage_backend import StorageError  # noqa: E402
from app.core.storage_backends import tencent as tencent_mod  # noqa: E402
from app.core.storage_backends.tencent import TencentCOSBackend  # noqa: E402


@pytest.fixture
def fake_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(tencent_mod, "_build_client", lambda cfg: client)
    return client


def _cfg(**overrides) -> TencentStorageConfig:
    base = dict(
        region="ap-guangzhou",
        bucket="b-12345",
        secret_id="k",
        secret_key="s",
        prefix="p/",
        public_base_url="",
    )
    base.update(overrides)
    return TencentStorageConfig(**base)


# ---------- save ----------


def test_save_applies_prefix_and_forwards_content_type(fake_client):
    backend = TencentCOSBackend(_cfg(prefix="p/"))
    backend.save("foo.jpg", b"BYTES", content_type="image/jpeg")
    fake_client.put_object.assert_called_once_with(
        Bucket="b-12345",
        Key="p/foo.jpg",
        Body=b"BYTES",
        ContentType="image/jpeg",
    )


def test_save_defaults_content_type(fake_client):
    backend = TencentCOSBackend(_cfg(prefix=""))
    backend.save("bar.bin", b"x")
    _, kwargs = fake_client.put_object.call_args
    assert kwargs["ContentType"] == "application/octet-stream"


def test_save_wraps_cos_error(fake_client):
    fake_client.put_object.side_effect = CosClientError("boom")
    backend = TencentCOSBackend(_cfg())
    with pytest.raises(StorageError) as ei:
        backend.save("k", b"v")
    assert ei.value.provider == "tencent"
    assert ei.value.op == "save"


# ---------- url ----------


def test_url_uses_public_base_url_when_set(fake_client):
    backend = TencentCOSBackend(_cfg(prefix="p/", public_base_url="https://cdn.example/"))
    assert backend.url("foo.jpg") == "https://cdn.example/p/foo.jpg"
    fake_client.get_presigned_url.assert_not_called()


def test_url_generates_presigned_url_when_no_public_base_url(fake_client):
    fake_client.get_presigned_url.return_value = "https://signed.example/x?sig=abc"
    backend = TencentCOSBackend(_cfg(prefix="p/", public_base_url=""))
    assert backend.url("foo.jpg") == "https://signed.example/x?sig=abc"
    fake_client.get_presigned_url.assert_called_once_with(
        Method="GET", Bucket="b-12345", Key="p/foo.jpg", Expired=3600
    )


# ---------- delete ----------


def test_delete_calls_delete_object(fake_client):
    backend = TencentCOSBackend(_cfg(prefix="p/"))
    backend.delete("foo.jpg")
    fake_client.delete_object.assert_called_once_with(Bucket="b-12345", Key="p/foo.jpg")


def test_delete_wraps_cos_error(fake_client):
    fake_client.delete_object.side_effect = CosServiceError(
        "DELETE", '{"Error":{"Code":"AccessDenied"}}', 403
    )
    backend = TencentCOSBackend(_cfg())
    with pytest.raises(StorageError):
        backend.delete("x")


# ---------- exists ----------


def test_exists_returns_true(fake_client):
    fake_client.object_exists.return_value = True
    backend = TencentCOSBackend(_cfg(prefix="p/"))
    assert backend.exists("foo.jpg") is True
    fake_client.object_exists.assert_called_once_with(Bucket="b-12345", Key="p/foo.jpg")


def test_exists_returns_false(fake_client):
    fake_client.object_exists.return_value = False
    backend = TencentCOSBackend(_cfg())
    assert backend.exists("missing.jpg") is False


def test_exists_wraps_cos_error(fake_client):
    fake_client.object_exists.side_effect = CosClientError("boom")
    backend = TencentCOSBackend(_cfg())
    with pytest.raises(StorageError):
        backend.exists("x")
