from __future__ import annotations

from app.schemas.serialization import load_json
from app.schemas.types import JsonObject
from app.schemas.validation import json_values_equal
from app.services.errors import ServiceConflictError


def existing_submission_or_none(
    original_json: str | None,
    submitted: JsonObject,
    *,
    conflict_message: str,
) -> JsonObject | None:
    """Return the stored payload for an identical retry or raise for changed content."""
    if original_json is None:
        return None
    stored = load_json(original_json)
    if not json_values_equal(stored, submitted):
        raise ServiceConflictError("id_conflict", conflict_message)
    return stored
