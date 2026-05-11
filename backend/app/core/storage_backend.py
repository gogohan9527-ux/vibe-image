"""Storage backend abstraction (2026-05-11 Addendum §D).

This module hosts:

* The :class:`StorageBackend` Protocol — the four-method contract every
  concrete backend (local, aliyun, tencent, cloudflare, aws, minio)
  implements.
* :class:`StorageError` — the single exception type adapters raise.
* :class:`LocalBackend` — the historical local-filesystem backend, kept as
  the default so installations that don't configure object storage keep
  behaving exactly as before.
* :func:`build_storage_backend` — factory that maps ``StorageConfig`` →
  concrete instance. Today only ``local`` is wired; the other branches raise
  ``NotImplementedError`` and are filled in by Lane P (Storage Providers).
* :func:`to_url` — a small pure helper that normalises legacy / new
  ``image_path`` strings into URLs for client serialization.

The full contract surface (key naming, URL strategy, error semantics, what
adapter authors must / mustn't do) lives in ``docs/storage-backend-contract.md``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from ..config import StorageConfig


logger = logging.getLogger(__name__)


@runtime_checkable
class StorageBackend(Protocol):
    """Four-method contract every storage adapter implements.

    See ``docs/storage-backend-contract.md`` for full semantics.
    """

    def save(
        self,
        key: str,
        content: bytes,
        *,
        content_type: Optional[str] = None,
    ) -> None: ...

    def url(self, key: str) -> str: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...


class StorageError(RuntimeError):
    """Raised by adapters when an underlying SDK call fails.

    Attributes:
        provider: the backend name (e.g. ``"aliyun"``, ``"local"``).
        op: one of ``"save"``, ``"url"``, ``"delete"``, ``"exists"``.
        key: the storage key that was being acted on, or ``None`` for ops
            (like a global config error) where a key doesn't apply.
        cause: the original SDK exception, if any.
    """

    def __init__(
        self,
        provider: str,
        op: str,
        key: Optional[str],
        cause: Optional[Exception] = None,
    ) -> None:
        self.provider = provider
        self.op = op
        self.key = key
        self.cause = cause
        suffix = f" (key={key!r})" if key is not None else ""
        message = f"storage_error: provider={provider} op={op}{suffix}"
        if cause is not None:
            message += f" cause={type(cause).__name__}: {cause}"
        super().__init__(message)


# ---------- LocalBackend ----------


class LocalBackend:
    """Filesystem-backed storage rooted at ``images_dir``.

    Preserves the historical layout where the FastAPI app mounts
    ``images_dir`` at ``/images/`` via ``StaticFiles``. ``key`` may contain
    forward slashes (e.g. ``temp/<sha1>.png``) — sub-directories are created
    on demand.
    """

    def __init__(self, images_dir: Path) -> None:
        self._images_dir = images_dir

    @property
    def images_dir(self) -> Path:
        return self._images_dir

    def save(
        self,
        key: str,
        content: bytes,
        *,
        content_type: Optional[str] = None,  # noqa: ARG002 - local fs has no MIME
    ) -> None:
        target = self._images_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def url(self, key: str) -> str:
        # Always forward slashes; ``os.path.join`` would use ``\`` on Windows.
        return f"/images/{key}"

    def delete(self, key: str) -> None:
        target = self._images_dir / key
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            # Treat unlink hiccups as non-fatal so the orchestrator can still
            # delete the DB row. We deliberately do not raise here.
            logger.info("LocalBackend.delete: could not unlink %s (%s)", target, exc)

    def exists(self, key: str) -> bool:
        return (self._images_dir / key).exists()


# ---------- factory ----------


def build_storage_backend(
    cfg: StorageConfig, *, images_dir: Path
) -> StorageBackend:
    """Construct a concrete backend from the validated ``StorageConfig``.

    Cloud adapters are imported lazily inside their branch so a missing SDK
    only breaks the deployments that actually opted into that provider — the
    Local-only path imports nothing beyond stdlib + pydantic.
    """
    backend = cfg.backend
    if backend == "local":
        return LocalBackend(images_dir=images_dir)
    if backend == "aliyun":
        from .storage_backends.aliyun import AliyunOSSBackend
        return AliyunOSSBackend(cfg.aliyun)
    if backend == "tencent":
        from .storage_backends.tencent import TencentCOSBackend
        return TencentCOSBackend(cfg.tencent)
    if backend == "cloudflare":
        from .storage_backends.aws_like import AwsLikeBackend
        return AwsLikeBackend.from_cloudflare(cfg.cloudflare)
    if backend == "aws":
        from .storage_backends.aws_like import AwsLikeBackend
        return AwsLikeBackend.from_aws(cfg.aws)
    if backend == "minio":
        from .storage_backends.aws_like import AwsLikeBackend
        return AwsLikeBackend.from_minio(cfg.minio)
    raise ValueError(f"unknown storage backend: {backend!r}")


# ---------- URL normalisation helper (S11) ----------


def hydrate_task_item_urls(item, backend: StorageBackend):
    """Populate ``item.image_url`` and ``item.input_image_url`` in place.

    ``item`` is a ``TaskItem``. We avoid importing ``TaskItem`` here to keep
    ``storage_backend`` independent of ``schemas``; duck-typing on the two
    fields is fine because both attributes are plain optional strings.
    """
    item.image_url = to_url(backend, item.image_path)
    item.input_image_url = to_url(backend, item.input_image_path)
    return item


def to_url(backend: StorageBackend, image_path: Optional[str]) -> Optional[str]:
    """Map an ``image_path`` value (from DB or runtime) to a client-facing URL.

    Three input shapes are accepted for backwards compatibility:

    1. Already an absolute ``http(s)://...`` URL — returned verbatim. (Lets
       cloud-backend rows whose ``image_path`` is a presigned/public URL pass
       through unchanged.)
    2. ``/images/...`` — already a local static-mount URL; returned verbatim.
    3. Anything else is treated as a storage key and routed through
       ``backend.url(key)``.

    ``None`` / empty input returns ``None``.
    """
    if not image_path:
        return None
    if image_path.startswith(("http://", "https://")):
        return image_path
    if image_path.startswith("/images/"):
        return image_path
    return backend.url(image_path)
