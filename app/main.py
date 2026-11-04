from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_exception_handlers
from app.api.responses import error_response
from app.api.router import register_routes
from app.database import DEFAULT_DB_PATH, initialize_database
from app.schemas.serialization import load_json
from app.services.identity_resolution import current_association


STATIC_DIR = Path(__file__).with_name("static")


def create_app(db_path: str | Path | None = None) -> FastAPI:
    resolved_db_path = Path(
        db_path if db_path is not None else os.getenv("GOVIA_DB_PATH", DEFAULT_DB_PATH)
    ).resolve()
    initialize_database(resolved_db_path)

    app = FastAPI(
        title="Govia Aircraft History",
        version="1.0.0",
        description="Ingest position reports and resolve time-bounded aircraft identities.",
    )
    app.state.db_path = resolved_db_path

    register_exception_handlers(app)
    register_routes(app, STATIC_DIR)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()


__all__ = [
    "app",
    "create_app",
    "current_association",
    "error_response",
    "load_json",
]
