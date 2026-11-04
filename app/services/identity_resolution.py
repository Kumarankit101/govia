from __future__ import annotations

import sqlite3

from app.repositories import mappings


def current_association(
    connection: sqlite3.Connection,
    reported_identifier: str,
    observed_at_ms: int,
) -> dict[str, str] | None:
    row = mappings.find_current(connection, reported_identifier, observed_at_ms)
    if row is None:
        return None
    return {"aircraft_id": row["aircraft_id"], "mapping_id": row["mapping_id"]}
