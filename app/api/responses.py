from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from app.schemas.types import JsonObject


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


def create_or_existing_response(
    record_key: str,
    record: JsonObject,
    *,
    created: bool,
    additional_content: dict[str, Any] | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "status": "created" if created else "existing",
        record_key: record,
    }
    if additional_content:
        content.update(additional_content)
    return JSONResponse(status_code=201 if created else 200, content=content)


def observation_response(
    observation: JsonObject,
    association: dict[str, str] | None,
    *,
    created: bool,
) -> JSONResponse:
    return create_or_existing_response(
        "observation",
        observation,
        created=created,
        additional_content={"association": association},
    )


def observation_detail_response(
    observation: JsonObject,
    association: dict[str, str] | None,
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"observation": observation, "association": association},
    )


def history_response(
    aircraft_id: str,
    from_text: str | None,
    to_text: str | None,
    history: list[JsonObject],
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={
            "aircraft_id": aircraft_id,
            "filters": {"from": from_text, "to": to_text},
            "count": len(history),
            "history": history,
        },
    )
