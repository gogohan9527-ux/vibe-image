"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make ``backend/`` importable so ``app.*`` resolves.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.config import (  # noqa: E402
    ApiConfig,
    AppConfig,
    ExecutorConfig,
    PathsConfig,
    ServerConfig,
)
from app.core.storage import Storage  # noqa: E402
from app.core.task_manager import TaskManager  # noqa: E402


def make_config(tmp_path: Path, **overrides) -> AppConfig:
    images_dir = tmp_path / "images"
    prompts_dir = tmp_path / "prompts"
    db_path = tmp_path / "data" / "vibe.db"
    images_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    cfg = AppConfig(
        api=ApiConfig(
            base_url="https://example.invalid/v1/images/generations",
            api_key="sk-test-key",
            default_model="t8-/gpt-image-2",
            default_size="1024x1024",
            default_quality="low",
            default_format="jpeg",
            request_timeout_seconds=5,
        ),
        server=ServerConfig(host="127.0.0.1", port=8000, cors_origins=[]),
        executor=ExecutorConfig(
            default_concurrency=overrides.get("concurrency", 2),
            default_queue_size=overrides.get("queue_size", 10),
            max_concurrency=32,
            max_queue_size=10000,
        ),
        paths=PathsConfig(
            images_dir=str(images_dir),
            prompts_dir=str(prompts_dir),
            database_path=str(db_path),
        ),
    )
    return cfg


@pytest.fixture
def app_config(tmp_path):
    return make_config(tmp_path)


@pytest.fixture
def storage(app_config):
    s = Storage(db_path=app_config.database_path, prompts_dir=app_config.prompts_dir)
    yield s
    s.close()


@pytest.fixture
def manager_factory(app_config, storage):
    created = []

    def _make(generator_runner=None):
        m = TaskManager(
            storage=storage, config=app_config, generator_runner=generator_runner
        )
        created.append(m)
        return m

    yield _make
    for m in created:
        m.shutdown()
