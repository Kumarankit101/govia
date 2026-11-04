from __future__ import annotations

import sqlite3
from typing import Any

from app.schemas.types import JsonObject


def find_by_id(
    connection: sqlite3.Connection, observation_id: str
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT original_json, reported_identifier, observed_at_ms
        FROM observations
        WHERE observation_id = ?
        """,
        (observation_id,),
    ).fetchone()


def insert(
    connection: sqlite3.Connection,
    values: JsonObject,
    original_json: str,
) -> None:
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


def find_aircraft_history(
    connection: sqlite3.Connection,
    aircraft_id: str,
    from_ms: int | None,
    to_ms: int | None,
) -> list[sqlite3.Row]:
    clauses = ["m.aircraft_id = ?"]
    parameters: list[Any] = [aircraft_id]
    if from_ms is not None:
        clauses.append("o.observed_at_ms >= ?")
        parameters.append(from_ms)
    if to_ms is not None:
        clauses.append("o.observed_at_ms < ?")
        parameters.append(to_ms)

    return connection.execute(
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
