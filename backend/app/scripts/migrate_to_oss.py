"""One-shot migration: copy local ``images/`` files to the configured OSS backend
and rewrite ``tasks.image_path`` rows to bare keys.

Run from the ``backend/`` directory::

    python -m app.scripts.migrate_to_oss [--dry-run] [--limit N]

Behaviour:

* Requires ``config.storage.backend != "local"``.
* Scans rows in ``tasks`` whose ``image_path`` looks like a local path
  (absolute path, ``/images/...``, or the historical ``generated_<id>.<ext>``
  filename layout).
* For each row, computes the storage key as the basename of the resolved file.
* If ``storage.exists(key)`` already, it skips the upload and only updates the
  DB row if ``image_path`` is not yet the bare key.
* Otherwise reads the local file, sniffs ``Content-Type`` from the extension,
  and calls ``storage.save(key, content, content_type=...)``. Three retries
  with exponential backoff (0.5s / 1s / 2s) before giving up on
  ``StorageError``.
* Updates ``UPDATE tasks SET image_path = ? WHERE id = ?`` on success.
* Local files are **never** deleted — the user can clean them up manually
  after spot-checking the migration.

``--dry-run`` walks the same plan but skips ``storage.save`` and the
``UPDATE``. Useful for confirming what would happen.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import AppConfig, ConfigError, load_config
from ..core.storage_backend import (
    StorageBackend,
    StorageError,
    build_storage_backend,
)


logger = logging.getLogger("migrate_to_oss")


_EXT_TO_CONTENT_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


@dataclass
class _Stats:
    scanned: int = 0
    migrated: int = 0
    skipped_already: int = 0
    skipped_missing: int = 0
    failed: int = 0


def _configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _looks_like_local_path(image_path: str) -> bool:
    """True if ``image_path`` appears to refer to a local file rather than a key.

    A bare key has no leading slash and (for the generator's output) matches
    the ``generated_<id>.<ext>`` shape. We migrate:

    * absolute paths (anything starting with ``/`` or a drive letter),
    * ``/images/...`` static-mount paths,
    * the historical filename layout, even though it could technically already
      be a key — the migration is idempotent for those (``exists`` check).
    """
    if not image_path:
        return False
    # Absolute paths or static-mount URLs.
    if image_path.startswith("/"):
        return True
    if len(image_path) >= 2 and image_path[1] == ":":  # e.g. "C:\..."
        return True
    # ``generated_<id>.<ext>`` form — bare filename. Migrate so the DB picks
    # up the canonical key while the ``exists`` probe makes it a no-op upload.
    if image_path.startswith("generated_"):
        return True
    return False


def _resolve_local_file(image_path: str, images_dir: Path) -> Path:
    if image_path.startswith("/images/"):
        # ``/images/x/y.png`` → ``<images_dir>/x/y.png``.
        relative = image_path[len("/images/") :]
        return images_dir / relative
    p = Path(image_path)
    if p.is_absolute():
        return p
    return images_dir / p


def _content_type_for(path: Path) -> str:
    return _EXT_TO_CONTENT_TYPE.get(path.suffix.lower(), "application/octet-stream")


def _save_with_retry(
    storage: StorageBackend,
    key: str,
    content: bytes,
    *,
    content_type: str,
    attempts: int = 3,
) -> None:
    """Save with up to ``attempts`` tries; backoff 0.5s, 1s, 2s..."""
    delay = 0.5
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            storage.save(key, content, content_type=content_type)
            return
        except StorageError as exc:
            last_exc = exc
            if attempt == attempts:
                break
            logger.warning(
                "save attempt %d/%d for key=%s failed: %s; retrying in %.1fs",
                attempt,
                attempts,
                key,
                exc,
                delay,
            )
            time.sleep(delay)
            delay *= 2
    assert last_exc is not None
    raise last_exc


def _iter_candidate_rows(
    db_path: Path, *, limit: Optional[int]
) -> list[sqlite3.Row]:
    """Fetch and filter candidate rows up-front.

    Materialising the result means the read connection is closed before the
    caller starts opening write connections via :func:`_update_image_path`,
    which avoids SQLite "database is locked" errors during the migration
    loop.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT id, image_path FROM tasks "
            "WHERE image_path IS NOT NULL AND image_path != ''"
        )
        results: list[sqlite3.Row] = []
        for row in cur:
            if not _looks_like_local_path(row["image_path"]):
                continue
            results.append(row)
            if limit is not None and len(results) >= limit:
                break
        return results
    finally:
        conn.close()


def _update_image_path(db_path: Path, task_id: str, key: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE tasks SET image_path = ? WHERE id = ?", (key, task_id)
        )
        conn.commit()
    finally:
        conn.close()


def _migrate(
    config: AppConfig,
    storage: StorageBackend,
    *,
    dry_run: bool,
    limit: Optional[int],
) -> _Stats:
    stats = _Stats()
    images_dir = config.images_dir
    db_path = config.database_path

    for row in _iter_candidate_rows(db_path, limit=limit):
        stats.scanned += 1
        task_id = row["id"]
        image_path = row["image_path"]
        local_file = _resolve_local_file(image_path, images_dir)
        key = local_file.name  # bare filename = canonical key

        if not local_file.exists():
            logger.info("task=%s: file missing on disk (%s); skipping", task_id, local_file)
            stats.skipped_missing += 1
            continue

        try:
            already = storage.exists(key)
        except StorageError as exc:
            logger.error("task=%s: exists() failed for key=%s: %s", task_id, key, exc)
            stats.failed += 1
            continue

        if already:
            stats.skipped_already += 1
            if image_path != key and not dry_run:
                _update_image_path(db_path, task_id, key)
            logger.info(
                "task=%s: key=%s already present in OSS%s",
                task_id,
                key,
                " (DB updated)" if image_path != key and not dry_run else "",
            )
            continue

        content_type = _content_type_for(local_file)

        if dry_run:
            logger.info(
                "task=%s: WOULD upload %s → key=%s (content-type=%s)",
                task_id,
                local_file,
                key,
                content_type,
            )
            stats.migrated += 1
            continue

        try:
            content = local_file.read_bytes()
            _save_with_retry(storage, key, content, content_type=content_type)
        except StorageError as exc:
            logger.error("task=%s: save failed for key=%s: %s", task_id, key, exc)
            stats.failed += 1
            continue
        except OSError as exc:
            logger.error("task=%s: read failed for %s: %s", task_id, local_file, exc)
            stats.failed += 1
            continue

        _update_image_path(db_path, task_id, key)
        stats.migrated += 1
        logger.info("task=%s: migrated → key=%s", task_id, key)

    return stats


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_to_oss",
        description="Copy local images/ files to the configured OSS backend.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan-only; do not upload or modify the DB.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N candidate rows.",
    )
    args = parser.parse_args(argv)

    _configure_logging()

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if config.storage.backend == "local":
        print(
            "error: storage.backend is 'local' — nothing to migrate to. "
            "Configure an OSS backend in config/config.yaml first.",
            file=sys.stderr,
        )
        return 1

    storage = build_storage_backend(config.storage, images_dir=config.images_dir)
    stats = _migrate(config, storage, dry_run=args.dry_run, limit=args.limit)

    suffix = " (DRY RUN)" if args.dry_run else ""
    print(
        f"Done{suffix}. scanned={stats.scanned} migrated={stats.migrated} "
        f"skipped_already_in_oss={stats.skipped_already} "
        f"skipped_file_missing={stats.skipped_missing} failed={stats.failed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
