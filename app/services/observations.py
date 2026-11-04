from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.database import connect, serialized_write
from app.repositories import observations
from app.schemas.serialization import dump_json, load_json
from app.schemas.types import JsonObject
from app.services.idempotency import existing_submission_or_none
from app.services.identity_resolution import current_association


@dataclass(frozen=True)
class ObservationResult:
    observation: JsonObject
    association: dict[str, str] | None
    created: bool = False


def create_observation(
    db_path: Path,
    payload: JsonObject,
    values: JsonObject,
) -> ObservationResult:
    original_json = dump_json(payload)
    with serialized_write(db_path) as connection:
        existing = observations.find_by_id(connection, values["observation_id"])
        if existing is not None:
            stored = existing_submission_or_none(
                existing["original_json"],
                payload,
                conflict_message="observation_id already exists with different content",
                timestamp_fields=("observed_at",),
            )
            assert stored is not None
            association = current_association(
                connection,
                existing["reported_identifier"],
                existing["observed_at_ms"],
            )
            return ObservationResult(stored, association)

        observations.insert(connection, values, original_json)
        association = current_association(
            connection,
            values["reported_identifier"],
            values["observed_at_ms"],
        )
        return ObservationResult(payload, association, created=True)


def get_observation(db_path: Path, observation_id: str) -> ObservationResult | None:
    connection = connect(db_path)
    try:
        row = observations.find_by_id(connection, observation_id)
        if row is None:
            return None
        association = current_association(
            connection,
            row["reported_identifier"],
            row["observed_at_ms"],
        )
        return ObservationResult(load_json(row["original_json"]), association)
    finally:
        connection.close()
