from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.database import serialized_write
from app.repositories import mappings
from app.schemas.serialization import dump_json
from app.schemas.types import JsonObject
from app.services.errors import ServiceConflictError
from app.services.idempotency import existing_submission_or_none


@dataclass(frozen=True)
class MappingResult:
    identity_mapping: JsonObject
    created: bool = False


def create_mapping(
    db_path: Path,
    payload: JsonObject,
    values: JsonObject,
) -> MappingResult:
    original_json = dump_json(payload)
    with serialized_write(db_path) as connection:
        existing = mappings.find_by_id(connection, values["mapping_id"])
        if existing is not None:
            stored = existing_submission_or_none(
                existing["original_json"],
                payload,
                conflict_message="mapping_id already exists with different content",
            )
            assert stored is not None
            return MappingResult(stored)

        overlaps = mappings.find_overlaps(
            connection,
            values["reported_identifier"],
            values["valid_from_ms"],
            values["valid_to_ms"],
        )
        if overlaps:
            raise ServiceConflictError(
                "overlapping_mapping",
                "Mapping interval overlaps an existing mapping for this reported_identifier",
                {"conflicting_mapping_ids": [row["mapping_id"] for row in overlaps]},
            )

        try:
            mappings.insert(connection, values, original_json)
        except sqlite3.IntegrityError as exc:
            if "overlapping identity mapping" in str(exc):
                raise ServiceConflictError(
                    "overlapping_mapping",
                    "Mapping interval overlaps an existing mapping for this reported_identifier",
                ) from exc
            raise

        return MappingResult(payload, created=True)
