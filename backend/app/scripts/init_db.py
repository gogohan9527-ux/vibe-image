"""CLI entrypoint to initialize the database and seed prompt templates.

Run from the ``backend/`` directory::

    python -m app.scripts.init_db

Creates all tables (tasks, prompt_templates) if they do not already exist,
then imports any ``<project_root>/prompt/prompt_*.json`` seed files whose
``id`` is not already present in the database. Existing rows are never
overwritten. The printed result comes directly from ``Storage.init_db()``.
"""

from __future__ import annotations

import logging
import sys
import traceback

from ..config import ConfigError, get_config
from ..core.storage import Storage


def _configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    _configure_logging()
    try:
        config = get_config()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    storage = Storage(
        db_path=config.database_path,
        prompts_dir=config.prompts_dir,
    )
    try:
        result = storage.init_db()
    finally:
        storage.close()
    for r in result:
        print(r["message"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - top-level CLI: log + exit non-zero
        traceback.print_exc()
        sys.exit(1)
