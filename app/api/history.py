from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.api.responses import history_response
from app.schemas.types import ValidationDetail
from app.schemas.validation import (
    InputValidationError,
    parse_timestamp,
    validate_interval,
)
from app.services.aircraft_history import get_aircraft_history as find_aircraft_history


router = APIRouter()


@router.get("/aircraft/{aircraft_id}/history", tags=["queries"])
def get_aircraft_history(
    request: Request,
    aircraft_id: str,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
) -> JSONResponse:
    from_ms: int | None = None
    to_ms: int | None = None
    if from_ is not None:
        _, from_ms = parse_timestamp(from_, "from")
    if to is not None:
        _, to_ms = parse_timestamp(to, "to")

    errors: list[ValidationDetail] = []
    validate_interval(
        from_ms,
        to_ms,
        from_field="from",
        to_field="to",
        errors=errors,
    )
    if errors:
        raise InputValidationError(errors)

    history = find_aircraft_history(
        request.app.state.db_path,
        aircraft_id,
        from_ms,
        to_ms,
    )
    return history_response(aircraft_id, from_, to, history)
