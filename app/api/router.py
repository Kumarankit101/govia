from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.api.history import router as history_router
from app.api.mappings import router as mappings_router
from app.api.observations import router as observations_router
from app.api.system import create_system_router


def register_routes(app: FastAPI, static_dir: Path) -> None:
    app.include_router(observations_router)
    app.include_router(mappings_router)
    app.include_router(history_router)
    app.include_router(create_system_router(static_dir))
