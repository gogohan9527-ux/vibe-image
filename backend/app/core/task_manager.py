"""Task manager: explicit pending queue + ThreadPoolExecutor + cancel/SSE.

Design:
- We keep our OWN pending queue (a deque) instead of submitting straight to
  the pool. Reasons:
  1. We need to enforce ``len(pending) + len(running) >= cap`` rejection
     synchronously at submit time.
  2. Cancelling a queued task must remove it BEFORE it ever starts running,
     which a vanilla executor's queue can't guarantee.
  3. ``set_concurrency`` must rebuild the pool without losing pending tasks.
- Running futures live in ``_running``. When one finishes we ``_pump()`` to
  start the next pending task.
- All state mutations go under ``self._lock``. Listener callbacks are called
  WITHOUT the lock to avoid deadlocks.
"""

from __future__ import annotations

import logging
import json
import threading
import uuid
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from ..config import AppConfig
from ..errors import (
    CancelledError,
    OutOfRangeError,
    QueueFullError,
    TaskNotCancellableError,
    TaskNotFoundError,
    UpstreamError,
    VibeError,
)
from ..providers import PROVIDER_REGISTRY
from .generator import GeneratorConfig, GeneratorTask, ReferenceImage, generate_image
from .storage import Storage, utcnow_iso
from .storage_backend import LocalBackend, StorageBackend, to_url


logger = logging.getLogger(__name__)


_CONTENT_TYPE_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _content_type_for_key(key: str) -> str:
    return _CONTENT_TYPE_BY_SUFFIX.get(Path(key).suffix.lower(), "application/octet-stream")


def _extract_revised_prompt(payload: object) -> Optional[str]:
    """Best-effort lookup of a human-readable summary in the upstream response.

    The OpenAI-shaped image-generation API may return
    ``{"data": [{"url": "...", "revised_prompt": "..."}]}``. We look there
    first, then fall back to a top-level ``revised_prompt``. Returns the
    trimmed string when present and non-empty, otherwise None.

    Note: as of this implementation the upstream we hit (see
    ``backend/app/core/generator.py``) does not guarantee this field; the
    title-from-response path is best-effort.
    """
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        candidate = data[0].get("revised_prompt")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    candidate = payload.get("revised_prompt")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return None


Listener = Callable[[dict], None]


@dataclass
class TaskInput:
    prompt: str
    model: str
    size: str
    quality: str
    format: str
    provider_id: str
    key_id: str
    base_url: str
    creds: dict[str, str]
    prompt_template_id: Optional[str] = None
    priority: bool = False
    # Canonical multi-reference keys, e.g. ["temp/<sha1>.png"].
    input_image_paths: list[str] = field(default_factory=list)


@dataclass
class TaskHandle:
    task_id: str
    task_input: TaskInput
    cancel_event: threading.Event = field(default_factory=threading.Event)
    future: Optional[Future] = None
    # True when the user provided a non-empty title; tells the generator
    # completion path to NOT overwrite the title with response text.
    title_locked: bool = False


class TaskManager:
    def __init__(
        self,
        storage: Storage,
        config: AppConfig,
        generator_runner: Optional[Callable[..., Any]] = None,
        storage_backend: Optional[StorageBackend] = None,
    ) -> None:
        self._storage = storage
        self._config = config
        self._generator_runner = generator_runner or generate_image
        # When no backend is injected (legacy test paths), fall back to the
        # local-filesystem backend rooted at the configured images_dir.
        self._storage_backend: StorageBackend = (
            storage_backend
            if storage_backend is not None
            else LocalBackend(images_dir=config.images_dir)
        )

        self._lock = threading.RLock()
        self._pending: Deque[TaskHandle] = deque()
        self._running: Dict[str, TaskHandle] = {}
        self._listeners: List[Listener] = []
        self._listeners_lock = threading.RLock()

        self._concurrency = config.executor.default_concurrency
        self._queue_cap = config.executor.default_queue_size

        self._executor = ThreadPoolExecutor(
            max_workers=self._concurrency, thread_name_prefix="vibe-task"
        )

    # ---------- public API ----------

    @property
    def concurrency(self) -> int:
        return self._concurrency

    @property
    def queue_cap(self) -> int:
        return self._queue_cap

    def total_load(self) -> int:
        with self._lock:
            return len(self._pending) + len(self._running)

    def submit(self, task_input: TaskInput) -> dict:
        """Submit a task; return the persisted task row dict."""
        with self._lock:
            current = len(self._pending) + len(self._running)
            if current >= self._queue_cap:
                raise QueueFullError(queue_size=current, cap=self._queue_cap)
            task_id = str(uuid.uuid4())

            handle = TaskHandle(
                task_id=task_id,
                task_input=task_input,
                title_locked=False,
            )
            row = {
                "id": task_id,
                "prompt_template_id": task_input.prompt_template_id,
                "prompt": task_input.prompt,
                "title": task_input.prompt.strip()[:30],
                "model": task_input.model,
                "size": task_input.size,
                "quality": task_input.quality,
                "format": task_input.format,
                "status": "queued",
                "progress": 0,
                "image_path": None,
                "error_message": None,
                "created_at": utcnow_iso(),
                "started_at": None,
                "finished_at": None,
                "priority": 1 if task_input.priority else 0,
                "provider_id": task_input.provider_id,
                "key_id": task_input.key_id,
                "input_image_path": (
                    task_input.input_image_paths[0]
                    if task_input.input_image_paths
                    else None
                ),
                "input_image_paths": (
                    json.dumps(task_input.input_image_paths)
                    if task_input.input_image_paths
                    else None
                ),
            }
            self._storage.insert_task(row)
            if task_input.priority:
                self._pending.appendleft(handle)
            else:
                self._pending.append(handle)
            self._pump_locked()

        self._emit({"event": "status", "task_id": task_id, "status": "queued", "progress": 0})
        return row

    def cancel(self, task_id: str) -> dict:
        """Cancel a queued or running task. Returns the updated row."""
        with self._lock:
            # Pending case.
            for i, h in enumerate(self._pending):
                if h.task_id == task_id:
                    del self._pending[i]
                    row = self._storage.update_task_fields(
                        task_id,
                        status="cancelled",
                        finished_at=utcnow_iso(),
                    )
                    listeners_payload = {
                        "event": "terminal",
                        "task_id": task_id,
                        "status": "cancelled",
                        "progress": row.get("progress", 0),
                    }
                    break
            else:
                # Running case.
                handle = self._running.get(task_id)
                if handle is not None:
                    handle.cancel_event.set()
                    row = self._storage.update_task_fields(
                        task_id, status="cancelling"
                    )
                    listeners_payload = {
                        "event": "status",
                        "task_id": task_id,
                        "status": "cancelling",
                        "progress": row.get("progress", 0),
                    }
                else:
                    # Not pending, not running: must be terminal.
                    try:
                        existing = self._storage.get_task(task_id)
                    except TaskNotFoundError:
                        raise
                    if existing["status"] in ("succeeded", "failed", "cancelled"):
                        raise TaskNotCancellableError(
                            f"Task is already {existing['status']}.",
                            task_id=task_id,
                            status=existing["status"],
                        )
                    raise TaskNotCancellableError(
                        f"Task in status {existing['status']} cannot be cancelled.",
                        task_id=task_id,
                    )

        self._emit(listeners_payload)
        return row

    def set_concurrency(self, n: int) -> None:
        max_n = self._config.executor.max_concurrency
        if n < 1 or n > max_n:
            raise OutOfRangeError("concurrency", f"concurrency must be 1..{max_n}")
        with self._lock:
            if n == self._concurrency:
                return
            old_pool = self._executor
            self._executor = ThreadPoolExecutor(
                max_workers=n, thread_name_prefix="vibe-task"
            )
            self._concurrency = n
            self._pump_locked()
        # Old pool keeps running its in-flight tasks; do not block.
        old_pool.shutdown(wait=False)

    def set_queue_cap(self, n: int) -> None:
        max_n = self._config.executor.max_queue_size
        if n < 1 or n > max_n:
            raise OutOfRangeError("queue_cap", f"queue_cap must be 1..{max_n}")
        with self._lock:
            self._queue_cap = n

    def shutdown(self) -> None:
        with self._lock:
            for handle in list(self._running.values()):
                handle.cancel_event.set()
        self._executor.shutdown(wait=False)

    # ---------- listeners ----------

    def subscribe(self, callback: Listener) -> None:
        with self._listeners_lock:
            self._listeners.append(callback)

    def unsubscribe(self, callback: Listener) -> None:
        with self._listeners_lock:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

    def _emit(self, payload: dict) -> None:
        with self._listeners_lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(payload)
            except Exception:  # noqa: BLE001 - listener crashes must not affect tasks
                logger.exception("listener raised; continuing")

    # ---------- internal: scheduling ----------

    def _pump_locked(self) -> None:
        """Move pending → running while capacity allows. Caller holds _lock."""
        while self._pending and len(self._running) < self._concurrency:
            handle = self._pending.popleft()
            self._running[handle.task_id] = handle
            handle.future = self._executor.submit(self._run_task, handle)

    def _run_task(self, handle: TaskHandle) -> None:
        task_id = handle.task_id
        task_input = handle.task_input

        # Pre-flight cancel check (it might have been cancelled while pending — but
        # we removed those above; this is for race safety).
        if handle.cancel_event.is_set():
            self._finalize_cancelled(handle)
            return

        # Mark running.
        try:
            self._storage.update_task_fields(
                task_id,
                status="running",
                progress=0,
                started_at=utcnow_iso(),
            )
        except TaskNotFoundError:
            return  # row was deleted from under us; bail

        self._emit(
            {"event": "status", "task_id": task_id, "status": "running", "progress": 0}
        )

        provider = PROVIDER_REGISTRY.get(task_input.provider_id)
        if provider is None:
            self._finalize_failed(
                handle, f"unknown provider: {task_input.provider_id}"
            )
            return

        gen_config = GeneratorConfig(
            provider=provider,
            creds=dict(task_input.creds),
            base_url=task_input.base_url,
            request_timeout_seconds=self._config.defaults.request_timeout_seconds,
            images_dir=self._config.images_dir,
            storage_backend=self._storage_backend,
        )
        try:
            reference_images = self._build_reference_images(
                task_input.input_image_paths
            )
        except Exception as exc:  # noqa: BLE001 - storage backends wrap SDK errors
            self._finalize_failed(handle, f"Reference image unavailable: {exc}")
            return

        gen_task = GeneratorTask(
            task_id=task_id,
            prompt=task_input.prompt,
            model=task_input.model,
            size=task_input.size,
            quality=task_input.quality,
            format=task_input.format,
            reference_images=reference_images,
        )

        def _on_progress(p: int) -> None:
            try:
                self._storage.update_progress(task_id, p)
            except TaskNotFoundError:
                return
            self._emit(
                {"event": "progress", "task_id": task_id, "progress": p, "status": "running"}
            )

        def _on_metadata(payload: dict) -> None:
            # Best-effort title overwrite from the upstream response.
            if handle.title_locked:
                return
            revised = _extract_revised_prompt(payload)
            if not revised:
                return
            try:
                self._storage.update_task_title(task_id, revised[:30])
            except TaskNotFoundError:
                return

        try:
            image_result = self._generator_runner(
                gen_task,
                gen_config,
                cancel_event=handle.cancel_event,
                progress_cb=_on_progress,
                metadata_cb=_on_metadata,
            )
        except CancelledError:
            self._finalize_cancelled(handle)
            return
        except (UpstreamError, VibeError) as exc:
            self._finalize_failed(handle, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - unknown errors must still terminate cleanly
            logger.exception("Unexpected generator failure for %s", task_id)
            self._finalize_failed(handle, f"Unexpected error: {exc}")
            return

        # ``generate_image`` now returns a storage key (str). For backward
        # compatibility with tests/runners that still return a ``Path``, fall
        # back to the file basename — which under LocalBackend matches the
        # historical key naming.
        if isinstance(image_result, Path):
            image_key = image_result.name
        else:
            image_key = str(image_result)

        # Success.
        try:
            row = self._storage.update_task_fields(
                task_id,
                status="succeeded",
                progress=100,
                image_path=image_key,
                finished_at=utcnow_iso(),
            )
        except TaskNotFoundError:
            return
        finally:
            self._post_run_cleanup(task_id)
        image_path_str = row.get("image_path")
        image_url = to_url(self._storage_backend, image_path_str)
        self._emit(
            {
                "event": "terminal",
                "task_id": task_id,
                "status": "succeeded",
                "progress": 100,
                "image_path": image_path_str,
                "image_url": image_url,
            }
        )

    def _build_reference_images(self, keys: list[str]) -> list[ReferenceImage]:
        refs: list[ReferenceImage] = []
        for key in keys:
            refs.append(
                ReferenceImage(
                    key=key,
                    url=self._storage_backend.url(key),
                    filename=Path(key).name,
                    content_type=_content_type_for_key(key),
                    content=self._storage_backend.read(key),
                )
            )
        return refs

    def _finalize_cancelled(self, handle: TaskHandle) -> None:
        try:
            self._storage.update_task_fields(
                handle.task_id,
                status="cancelled",
                finished_at=utcnow_iso(),
            )
        except TaskNotFoundError:
            pass
        self._post_run_cleanup(handle.task_id)
        self._emit(
            {
                "event": "terminal",
                "task_id": handle.task_id,
                "status": "cancelled",
                "progress": 0,
            }
        )

    def _finalize_failed(self, handle: TaskHandle, message: str) -> None:
        try:
            self._storage.update_task_fields(
                handle.task_id,
                status="failed",
                error_message=message,
                finished_at=utcnow_iso(),
            )
        except TaskNotFoundError:
            pass
        self._post_run_cleanup(handle.task_id)
        self._emit(
            {
                "event": "terminal",
                "task_id": handle.task_id,
                "status": "failed",
                "progress": 0,
                "error_message": message,
            }
        )

    def _post_run_cleanup(self, task_id: str) -> None:
        with self._lock:
            self._running.pop(task_id, None)
            self._pump_locked()
