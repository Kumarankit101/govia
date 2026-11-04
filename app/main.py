from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import DEFAULT_DB_PATH, connect, initialize_database, serialized_write
from app.validation import (
    InputValidationError,
    dump_json,
    json_values_equal,
    parse_json_object,
    parse_timestamp,
    validate_mapping,
    validate_observation,
)


STATIC_DIR = Path(__file__).with_name("static")


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


def load_json(value: str) -> dict[str, Any]:
    return json.loads(value)


def current_association(
    connection: sqlite3.Connection, reported_identifier: str, observed_at_ms: int
) -> dict[str, str] | None:
    row = connection.execute(
        """
        SELECT aircraft_id, mapping_id
        FROM identity_mappings
        WHERE reported_identifier = ?
          AND valid_from_ms <= ?
          AND (valid_to_ms IS NULL OR valid_to_ms > ?)
        LIMIT 1
        """,
        (reported_identifier, observed_at_ms, observed_at_ms),
    ).fetchone()
    if row is None:
        return None
    return {"aircraft_id": row["aircraft_id"], "mapping_id": row["mapping_id"]}


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

    @app.exception_handler(InputValidationError)
    async def input_validation_handler(
        _request: Request, exc: InputValidationError
    ) -> JSONResponse:
        return error_response(400, "invalid_request", "Request validation failed", exc.details)

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

    @app.post("/observations", tags=["ingestion"])
    async def post_observation(request: Request) -> JSONResponse:
        payload = parse_json_object(await request.body())
        values = validate_observation(payload)
        original_json = dump_json(payload)

        with serialized_write(resolved_db_path) as connection:
            existing = connection.execute(
                "SELECT original_json, reported_identifier, observed_at_ms FROM observations WHERE observation_id = ?",
                (values["observation_id"],),
            ).fetchone()
            if existing is not None:
                if not json_values_equal(load_json(existing["original_json"]), payload):
                    return error_response(
                        409,
                        "id_conflict",
                        "observation_id already exists with different content",
                    )
                association = current_association(
                    connection, existing["reported_identifier"], existing["observed_at_ms"]
                )
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "existing",
                        "observation": load_json(existing["original_json"]),
                        "association": association,
                    },
                )

            connection.execute(
                """
                INSERT INTO observations (
                    observation_id, reported_identifier, observed_at_text, observed_at_ms,
                    latitude, longitude, original_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["observation_id"],
                    values["reported_identifier"],
                    values["observed_at_text"],
                    values["observed_at_ms"],
                    values["latitude"],
                    values["longitude"],
                    original_json,
                ),
            )
            association = current_association(
                connection, values["reported_identifier"], values["observed_at_ms"]
            )
            return JSONResponse(
                status_code=201,
                content={
                    "status": "created",
                    "observation": payload,
                    "association": association,
                },
            )

    @app.post("/identity-mappings", tags=["ingestion"])
    async def post_identity_mapping(request: Request) -> JSONResponse:
        payload = parse_json_object(await request.body())
        values = validate_mapping(payload)
        original_json = dump_json(payload)

        with serialized_write(resolved_db_path) as connection:
            existing = connection.execute(
                "SELECT original_json FROM identity_mappings WHERE mapping_id = ?",
                (values["mapping_id"],),
            ).fetchone()
            if existing is not None:
                if not json_values_equal(load_json(existing["original_json"]), payload):
                    return error_response(
                        409,
                        "id_conflict",
                        "mapping_id already exists with different content",
                    )
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "existing",
                        "identity_mapping": load_json(existing["original_json"]),
                    },
                )

            overlaps = connection.execute(
                """
                SELECT mapping_id
                FROM identity_mappings
                WHERE reported_identifier = ?
                  AND (? IS NULL OR valid_from_ms < ?)
                  AND (valid_to_ms IS NULL OR valid_to_ms > ?)
                ORDER BY mapping_id
                """,
                (
                    values["reported_identifier"],
                    values["valid_to_ms"],
                    values["valid_to_ms"],
                    values["valid_from_ms"],
                ),
            ).fetchall()
            if overlaps:
                return error_response(
                    409,
                    "overlapping_mapping",
                    "Mapping interval overlaps an existing mapping for this reported_identifier",
                    {"conflicting_mapping_ids": [row["mapping_id"] for row in overlaps]},
                )

            try:
                connection.execute(
                    """
                    INSERT INTO identity_mappings (
                        mapping_id, reported_identifier, aircraft_id,
                        valid_from_text, valid_from_ms, valid_to_text, valid_to_ms,
                        original_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values["mapping_id"],
                        values["reported_identifier"],
                        values["aircraft_id"],
                        values["valid_from_text"],
                        values["valid_from_ms"],
                        values["valid_to_text"],
                        values["valid_to_ms"],
                        original_json,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if "overlapping identity mapping" in str(exc):
                    return error_response(
                        409,
                        "overlapping_mapping",
                        "Mapping interval overlaps an existing mapping for this reported_identifier",
                    )
                raise

            return JSONResponse(
                status_code=201,
                content={"status": "created", "identity_mapping": payload},
            )

    @app.get("/observations/{observation_id}", tags=["queries"])
    def get_observation(observation_id: str) -> JSONResponse:
        connection = connect(resolved_db_path)
        try:
            row = connection.execute(
                """
                SELECT original_json, reported_identifier, observed_at_ms
                FROM observations
                WHERE observation_id = ?
                """,
                (observation_id,),
            ).fetchone()
            if row is None:
                return error_response(404, "not_found", "Observation not found")
            association = current_association(
                connection, row["reported_identifier"], row["observed_at_ms"]
            )
            return JSONResponse(
                status_code=200,
                content={
                    "observation": load_json(row["original_json"]),
                    "association": association,
                },
            )
        finally:
            connection.close()

    @app.get("/aircraft/{aircraft_id}/history", tags=["queries"])
    def get_aircraft_history(
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
        if from_ms is not None and to_ms is not None and from_ms >= to_ms:
            raise InputValidationError(
                [{"field": "to", "message": "Must be later than from"}]
            )

        clauses = ["m.aircraft_id = ?"]
        parameters: list[Any] = [aircraft_id]
        if from_ms is not None:
            clauses.append("o.observed_at_ms >= ?")
            parameters.append(from_ms)
        if to_ms is not None:
            clauses.append("o.observed_at_ms < ?")
            parameters.append(to_ms)

        connection = connect(resolved_db_path)
        try:
            rows = connection.execute(
                f"""
                SELECT o.original_json, m.mapping_id
                FROM identity_mappings AS m
                JOIN observations AS o INDEXED BY idx_observations_identifier_time
                  ON o.reported_identifier = m.reported_identifier
                 AND o.observed_at_ms >= m.valid_from_ms
                 AND (m.valid_to_ms IS NULL OR o.observed_at_ms < m.valid_to_ms)
                WHERE {' AND '.join(clauses)}
                ORDER BY o.observed_at_ms ASC, o.observation_id ASC
                """,
                parameters,
            ).fetchall()
        finally:
            connection.close()

        history = [
            {"observation": load_json(row["original_json"]), "mapping_id": row["mapping_id"]}
            for row in rows
        ]
        return JSONResponse(
            status_code=200,
            content={
                "aircraft_id": aircraft_id,
                "filters": {"from": from_, "to": to},
                "count": len(history),
                "history": history,
            },
        )

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def web_interface() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
