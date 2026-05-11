"""Unit tests for AwsLikeBackend (AWS / Cloudflare R2 / MinIO).

The boto3 client is replaced with a MagicMock so no network calls happen.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# These tests exercise behaviour that relies on botocore's exception types.
# Skip the whole module when the optional SDK is not installed (e.g. on a
# Local-only deployment).
boto3 = pytest.importorskip("boto3")
botocore_exceptions = pytest.importorskip("botocore.exceptions")
ClientError = botocore_exceptions.ClientError

from app.config import (  # noqa: E402
    AwsStorageConfig,
    CloudflareStorageConfig,
    MinioStorageConfig,
)
from app.core.storage_backend import StorageError  # noqa: E402
from app.core.storage_backends import aws_like as aws_like_mod  # noqa: E402
from app.core.storage_backends.aws_like import AwsLikeBackend  # noqa: E402


# ---------- helpers ----------


@pytest.fixture
def fake_client(monkeypatch):
    """Patch _build_client to return a fresh MagicMock for each test."""
    client = MagicMock()
    monkeypatch.setattr(aws_like_mod, "_build_client", lambda **kw: client)
    return client


def _minio_cfg(**overrides) -> MinioStorageConfig:
    base = dict(
        endpoint="http://localhost:9000",
        bucket="b",
        access_key="k",
        secret_key="s",
        prefix="p/",
        public_base_url="",
        secure=False,
    )
    base.update(overrides)
    return MinioStorageConfig(**base)


def _aws_cfg(**overrides) -> AwsStorageConfig:
    base = dict(
        region="us-east-1",
        bucket="b",
        access_key_id="k",
        access_key_secret="s",
        prefix="",
        public_base_url="",
    )
    base.update(overrides)
    return AwsStorageConfig(**base)


def _r2_cfg(**overrides) -> CloudflareStorageConfig:
    base = dict(
        account_id="acct123",
        bucket="b",
        access_key_id="k",
        access_key_secret="s",
        prefix="",
        public_base_url="",
    )
    base.update(overrides)
    return CloudflareStorageConfig(**base)


# ---------- save ----------


def test_save_applies_prefix_and_forwards_content_type(fake_client):
    backend = AwsLikeBackend.from_minio(_minio_cfg(prefix="p/"))
    backend.save("foo.jpg", b"BYTES", content_type="image/jpeg")
    fake_client.put_object.assert_called_once_with(
        Bucket="b", Key="p/foo.jpg", Body=b"BYTES", ContentType="image/jpeg"
    )


def test_save_defaults_content_type_when_missing(fake_client):
    backend = AwsLikeBackend.from_minio(_minio_cfg(prefix=""))
    backend.save("bar.bin", b"x")
    args, kwargs = fake_client.put_object.call_args
    assert kwargs["Key"] == "bar.bin"
    assert kwargs["ContentType"] == "application/octet-stream"


def test_save_wraps_client_error(fake_client):
    fake_client.put_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "nope"}}, "PutObject"
    )
    backend = AwsLikeBackend.from_minio(_minio_cfg())
    with pytest.raises(StorageError) as ei:
        backend.save("x", b"y")
    assert ei.value.provider == "minio"
    assert ei.value.op == "save"
    assert ei.value.key == "x"


# ---------- url ----------


def test_url_uses_public_base_url_when_set(fake_client):
    cfg = _minio_cfg(prefix="p/", public_base_url="https://cdn.example.com/")
    backend = AwsLikeBackend.from_minio(cfg)
    assert backend.url("foo.jpg") == "https://cdn.example.com/p/foo.jpg"
    fake_client.generate_presigned_url.assert_not_called()


def test_url_generates_presigned_when_no_public_base_url(fake_client):
    fake_client.generate_presigned_url.return_value = "https://signed.example/x?sig=abc"
    backend = AwsLikeBackend.from_minio(_minio_cfg(prefix="p/", public_base_url=""))
    result = backend.url("foo.jpg")
    assert result == "https://signed.example/x?sig=abc"
    fake_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "b", "Key": "p/foo.jpg"},
        ExpiresIn=3600,
    )


# ---------- delete ----------


def test_delete_calls_delete_object_with_prefixed_key(fake_client):
    backend = AwsLikeBackend.from_minio(_minio_cfg(prefix="p/"))
    backend.delete("foo.jpg")
    fake_client.delete_object.assert_called_once_with(Bucket="b", Key="p/foo.jpg")


def test_delete_swallows_404_client_error(fake_client):
    fake_client.delete_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "x"}}, "DeleteObject"
    )
    backend = AwsLikeBackend.from_minio(_minio_cfg())
    # Must NOT raise.
    backend.delete("missing.jpg")


def test_delete_wraps_other_client_error(fake_client):
    fake_client.delete_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "x"}}, "DeleteObject"
    )
    backend = AwsLikeBackend.from_minio(_minio_cfg())
    with pytest.raises(StorageError):
        backend.delete("x.jpg")


# ---------- exists ----------


def test_exists_returns_true_when_head_succeeds(fake_client):
    fake_client.head_object.return_value = {"ContentLength": 10}
    backend = AwsLikeBackend.from_minio(_minio_cfg())
    assert backend.exists("foo.jpg") is True


def test_exists_returns_false_on_404(fake_client):
    fake_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
    )
    backend = AwsLikeBackend.from_minio(_minio_cfg())
    assert backend.exists("missing.jpg") is False


def test_exists_wraps_unexpected_error(fake_client):
    fake_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "x"}}, "HeadObject"
    )
    backend = AwsLikeBackend.from_minio(_minio_cfg())
    with pytest.raises(StorageError):
        backend.exists("x.jpg")


# ---------- factories pass through correct provider name ----------


def test_provider_name_aws(fake_client):
    backend = AwsLikeBackend.from_aws(_aws_cfg())
    fake_client.put_object.side_effect = ClientError(
        {"Error": {"Code": "Boom"}}, "PutObject"
    )
    with pytest.raises(StorageError) as ei:
        backend.save("k", b"v")
    assert ei.value.provider == "aws"


def test_provider_name_cloudflare(fake_client):
    backend = AwsLikeBackend.from_cloudflare(_r2_cfg())
    fake_client.put_object.side_effect = ClientError(
        {"Error": {"Code": "Boom"}}, "PutObject"
    )
    with pytest.raises(StorageError) as ei:
        backend.save("k", b"v")
    assert ei.value.provider == "cloudflare"
