from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


def create_system_router(static_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/", include_in_schema=False)
    def web_interface() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return router
