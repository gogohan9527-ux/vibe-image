"""Upload routes — temp reference images for img2img tasks.

The single endpoint, ``POST /api/uploads/temp``, accepts a multipart ``file``
field, validates it as a real PNG / JPEG / WEBP (MIME + magic-byte header),
deduplicates by ``sha1(content)``, and writes it under
``config.images_temp_dir`` (= ``images_dir/temp``). The returned
``input_image_path`` is the form ``temp/<sha1>.<ext>`` and is what the
client is expected to feed verbatim back into ``POST /api/tasks``.

Header sniffing uses stdlib only (no Pillow dependency) — magic bytes are
sufficient to reject non-image payloads. The accepted formats and their
magic-byte signatures live in ``_HEADER_SNIFFERS`` below.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, File, Request, UploadFile

from ..config import AppConfig
from ..core.storage_backend import StorageBackend
from ..errors import InvalidUploadError, UploadTooLargeError
from ..schemas import TempUploadResponse


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/uploads", tags=["uploads"])


_ALLOWED_MIMES = {"image/png", "image/jpeg", "image/webp"}


def _sniff_image_format(content: bytes) -> Optional[str]:
    """Return the canonical extension (".png" / ".jpg" / ".webp") or None.

    Magic byte references:
    - PNG  : ``89 50 4E 47 0D 0A 1A 0A``
    - JPEG : starts with ``FF D8 FF`` (any of E0/E1/EE/DB second byte)
    - WEBP : ``RIFF....WEBP`` (12-byte container header)
    """
    if len(content) < 12:
        return None
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    return None


@router.post("/temp", response_model=TempUploadResponse)
async def upload_temp_image(
    request: Request,
    file: UploadFile = File(...),
) -> TempUploadResponse:
    config: AppConfig = request.app.state.config
    storage: StorageBackend = request.app.state.storage_backend
    max_bytes = config.defaults.max_upload_bytes

    # Reject up-front by content-type when the client tells us. We still
    # double-check the actual bytes below — content-type is user-supplied
    # and untrusted.
    declared_mime = (file.content_type or "").lower()
    if declared_mime and declared_mime not in _ALLOWED_MIMES:
        raise InvalidUploadError(
            reason=f"unsupported content-type: {declared_mime}"
        )

    # Stream the upload, capping at ``max_bytes + 1`` so we can detect overrun
    # without buffering arbitrarily large bodies.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLargeError(max_bytes=max_bytes, actual_bytes=total)
        chunks.append(chunk)

    content = b"".join(chunks)
    if not content:
        raise InvalidUploadError(reason="empty file")

    ext = _sniff_image_format(content)
    if ext is None:
        raise InvalidUploadError(reason="not a valid image (header sniff failed)")

    sha1 = hashlib.sha1(content, usedforsecurity=False).hexdigest()
    filename = f"{sha1}{ext}"
    key = f"temp/{filename}"
    # Skip the SDK round-trip when the object already exists (dedup).
    if not storage.exists(key):
        content_type = declared_mime or _ext_to_content_type(ext)
        storage.save(key, content, content_type=content_type)

    return TempUploadResponse(
        input_image_path=key,
        url=storage.url(key),
    )


def _ext_to_content_type(ext: str) -> str:
    """Best-effort mapping from sniffed extension back to MIME type."""
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")
