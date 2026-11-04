from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.responses import error_response
from app.schemas.validation import InputValidationError
from app.services.errors import ServiceConflictError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(InputValidationError)
    async def input_validation_handler(
        _request: Request, exc: InputValidationError
    ) -> JSONResponse:
        return error_response(400, "invalid_request", "Request validation failed", exc.details)

    @app.exception_handler(ServiceConflictError)
    async def service_conflict_handler(
        _request: Request, exc: ServiceConflictError
    ) -> JSONResponse:
        return error_response(409, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        message = exc.detail if isinstance(exc.detail, str) else "HTTP request failed"
        return error_response(
            exc.status_code,
            codes.get(exc.status_code, "http_error"),
            message,
            headers=exc.headers,
        )
