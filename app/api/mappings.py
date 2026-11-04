from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.responses import create_or_existing_response
from app.schemas.validation import parse_json_object, validate_mapping
from app.services.mappings import create_mapping


router = APIRouter()


@router.post("/identity-mappings", tags=["ingestion"])
async def post_identity_mapping(request: Request) -> JSONResponse:
    payload = parse_json_object(await request.body())
    values = validate_mapping(payload)
    result = create_mapping(request.app.state.db_path, payload, values)
    return create_or_existing_response(
        "identity_mapping",
        result.identity_mapping,
        created=result.created,
    )
