"""Unit tests for AliyunOSSBackend (mocks oss2.Bucket)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Skip the whole module when the optional SDK is not installed.
oss2 = pytest.importorskip("oss2")
oss2_exceptions = pytest.importorskip("oss2.exceptions")
OssError = oss2_exceptions.OssError
NoSuchKey = oss2_exceptions.NoSuchKey

from app.config import AliyunStorageConfig  # noqa: E402
from app.core.storage_backend import StorageError  # noqa: E402
from app.core.storage_backends import aliyun as aliyun_mod  # noqa: E402
from app.core.storage_backends.aliyun import AliyunOSSBackend  # noqa: E402


@pytest.fixture
def fake_bucket(monkeypatch):
    bucket = MagicMock()
    monkeypatch.setattr(aliyun_mod, "_build_bucket", lambda cfg: bucket)
    return bucket


def _cfg(**overrides) -> AliyunStorageConfig:
    base = dict(
        endpoint="oss-cn-hangzhou.aliyuncs.com",
        bucket="b",
        access_key_id="k",
        access_key_secret="s",
        prefix="p/",
        public_base_url="",
    )
    base.update(overrides)
    return AliyunStorageConfig(**base)


# ---------- save ----------


def test_save_applies_prefix_and_forwards_content_type(fake_bucket):
    backend = AliyunOSSBackend(_cfg(prefix="p/"))
    backend.save("foo.jpg", b"BYTES", content_type="image/jpeg")
    fake_bucket.put_object.assert_called_once_with(
        "p/foo.jpg", b"BYTES", headers={"Content-Type": "image/jpeg"}
    )


def test_save_defaults_content_type(fake_bucket):
    backend = AliyunOSSBackend(_cfg(prefix=""))
    backend.save("bar.bin", b"x")
    _, kwargs = fake_bucket.put_object.call_args
    assert kwargs["headers"]["Content-Type"] == "application/octet-stream"


def test_save_wraps_oss_error(fake_bucket):
    fake_bucket.put_object.side_effect = OssError(
        500, {}, b"{}", {"Message": "boom"}
    )
    backend = AliyunOSSBackend(_cfg())
    with pytest.raises(StorageError) as ei:
        backend.save("k", b"v")
    assert ei.value.provider == "aliyun"
    assert ei.value.op == "save"


# ---------- read ----------


def test_read_applies_prefix(fake_bucket):
    obj = MagicMock()
    obj.read.return_value = b"BYTES"
    fake_bucket.get_object.return_value = obj
    backend = AliyunOSSBackend(_cfg(prefix="p/"))
    assert backend.read("foo.jpg") == b"BYTES"
    fake_bucket.get_object.assert_called_once_with("p/foo.jpg")


# ---------- url ----------


def test_url_uses_public_base_url_when_set(fake_bucket):
    backend = AliyunOSSBackend(_cfg(prefix="p/", public_base_url="https://cdn.example/"))
    assert backend.url("foo.jpg") == "https://cdn.example/p/foo.jpg"
    fake_bucket.sign_url.assert_not_called()


def test_url_generates_presigned_url_when_no_public_base_url(fake_bucket):
    fake_bucket.sign_url.return_value = "https://signed.example/x?sig=abc"
    backend = AliyunOSSBackend(_cfg(prefix="p/", public_base_url=""))
    result = backend.url("foo.jpg")
    assert result == "https://signed.example/x?sig=abc"
    fake_bucket.sign_url.assert_called_once_with("GET", "p/foo.jpg", 3600, slash_safe=True)


# ---------- delete ----------


def test_delete_calls_delete_object(fake_bucket):
    backend = AliyunOSSBackend(_cfg(prefix="p/"))
    backend.delete("foo.jpg")
    fake_bucket.delete_object.assert_called_once_with("p/foo.jpg")


def test_delete_swallows_no_such_key(fake_bucket):
    fake_bucket.delete_object.side_effect = NoSuchKey(404, {}, b"{}", {"Message": "x"})
    backend = AliyunOSSBackend(_cfg())
    # Must not raise.
    backend.delete("missing.jpg")


def test_delete_wraps_other_oss_error(fake_bucket):
    fake_bucket.delete_object.side_effect = OssError(
        500, {}, b"{}", {"Message": "boom"}
    )
    backend = AliyunOSSBackend(_cfg())
    with pytest.raises(StorageError):
        backend.delete("x")


# ---------- exists ----------


def test_exists_returns_true(fake_bucket):
    fake_bucket.object_exists.return_value = True
    backend = AliyunOSSBackend(_cfg(prefix="p/"))
    assert backend.exists("foo.jpg") is True
    fake_bucket.object_exists.assert_called_once_with("p/foo.jpg")


def test_exists_returns_false(fake_bucket):
    fake_bucket.object_exists.return_value = False
    backend = AliyunOSSBackend(_cfg())
    assert backend.exists("missing.jpg") is False


def test_exists_wraps_oss_error(fake_bucket):
    fake_bucket.object_exists.side_effect = OssError(
        500, {}, b"{}", {"Message": "boom"}
    )
    backend = AliyunOSSBackend(_cfg())
    with pytest.raises(StorageError):
        backend.exists("x")
