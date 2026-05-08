"""Tests for task title plumbing: auto-derive from prompt + overwrite from LLM response."""

from __future__ import annotations

from app.core.task_manager import TaskInput, _extract_revised_prompt


def _input(prompt: str = "a cat playing in a wide green garden", **kw) -> TaskInput:
    return TaskInput(
        prompt=prompt,
        model="t8-/gpt-image-2",
        size="1024x1024",
        quality="low",
        format="jpeg",
        **kw,
    )


def test_submit_uses_prompt_prefix_as_title(app_config, manager_factory, storage):
    def runner(task, config, cancel_event=None, progress_cb=None, metadata_cb=None):
        return config.images_dir / f"generated_{task.task_id}.jpeg"

    manager = manager_factory(generator_runner=runner)
    long_prompt = "x" * 50
    row = manager.submit(_input(prompt=long_prompt))
    persisted = storage.get_task(row["id"])
    assert persisted["title"] == "x" * 30


def test_submit_short_prompt_used_in_full(app_config, manager_factory, storage):
    def runner(task, config, cancel_event=None, progress_cb=None, metadata_cb=None):
        return config.images_dir / f"generated_{task.task_id}.jpeg"

    manager = manager_factory(generator_runner=runner)
    row = manager.submit(_input(prompt="hello world prompt"))
    persisted = storage.get_task(row["id"])
    assert persisted["title"] == "hello world prompt"


def test_extract_revised_prompt_in_data_field():
    payload = {"data": [{"url": "x", "revised_prompt": "  refined cat scene  "}]}
    assert _extract_revised_prompt(payload) == "refined cat scene"


def test_extract_revised_prompt_top_level():
    payload = {"data": [{"url": "x"}], "revised_prompt": "fallback summary"}
    assert _extract_revised_prompt(payload) == "fallback summary"


def test_extract_revised_prompt_missing_returns_none():
    assert _extract_revised_prompt({"data": [{"url": "x"}]}) is None
    assert _extract_revised_prompt({}) is None
    assert _extract_revised_prompt(None) is None


def test_generator_metadata_overwrites_title(
    app_config, manager_factory, storage
):
    """metadata_cb should overwrite the fallback title (prompt[:30]) with revised_prompt[:30]."""
    revised = "A magnificent cat among the dewy garden roses at dawn"

    def runner(task, config, cancel_event=None, progress_cb=None, metadata_cb=None):
        if metadata_cb is not None:
            metadata_cb({"data": [{"url": "x", "revised_prompt": revised}]})
        out = config.images_dir / f"generated_{task.task_id}.jpeg"
        out.write_bytes(b"FAKE")
        return out

    manager = manager_factory(generator_runner=runner)
    row = manager.submit(_input(prompt="cat in garden"))
    task_id = row["id"]

    import time
    deadline = time.time() + 3
    while time.time() < deadline:
        if storage.get_task(task_id)["status"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(0.05)

    persisted = storage.get_task(task_id)
    assert persisted["status"] == "succeeded"
    assert persisted["title"] == revised[:30]


def test_generator_no_revised_prompt_keeps_fallback(
    app_config, manager_factory, storage
):
    """If the upstream payload has no revised_prompt, fallback title persists."""

    def runner(task, config, cancel_event=None, progress_cb=None, metadata_cb=None):
        if metadata_cb is not None:
            metadata_cb({"data": [{"url": "x"}]})
        out = config.images_dir / f"generated_{task.task_id}.jpeg"
        out.write_bytes(b"FAKE")
        return out

    manager = manager_factory(generator_runner=runner)
    row = manager.submit(_input(prompt="aaaa bbbb cccc dddd eeee ffff"))
    task_id = row["id"]

    import time
    deadline = time.time() + 3
    while time.time() < deadline:
        if storage.get_task(task_id)["status"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(0.05)

    persisted = storage.get_task(task_id)
    assert persisted["title"] == "aaaa bbbb cccc dddd eeee ffff"
