from __future__ import annotations

from app.schemas.serialization import load_json
from app.schemas.types import JsonObject
from app.schemas.validation import json_values_equal, parse_timestamp
from app.services.errors import ServiceConflictError


def existing_submission_or_none(
    original_json: str | None,
    submitted: JsonObject,
    *,
    conflict_message: str,
    timestamp_fields: tuple[str, ...] = (),
) -> JsonObject | None:
    """Return the stored payload for an equivalent retry or raise for changed content."""
    if original_json is None:
        return None
    stored = load_json(original_json)
    if not submissions_equal(stored, submitted, timestamp_fields):
        raise ServiceConflictError("id_conflict", conflict_message)
    return stored


def submissions_equal(
    stored: JsonObject,
    submitted: JsonObject,
    timestamp_fields: tuple[str, ...],
) -> bool:
    if stored.keys() != submitted.keys():
        return False

    for field in stored:
        if field not in timestamp_fields:
            if not json_values_equal(stored[field], submitted[field]):
                return False
            continue

        stored_value = stored[field]
        submitted_value = submitted[field]
        if stored_value is None or submitted_value is None:
            if stored_value is not submitted_value:
                return False
            continue

        _, stored_ms = parse_timestamp(stored_value, field)
        _, submitted_ms = parse_timestamp(submitted_value, field)
        if stored_ms != submitted_ms:
            return False

    return True
