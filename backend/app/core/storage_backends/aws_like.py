"""AWS S3 / Cloudflare R2 / MinIO adapter (S3-compatible via boto3).

A single :class:`AwsLikeBackend` covers all three providers; they only differ
in endpoint URL, region, and addressing style. The three ``from_*`` factories
encapsulate those differences so the public factory in
``app.core.storage_backend`` can dispatch on ``cfg.backend`` cleanly.

All SDK exceptions are wrapped in :class:`~app.core.storage_backend.StorageError`.
``boto3`` / ``botocore`` are imported lazily inside ``_build_client`` so this
module imports cleanly even when those packages are not installed (the
``LocalBackend``-only path must keep working).
"""

from __future__ import annotations

from typing import Any, Optional

from ..storage_backend import StorageError
from ...config import (
    AwsStorageConfig,
    CloudflareStorageConfig,
    MinioStorageConfig,
)


def _build_client(
    *,
    endpoint_url: Optional[str],
    region: Optional[str],
    access_key_id: str,
    access_key_secret: str,
    addressing_style: str,
) -> Any:
    """Construct a boto3 S3 client. Isolated for easy monkeypatching in tests."""
    import boto3  # local import: keep optional dep out of module import path
    import botocore.config

    session = boto3.session.Session(
        aws_access_key_id=access_key_id or None,
        aws_secret_access_key=access_key_secret or None,
        region_name=region or None,
    )
    return session.client(
        "s3",
        endpoint_url=endpoint_url or None,
        config=botocore.config.Config(
            signature_version="s3v4",
            s3={"addressing_style": addressing_style},
        ),
    )


class AwsLikeBackend:
    """S3-compatible storage backend (AWS S3, Cloudflare R2, MinIO).

    Use the ``from_aws`` / ``from_cloudflare`` / ``from_minio`` classmethods
    rather than the constructor directly; they encode the per-provider
    quirks (endpoint URL, region default, addressing style, provider name).
    """

    def __init__(
        self,
        *,
        provider: str,
        bucket: str,
        prefix: str,
        public_base_url: str,
        endpoint_url: Optional[str],
        region: Optional[str],
        access_key_id: str,
        access_key_secret: str,
        addressing_style: str,
    ) -> None:
        self._provider = provider
        self._bucket = bucket
        self._prefix = prefix
        self._public_base_url = public_base_url
        self._client = _build_client(
            endpoint_url=endpoint_url,
            region=region,
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            addressing_style=addressing_style,
        )

    # ---------- factories ----------

    @classmethod
    def from_aws(cls, cfg: AwsStorageConfig) -> "AwsLikeBackend":
        return cls(
            provider="aws",
            bucket=cfg.bucket,
            prefix=cfg.prefix,
            public_base_url=cfg.public_base_url,
            endpoint_url=None,
            region=cfg.region or None,
            access_key_id=cfg.access_key_id,
            access_key_secret=cfg.access_key_secret,
            addressing_style="virtual",
        )

    @classmethod
    def from_cloudflare(cls, cfg: CloudflareStorageConfig) -> "AwsLikeBackend":
        endpoint_url = f"https://{cfg.account_id}.r2.cloudflarestorage.com"
        return cls(
            provider="cloudflare",
            bucket=cfg.bucket,
            prefix=cfg.prefix,
            public_base_url=cfg.public_base_url,
            endpoint_url=endpoint_url,
            region="auto",
            access_key_id=cfg.access_key_id,
            access_key_secret=cfg.access_key_secret,
            addressing_style="virtual",
        )

    @classmethod
    def from_minio(cls, cfg: MinioStorageConfig) -> "AwsLikeBackend":
        # cfg.endpoint is caller-provided and is expected to include the scheme
        # (e.g. "http://localhost:9000"). We do not coerce based on cfg.secure.
        return cls(
            provider="minio",
            bucket=cfg.bucket,
            prefix=cfg.prefix,
            public_base_url=cfg.public_base_url,
            endpoint_url=cfg.endpoint,
            region="us-east-1",
            access_key_id=cfg.access_key,
            access_key_secret=cfg.secret_key,
            addressing_style="path",
        )

    # ---------- StorageBackend Protocol ----------

    def save(
        self,
        key: str,
        content: bytes,
        *,
        content_type: Optional[str] = None,
    ) -> None:
        full_key = self._prefix + key
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=full_key,
                Body=content,
                ContentType=content_type or "application/octet-stream",
            )
        except Exception as exc:  # noqa: BLE001 - re-wrapped below after type check
            if _is_boto_error(exc):
                raise StorageError(self._provider, "save", key, exc) from exc
            raise

    def url(self, key: str) -> str:
        full_key = self._prefix + key
        if self._public_base_url:
            return self._public_base_url.rstrip("/") + "/" + full_key
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": full_key},
                ExpiresIn=3600,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_boto_error(exc):
                raise StorageError(self._provider, "url", key, exc) from exc
            raise

    def delete(self, key: str) -> None:
        full_key = self._prefix + key
        try:
            self._client.delete_object(Bucket=self._bucket, Key=full_key)
        except Exception as exc:  # noqa: BLE001
            if _is_boto_error(exc):
                # S3 delete is idempotent; boto3 typically returns 204 even for
                # missing keys. If a ClientError surfaces with a 404-equivalent
                # code, swallow it. Otherwise wrap.
                code = _client_error_code(exc)
                if code in {"404", "NoSuchKey", "NotFound"}:
                    return
                raise StorageError(self._provider, "delete", key, exc) from exc
            raise

    def exists(self, key: str) -> bool:
        full_key = self._prefix + key
        try:
            self._client.head_object(Bucket=self._bucket, Key=full_key)
            return True
        except Exception as exc:  # noqa: BLE001
            if _is_boto_error(exc):
                code = _client_error_code(exc)
                if code in {"404", "NoSuchKey", "NotFound"}:
                    return False
                raise StorageError(self._provider, "exists", key, exc) from exc
            raise


# ---------- helpers ----------


def _is_boto_error(exc: BaseException) -> bool:
    """True if ``exc`` is a botocore/boto3 exception we want to wrap.

    Imported lazily so the module loads without boto3 installed.
    """
    try:
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return False
    return isinstance(exc, (BotoCoreError, ClientError))


def _client_error_code(exc: BaseException) -> Optional[str]:
    """Extract ``response['Error']['Code']`` from a boto3 ``ClientError``.

    Returns ``None`` if ``exc`` is not a ``ClientError`` or the code is absent.
    """
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        return None
    if not isinstance(exc, ClientError):
        return None
    try:
        return str(exc.response["Error"]["Code"])
    except (KeyError, TypeError):
        return None
