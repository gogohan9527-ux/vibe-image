"""Tencent Cloud COS storage adapter.

Uses the official ``cos-python-sdk-v5`` package (import name ``qcloud_cos``).
All SDK exceptions are wrapped in
:class:`~app.core.storage_backend.StorageError`. The SDK is imported lazily so
this module imports cleanly when the package is absent.
"""

from __future__ import annotations

from typing import Any, Optional

from ..storage_backend import StorageError
from ...config import TencentStorageConfig


def _build_client(cfg: TencentStorageConfig) -> Any:
    """Construct a ``CosS3Client``. Isolated for test monkeypatching."""
    from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(
        Region=cfg.region,
        SecretId=cfg.secret_id,
        SecretKey=cfg.secret_key,
    )
    return CosS3Client(config)


class TencentCOSBackend:
    """Tencent COS-backed storage. Provider name = ``"tencent"``."""

    def __init__(self, cfg: TencentStorageConfig) -> None:
        self._bucket = cfg.bucket
        self._prefix = cfg.prefix
        self._public_base_url = cfg.public_base_url
        self._client = _build_client(cfg)

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
        except Exception as exc:  # noqa: BLE001
            if _is_cos_error(exc):
                raise StorageError("tencent", "save", key, exc) from exc
            raise

    def read(self, key: str) -> bytes:
        full_key = self._prefix + key
        try:
            result = self._client.get_object(Bucket=self._bucket, Key=full_key)
            return result["Body"].get_raw_stream().read()
        except Exception as exc:  # noqa: BLE001
            if _is_cos_error(exc):
                raise StorageError("tencent", "read", key, exc) from exc
            raise

    def url(self, key: str) -> str:
        full_key = self._prefix + key
        if self._public_base_url:
            return self._public_base_url.rstrip("/") + "/" + full_key
        try:
            return self._client.get_presigned_url(
                Method="GET",
                Bucket=self._bucket,
                Key=full_key,
                Expired=3600,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_cos_error(exc):
                raise StorageError("tencent", "url", key, exc) from exc
            raise

    def delete(self, key: str) -> None:
        full_key = self._prefix + key
        try:
            self._client.delete_object(Bucket=self._bucket, Key=full_key)
        except Exception as exc:  # noqa: BLE001
            # COS delete_object is idempotent for missing keys per the SDK
            # docs; any error that escapes is genuine.
            if _is_cos_error(exc):
                raise StorageError("tencent", "delete", key, exc) from exc
            raise

    def exists(self, key: str) -> bool:
        full_key = self._prefix + key
        try:
            return bool(self._client.object_exists(Bucket=self._bucket, Key=full_key))
        except Exception as exc:  # noqa: BLE001
            if _is_cos_error(exc):
                raise StorageError("tencent", "exists", key, exc) from exc
            raise


# ---------- helpers ----------


def _is_cos_error(exc: BaseException) -> bool:
    try:
        from qcloud_cos.cos_exception import CosClientError, CosServiceError
    except ImportError:
        return False
    return isinstance(exc, (CosClientError, CosServiceError))
