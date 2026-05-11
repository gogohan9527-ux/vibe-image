"""Aliyun OSS storage adapter.

Uses the official ``oss2`` SDK. All SDK exceptions are wrapped in
:class:`~app.core.storage_backend.StorageError`. ``oss2`` is imported lazily
inside :func:`_build_bucket` so this module imports cleanly even when the
package is not installed.
"""

from __future__ import annotations

from typing import Any, Optional

from ..storage_backend import StorageError
from ...config import AliyunStorageConfig


def _build_bucket(cfg: AliyunStorageConfig) -> Any:
    """Construct an ``oss2.Bucket`` client. Isolated for test monkeypatching."""
    import oss2  # local import: keep optional dep out of module import path

    auth = oss2.Auth(cfg.access_key_id, cfg.access_key_secret)
    return oss2.Bucket(auth, cfg.endpoint, cfg.bucket)


class AliyunOSSBackend:
    """Aliyun OSS-backed storage. Provider name = ``"aliyun"``."""

    def __init__(self, cfg: AliyunStorageConfig) -> None:
        self._prefix = cfg.prefix
        self._public_base_url = cfg.public_base_url
        self._bucket = _build_bucket(cfg)

    def save(
        self,
        key: str,
        content: bytes,
        *,
        content_type: Optional[str] = None,
    ) -> None:
        full_key = self._prefix + key
        headers = {"Content-Type": content_type or "application/octet-stream"}
        try:
            self._bucket.put_object(full_key, content, headers=headers)
        except Exception as exc:  # noqa: BLE001
            if _is_oss_error(exc):
                raise StorageError("aliyun", "save", key, exc) from exc
            raise

    def url(self, key: str) -> str:
        full_key = self._prefix + key
        if self._public_base_url:
            return self._public_base_url.rstrip("/") + "/" + full_key
        try:
            # ``slash_safe=True`` preserves "/" in the key path.
            return self._bucket.sign_url("GET", full_key, 3600, slash_safe=True)
        except Exception as exc:  # noqa: BLE001
            if _is_oss_error(exc):
                raise StorageError("aliyun", "url", key, exc) from exc
            raise

    def delete(self, key: str) -> None:
        full_key = self._prefix + key
        try:
            self._bucket.delete_object(full_key)
        except Exception as exc:  # noqa: BLE001
            if _is_no_such_key(exc):
                return
            if _is_oss_error(exc):
                raise StorageError("aliyun", "delete", key, exc) from exc
            raise

    def exists(self, key: str) -> bool:
        full_key = self._prefix + key
        try:
            return bool(self._bucket.object_exists(full_key))
        except Exception as exc:  # noqa: BLE001
            if _is_oss_error(exc):
                raise StorageError("aliyun", "exists", key, exc) from exc
            raise


# ---------- helpers ----------


def _is_oss_error(exc: BaseException) -> bool:
    try:
        from oss2.exceptions import OssError
    except ImportError:
        return False
    return isinstance(exc, OssError)


def _is_no_such_key(exc: BaseException) -> bool:
    try:
        from oss2.exceptions import NoSuchKey
    except ImportError:
        return False
    return isinstance(exc, NoSuchKey)
