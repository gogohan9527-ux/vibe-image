"""Image generator: dispatches a Provider's HttpCall and saves the image.

Phases reported via ``progress_cb``:
    0   queued (set by the manager before this runs)
    10  about to POST to the upstream
    50  upstream returned a URL
    80  downloading the image bytes
    100 image saved to disk

Cancellation: between phases the generator checks ``cancel_event.is_set()``
and raises ``CancelledError`` if so.

The generator no longer hardcodes the upstream payload — it asks the
``Provider`` to produce an ``HttpCall``, dispatches it, and asks the same
provider to parse the response into a ``ParsedResult``.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from ..errors import CancelledError, ProviderCapabilityError, UpstreamError
from ..providers.base import Provider
from .storage_backend import StorageBackend


logger = logging.getLogger(__name__)


@dataclass
class GeneratorTask:
    task_id: str
    prompt: str
    model: str
    size: str
    quality: str
    format: str  # e.g. "jpeg", "png"
    # 2026-05-09 Addendum (II) — when set, route through the provider's
    # ``build_image_edit_request`` instead of ``build_request``.
    input_image_path: Optional[Path] = None


@dataclass
class GeneratorConfig:
    """Per-call configuration injected by ``TaskManager``.

    As of 2026-05-11 the generator no longer touches the filesystem directly;
    it pushes bytes through ``storage_backend`` which decides whether they
    land on local disk or in an object-storage bucket. ``images_dir`` is
    retained because the legacy local backend still uses it indirectly and
    because img2img code paths may pull reference bytes off disk.
    """

    provider: Provider
    creds: dict
    base_url: str
    request_timeout_seconds: int
    images_dir: Path
    storage_backend: Optional[StorageBackend] = None


def _check_cancel(cancel_event: Optional[threading.Event]) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("Task cancelled before completion.")


def _summary(text: str, n: int = 200) -> str:
    text = text or ""
    return text[:n] + ("..." if len(text) > n else "")


def generate_image(
    task: GeneratorTask,
    config: GeneratorConfig,
    cancel_event: Optional[threading.Event] = None,
    progress_cb: Optional[Callable[[int], None]] = None,
    metadata_cb: Optional[Callable[[dict], None]] = None,
) -> str:
    """Run one generation. Returns the **storage key** of the saved image.

    The key is what the caller persists in ``tasks.image_path`` and what
    ``storage_backend.url(key)`` translates into a client-facing URL. For
    the local backend the file ends up at ``images_dir / key``; for cloud
    backends it lands in the bucket under the adapter's prefix.

    Raises ``CancelledError`` if cancelled, ``UpstreamError`` for upstream
    failures.
    """

    def _emit(p: int) -> None:
        if progress_cb is not None:
            try:
                progress_cb(p)
            except Exception:  # noqa: BLE001 - progress callback errors must not break the task
                logger.exception("progress_cb raised; ignoring")

    def _emit_metadata(payload: dict) -> None:
        if metadata_cb is None:
            return
        try:
            metadata_cb(payload)
        except Exception:  # noqa: BLE001 - metadata callback must not break the task
            logger.exception("metadata_cb raised; ignoring")

    _check_cancel(cancel_event)
    _emit(10)

    if task.input_image_path is not None:
        # img2img path — provider must opt-in via ``supports_image_input``
        # AND expose ``build_image_edit_request``. Otherwise reject early.
        provider = config.provider
        provider_id = getattr(provider, "id", "unknown")
        if not getattr(provider, "supports_image_input", False) or not hasattr(
            provider, "build_image_edit_request"
        ):
            raise ProviderCapabilityError(
                provider_id=provider_id, capability="image_input"
            )
        call = provider.build_image_edit_request(
            task=task,
            creds=config.creds,
            base_url=config.base_url,
            model=task.model,
        )
    else:
        call = config.provider.build_request(
            task=task,
            creds=config.creds,
            base_url=config.base_url,
            model=task.model,
        )

    try:
        if call.files is not None:
            # multipart: do NOT pass json=. Let requests build the boundary.
            resp = requests.request(
                method=call.method,
                url=call.url,
                headers=call.headers,
                files=call.files,
                data=call.data,
                timeout=config.request_timeout_seconds,
            )
        else:
            resp = requests.request(
                method=call.method,
                url=call.url,
                headers=call.headers,
                json=call.json_body,
                timeout=config.request_timeout_seconds,
            )
    except requests.RequestException as exc:
        raise UpstreamError(f"Upstream request failed: {exc}") from exc

    if resp.status_code >= 400:
        # Log status + summary, NEVER the Authorization header.
        logger.error(
            "Upstream %s returned %d: %s",
            call.url,
            resp.status_code,
            _summary(resp.text),
        )
        raise UpstreamError(
            f"Upstream returned HTTP {resp.status_code}: {_summary(resp.text)}"
        )

    try:
        result = resp.json()
    except ValueError as exc:
        raise UpstreamError(
            f"Upstream returned non-JSON body: {_summary(resp.text)}"
        ) from exc

    parsed = config.provider.parse_response(result)
    _emit_metadata(result)

    image_url = parsed.image_url
    if not image_url:
        raise UpstreamError("Upstream response did not contain an image URL.")

    _check_cancel(cancel_event)
    _emit(50)

    try:
        image_resp = requests.get(image_url, timeout=config.request_timeout_seconds)
    except requests.RequestException as exc:
        raise UpstreamError(f"Image download failed: {exc}") from exc
    if image_resp.status_code >= 400:
        raise UpstreamError(
            f"Image download HTTP {image_resp.status_code}: {_summary(image_resp.text)}"
        )

    _check_cancel(cancel_event)
    _emit(80)

    if config.storage_backend is None:
        raise RuntimeError(
            "generate_image requires GeneratorConfig.storage_backend; "
            "callers must inject the StorageBackend built in app lifespan"
        )

    ext = task.format.lower().lstrip(".") or "jpeg"
    key = f"generated_{task.task_id}.{ext}"
    content_type = image_resp.headers.get("content-type")
    config.storage_backend.save(key, image_resp.content, content_type=content_type)

    _check_cancel(cancel_event)
    _emit(100)

    return key
