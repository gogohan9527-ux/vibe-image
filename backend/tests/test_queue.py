"""Task manager queueing semantics."""

from __future__ import annotations

import threading
import time

import pytest

from app.core.task_manager import TaskInput
from app.errors import QueueFullError


def _input(prompt: str = "p") -> TaskInput:
    return TaskInput(
        prompt=prompt,
        model="t8-/gpt-image-2",
        size="1024x1024",
        quality="low",
        format="jpeg",
    )


def test_queue_full_rejects_after_cap(app_config, storage, manager_factory):
    app_config.executor.default_queue_size = 3
    blocker = threading.Event()
    started_count = {"n": 0}
    started_lock = threading.Lock()

    def slow_runner(task, config, cancel_event=None, progress_cb=None, metadata_cb=None):
        with started_lock:
            started_count["n"] += 1
        # Block until the test releases us.
        blocker.wait(timeout=5)
        return config.images_dir / f"generated_{task.task_id}.jpeg"

    # concurrency 1 + queue_cap 3 => 1 running + 2 pending = 3 total
    app_config.executor.default_concurrency = 1
    manager = manager_factory(generator_runner=slow_runner)
    manager.set_queue_cap(3)
    manager.set_concurrency(1)

    manager.submit(_input("a"))
    manager.submit(_input("b"))
    manager.submit(_input("c"))

    with pytest.raises(QueueFullError) as exc_info:
        manager.submit(_input("d"))
    assert exc_info.value.cap == 3
    assert exc_info.value.queue_size == 3

    blocker.set()


def test_cancel_pending_drops_task(app_config, storage, manager_factory):
    blocker = threading.Event()

    def slow_runner(task, config, cancel_event=None, progress_cb=None, metadata_cb=None):
        blocker.wait(timeout=5)
        return config.images_dir / f"generated_{task.task_id}.jpeg"

    app_config.executor.default_concurrency = 1
    manager = manager_factory(generator_runner=slow_runner)
    manager.set_concurrency(1)

    running_row = manager.submit(_input("running"))
    pending_row = manager.submit(_input("pending"))

    cancel_result = manager.cancel(pending_row["id"])
    assert cancel_result["status"] == "cancelled"

    blocker.set()
    # Wait for the running task to finish.
    deadline = time.time() + 5
    while time.time() < deadline:
        row = storage.get_task(running_row["id"])
        if row["status"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(0.05)

    pending_after = storage.get_task(pending_row["id"])
    assert pending_after["status"] == "cancelled"


def test_cancel_running_sets_event(app_config, storage, manager_factory):
    started = threading.Event()
    cancel_observed = threading.Event()

    def slow_runner(task, config, cancel_event=None, progress_cb=None, metadata_cb=None):
        started.set()
        # poll for cancel
        deadline = time.time() + 3
        while time.time() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                cancel_observed.set()
                from app.errors import CancelledError

                raise CancelledError("cancelled in test")
            time.sleep(0.02)
        return config.images_dir / f"generated_{task.task_id}.jpeg"

    manager = manager_factory(generator_runner=slow_runner)

    row = manager.submit(_input("x"))
    assert started.wait(timeout=2)
    manager.cancel(row["id"])

    deadline = time.time() + 3
    while time.time() < deadline:
        if storage.get_task(row["id"])["status"] == "cancelled":
            break
        time.sleep(0.05)

    assert cancel_observed.is_set()
    assert storage.get_task(row["id"])["status"] == "cancelled"


def test_concurrency_change_keeps_running_tasks(app_config, manager_factory, storage):
    barrier = threading.Event()

    def slow_runner(task, config, cancel_event=None, progress_cb=None, metadata_cb=None):
        barrier.wait(timeout=5)
        return config.images_dir / f"generated_{task.task_id}.jpeg"

    app_config.executor.default_concurrency = 2
    manager = manager_factory(generator_runner=slow_runner)
    manager.set_concurrency(2)

    rows = [manager.submit(_input(f"p{i}")) for i in range(3)]
    # Two should be running, one pending.
    time.sleep(0.1)
    assert manager.total_load() == 3

    # Lower concurrency to 1 — running ones stay; pending shouldn't start.
    manager.set_concurrency(1)
    assert manager.concurrency == 1

    # Release them and let everything finish.
    barrier.set()
    deadline = time.time() + 6
    while time.time() < deadline:
        statuses = [storage.get_task(r["id"])["status"] for r in rows]
        if all(s in ("succeeded", "failed", "cancelled") for s in statuses):
            break
        time.sleep(0.1)

    final = [storage.get_task(r["id"])["status"] for r in rows]
    assert all(s == "succeeded" for s in final)
