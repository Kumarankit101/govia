from __future__ import annotations

import sqlite3

from app.schemas.types import JsonObject


def find_by_id(connection: sqlite3.Connection, mapping_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT original_json FROM identity_mappings WHERE mapping_id = ?",
        (mapping_id,),
    ).fetchone()


def find_current(
    connection: sqlite3.Connection,
    reported_identifier: str,
    observed_at_ms: int,
) -> sqlite3.Row | None:
    return connection.execute(
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


def find_overlaps(
    connection: sqlite3.Connection,
    reported_identifier: str,
    valid_from_ms: int,
    valid_to_ms: int | None,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT mapping_id
        FROM identity_mappings
        WHERE reported_identifier = ?
          AND (? IS NULL OR valid_from_ms < ?)
          AND (valid_to_ms IS NULL OR valid_to_ms > ?)
        ORDER BY mapping_id
        """,
        (reported_identifier, valid_to_ms, valid_to_ms, valid_from_ms),
    ).fetchall()


def insert(
    connection: sqlite3.Connection,
    values: JsonObject,
    original_json: str,
) -> None:
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
