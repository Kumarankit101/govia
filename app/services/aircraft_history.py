from __future__ import annotations

from pathlib import Path

from app.database import connect
from app.repositories import observations
from app.schemas.serialization import load_json
from app.schemas.types import JsonObject


def get_aircraft_history(
    db_path: Path,
    aircraft_id: str,
    from_ms: int | None = None,
    to_ms: int | None = None,
) -> list[JsonObject]:
    connection = connect(db_path)
    try:
        rows = observations.find_aircraft_history(
            connection,
            aircraft_id,
            from_ms,
            to_ms,
        )
    finally:
        connection.close()

    return [
        {"observation": load_json(row["original_json"]), "mapping_id": row["mapping_id"]}
        for row in rows
    ]
