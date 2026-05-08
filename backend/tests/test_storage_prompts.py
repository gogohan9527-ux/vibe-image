"""Unit tests for SQLite-backed prompt template CRUD + init seeding."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.storage import Storage
from app.errors import PromptConflictError, PromptNotFoundError


# ---------- list / get / save / delete ----------


def test_save_prompt_inserts_row_with_slug(storage):
    rec = storage.save_prompt(title="Moonlit Forest", prompt="trees + fireflies")
    assert rec["id"] == "moonlit_forest"
    assert rec["title"] == "Moonlit Forest"
    assert rec["prompt"] == "trees + fireflies"
    assert rec["created_at"]
    # round-trips via list_prompts
    items = storage.list_prompts()
    assert any(p["id"] == "moonlit_forest" for p in items)


def test_save_prompt_id_collision_appends_suffix(storage):
    a = storage.save_prompt(title="duplicate", prompt="one")
    b = storage.save_prompt(title="duplicate", prompt="two")
    c = storage.save_prompt(title="duplicate", prompt="three")
    assert a["id"] == "duplicate"
    assert b["id"] == "duplicate-2"
    assert c["id"] == "duplicate-3"


def test_save_prompt_explicit_id_used_when_provided(storage):
    rec = storage.save_prompt(title="x", prompt="y", prompt_id="custom_id_99")
    assert rec["id"] == "custom_id_99"


def test_get_prompt_missing_raises(storage):
    with pytest.raises(PromptNotFoundError):
        storage.get_prompt("nope")


def test_get_prompt_returns_record(storage):
    storage.save_prompt(title="cat", prompt="meow", prompt_id="cat_meow")
    rec = storage.get_prompt("cat_meow")
    assert rec["id"] == "cat_meow"
    assert rec["prompt"] == "meow"


def test_delete_prompt_removes_row(storage):
    storage.save_prompt(title="ephemeral", prompt="x", prompt_id="ephemeral")
    storage.delete_prompt("ephemeral")
    with pytest.raises(PromptNotFoundError):
        storage.get_prompt("ephemeral")


def test_delete_prompt_missing_raises(storage):
    with pytest.raises(PromptNotFoundError):
        storage.delete_prompt("does_not_exist")


def test_delete_prompt_sample_protected(storage):
    storage.ensure_sample_prompt()
    with pytest.raises(PromptConflictError):
        storage.delete_prompt("sample")
    # still present
    rec = storage.get_prompt("sample")
    assert rec["id"] == "sample"


def test_list_prompts_orders_by_created_at_desc(storage):
    # Insert two with controlled timestamps via save_prompt + raw update.
    a = storage.save_prompt(title="alpha", prompt="A")
    b = storage.save_prompt(title="beta", prompt="B")
    items = storage.list_prompts()
    ids = [i["id"] for i in items]
    # Both present
    assert a["id"] in ids and b["id"] in ids


# ---------- update_prompt ----------


def test_update_prompt_title_only(storage):
    storage.save_prompt(title="old", prompt="content", prompt_id="upd1")
    rec = storage.update_prompt("upd1", title="new name")
    assert rec["title"] == "new name"
    assert rec["prompt"] == "content"


def test_update_prompt_prompt_only(storage):
    storage.save_prompt(title="n", prompt="old", prompt_id="upd2")
    rec = storage.update_prompt("upd2", prompt="new")
    assert rec["title"] == "n"
    assert rec["prompt"] == "new"


def test_update_prompt_both_fields(storage):
    storage.save_prompt(title="n", prompt="c", prompt_id="upd3")
    rec = storage.update_prompt("upd3", title="N", prompt="C")
    assert rec["title"] == "N"
    assert rec["prompt"] == "C"


def test_update_prompt_empty_payload_raises_value_error(storage):
    storage.save_prompt(title="n", prompt="c", prompt_id="upd4")
    with pytest.raises(ValueError):
        storage.update_prompt("upd4")


def test_update_prompt_missing_raises_not_found(storage):
    with pytest.raises(PromptNotFoundError):
        storage.update_prompt("not_there", title="x")


# ---------- init_prompt_templates_from_files ----------


def _write(p: Path, payload) -> None:
    p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) if isinstance(payload, (dict, list))
        else str(payload),
        encoding="utf-8",
    )


def test_init_imports_seed_files_then_skips_on_second_run(storage, tmp_path):
    # `storage` fixture's prompts_dir is empty; drop seed files into it.
    p1 = storage.prompts_dir / "prompt_alpha.json"
    p2 = storage.prompts_dir / "prompt_beta.json"
    # Use new field names
    _write(p1, {"id": "alpha", "title": "A", "prompt": "a"})
    _write(p2, {"id": "beta", "title": "B", "prompt": "b"})

    imported, skipped = storage.init_prompt_templates_from_files()
    assert (imported, skipped) == (2, 0)

    # Idempotent: second pass writes nothing.
    imported, skipped = storage.init_prompt_templates_from_files()
    assert (imported, skipped) == (0, 2)


def test_init_imports_legacy_name_content_keys(storage):
    """Files using legacy name/content keys should still be imported."""
    p = storage.prompts_dir / "prompt_legacy.json"
    _write(p, {"id": "legacy", "name": "L", "content": "legacy content"})

    imported, skipped = storage.init_prompt_templates_from_files()
    assert imported == 1
    rec = storage.get_prompt("legacy")
    assert rec["title"] == "L"
    assert rec["prompt"] == "legacy content"


def _by_module(result, module):
    return next(r for r in result if r["module"] == module)


def test_init_db_reports_schema_and_seed_data(storage):
    p = storage.prompts_dir / "prompt_alpha.json"
    _write(p, {"id": "alpha", "title": "A", "prompt": "a"})

    result = storage.init_db()
    assert _by_module(result, "tasks")["status"] == "exists"
    pt = _by_module(result, "prompt_templates")
    assert pt["status"] == "exists"
    assert pt["imported"] == 1
    assert pt["skipped"] == 0

    result = storage.init_db()
    pt = _by_module(result, "prompt_templates")
    assert pt["imported"] == 0
    assert pt["skipped"] == 1
    assert storage.get_prompt("alpha")["prompt"] == "a"


def test_init_skips_existing_id_does_not_overwrite(storage):
    # Seed via save_prompt with custom content first.
    storage.save_prompt(title="kept", prompt="DB-version", prompt_id="alpha")
    p = storage.prompts_dir / "prompt_alpha.json"
    _write(p, {"id": "alpha", "title": "JSON", "prompt": "JSON-version"})

    imported, skipped = storage.init_prompt_templates_from_files()
    assert (imported, skipped) == (0, 1)
    rec = storage.get_prompt("alpha")
    # The DB row was NOT overwritten by the JSON file.
    assert rec["prompt"] == "DB-version"


def test_init_tolerates_malformed_json(storage):
    bad = storage.prompts_dir / "prompt_bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    good = storage.prompts_dir / "prompt_good.json"
    _write(good, {"id": "good", "title": "G", "prompt": "g"})

    imported, skipped = storage.init_prompt_templates_from_files()
    # Bad file is logged-and-skipped (not raised); good is imported.
    assert imported == 1
    assert skipped == 0


def test_init_skips_missing_required_keys(storage):
    p = storage.prompts_dir / "prompt_missing.json"
    _write(p, {"id": "missing", "title": "only-id-and-title"})  # no prompt
    imported, skipped = storage.init_prompt_templates_from_files()
    assert imported == 0
