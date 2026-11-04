from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.responses import (
    error_response,
    observation_detail_response,
    observation_response,
)
from app.schemas.validation import parse_json_object, validate_observation
from app.services.observations import create_observation, get_observation as find_observation


router = APIRouter()


@router.post("/observations", tags=["ingestion"])
async def post_observation(request: Request) -> JSONResponse:
    payload = parse_json_object(await request.body())
    values = validate_observation(payload)
    result = create_observation(request.app.state.db_path, payload, values)
    return observation_response(
        result.observation,
        result.association,
        created=result.created,
    )


@router.get("/observations/{observation_id}", tags=["queries"])
def get_observation(request: Request, observation_id: str) -> JSONResponse:
    result = find_observation(request.app.state.db_path, observation_id)
    if result is None:
        return error_response(404, "not_found", "Observation not found")
    return observation_detail_response(result.observation, result.association)
