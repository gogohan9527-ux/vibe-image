"""FastAPI app entrypoint for the vibe-image backend."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import history as history_routes
from .api import prompts as prompts_routes
from .api import settings as settings_routes
from .api import tasks as tasks_routes
from .config import AppConfig, ConfigError, get_config
from .core.storage import Storage
from .core.task_manager import TaskManager
from .errors import VibeError


logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    config: AppConfig = app.state.config
    storage = Storage(db_path=config.database_path, prompts_dir=config.prompts_dir)
    storage.mark_orphaned_running_as_failed()
    config.images_dir.mkdir(parents=True, exist_ok=True)

    manager = TaskManager(storage=storage, config=config)
    app.state.storage = storage
    app.state.task_manager = manager
    try:
        yield
    finally:
        manager.shutdown()
        storage.close()


def create_app(config: AppConfig | None = None) -> FastAPI:
    _configure_logging()
    if config is None:
        try:
            config = get_config()
        except ConfigError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)

    app = FastAPI(title="vibe-image", version="0.1.0", lifespan=_lifespan)
    app.state.config = config

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(tasks_routes.router, prefix="/api")
    app.include_router(prompts_routes.router, prefix="/api")
    app.include_router(settings_routes.router, prefix="/api")
    app.include_router(history_routes.router, prefix="/api")

    # Static images. Mount AFTER routers so /api/* never gets shadowed.
    # StaticFiles requires the directory to exist at mount time; lifespan
    # creates it on startup, but create_app runs before lifespan so we
    # ensure it here too.
    config.images_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/images",
        StaticFiles(directory=str(config.images_dir)),
        name="images",
    )

    @app.exception_handler(VibeError)
    async def _vibe_error_handler(_: Request, exc: VibeError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_payload())

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
