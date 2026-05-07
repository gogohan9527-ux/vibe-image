"""Image generator: thin wrapper around the upstream image API.

Phases reported via ``progress_cb``:
    0   queued (set by the manager before this runs)
    10  about to POST to the upstream
    50  upstream returned a URL
    80  downloading the image bytes
    100 image saved to disk

Cancellation: between phases the generator checks ``cancel_event.is_set()``
and raises ``CancelledError`` if so.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from ..errors import CancelledError, UpstreamError


logger = logging.getLogger(__name__)


@dataclass
class GeneratorTask:
    task_id: str
    prompt: str
    model: str
    size: str
    quality: str
    format: str  # e.g. "jpeg", "png"


@dataclass
class GeneratorConfig:
    base_url: str
    api_key: str
    request_timeout_seconds: int
    images_dir: Path


def _check_cancel(cancel_event: Optional[threading.Event]) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("Task cancelled before completion.")


def _summary(text: str, n: int = 200) -> str:
    text = text or ""
    return text[:n] + ("..." if len(text) > n else "")


def _extract_image_url(payload: dict) -> str:
    data = payload.get("data") or []
    if not data:
        raise UpstreamError(
            f"Upstream returned no data: {_summary(json.dumps(payload, ensure_ascii=False))}"
        )
    url = data[0].get("url")
    if not url:
        raise UpstreamError("Upstream response did not contain an image URL.")
    return url


def generate_image(
    task: GeneratorTask,
    config: GeneratorConfig,
    cancel_event: Optional[threading.Event] = None,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> Path:
    """Run one generation. Returns the path to the saved image.

    Raises ``CancelledError`` if cancelled, ``UpstreamError`` for upstream
    failures.
    """

    def _emit(p: int) -> None:
        if progress_cb is not None:
            try:
                progress_cb(p)
            except Exception:  # noqa: BLE001 - progress callback errors must not break the task
                logger.exception("progress_cb raised; ignoring")

    _check_cancel(cancel_event)
    _emit(10)

    payload = json.dumps(
        {
            "model": task.model,
            "prompt": task.prompt,
            "n": 1,
            "size": task.size,
            "quality": task.quality,
            "format": task.format,
        }
    )
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            config.base_url,
            headers=headers,
            data=payload,
            timeout=config.request_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise UpstreamError(f"Upstream request failed: {exc}") from exc

    if resp.status_code >= 400:
        # Log status + summary, NEVER the Authorization header.
        logger.error(
            "Upstream %s returned %d: %s",
            config.base_url,
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

    image_url = _extract_image_url(result)

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

    config.images_dir.mkdir(parents=True, exist_ok=True)
    ext = task.format.lower().lstrip(".") or "jpeg"
    out_path = config.images_dir / f"generated_{task.task_id}.{ext}"
    out_path.write_bytes(image_resp.content)

    _check_cancel(cancel_event)
    _emit(100)

    return out_path
