from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Any

from app.schemas.types import JsonObject, ValidationDetail


UTC_TIMESTAMP = re.compile(
    r"^(?P<base>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
    r"(?P<fraction>\.\d{1,3})?(?P<zone>Z|\+00:00)$"
)
EPOCH_ORDINAL = date(1970, 1, 1).toordinal()
OBSERVATION_FIELDS = {
    "observation_id",
    "reported_identifier",
    "observed_at",
    "latitude",
    "longitude",
    "metadata",
}
OBSERVATION_REQUIRED = OBSERVATION_FIELDS - {"metadata"}
MAPPING_FIELDS = {
    "mapping_id",
    "reported_identifier",
    "aircraft_id",
    "valid_from",
    "valid_to",
}


class InputValidationError(Exception):
    def __init__(self, details: list[ValidationDetail]) -> None:
        super().__init__("Request validation failed")
        self.details = details


def parse_json_object(raw_body: bytes) -> JsonObject:
    def reject_constant(value: str) -> None:
        raise ValueError(f"{value} is not valid JSON")

    try:
        value = json.loads(raw_body.decode("utf-8"), parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise InputValidationError(
            [{"field": "$", "message": f"Body must be valid JSON: {exc}"}]
        ) from exc
    if not isinstance(value, dict):
        raise InputValidationError(
            [{"field": "$", "message": "Request body must be a JSON object"}]
        )
    return value


def _timestamp_to_milliseconds(
    value: Any, field: str
) -> tuple[str | None, int | None, list[ValidationDetail]]:
    if not isinstance(value, str):
        return None, None, [{"field": field, "message": "Must be a UTC RFC3339 string"}]
    match = UTC_TIMESTAMP.fullmatch(value)
    if not match:
        return None, None, [
            {
                "field": field,
                "message": "Must end in Z or +00:00 and use at most three fractional digits",
            }
        ]
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, None, [{"field": field, "message": "Must be a valid calendar timestamp"}]

    milliseconds = (
        (parsed.date().toordinal() - EPOCH_ORDINAL) * 86_400_000
        + parsed.hour * 3_600_000
        + parsed.minute * 60_000
        + parsed.second * 1_000
        + parsed.microsecond // 1_000
    )
    return value, milliseconds, []


def parse_timestamp(value: Any, field: str) -> tuple[str, int]:
    original, milliseconds, errors = _timestamp_to_milliseconds(value, field)
    if errors:
        raise InputValidationError(errors)
    assert original is not None and milliseconds is not None
    return original, milliseconds


def _nonempty_string(
    payload: JsonObject, field: str, errors: list[ValidationDetail]
) -> None:
    value = payload.get(field)
    if not isinstance(value, str) or value == "":
        errors.append({"field": field, "message": "Must be a nonempty string"})


def _check_fields(
    payload: JsonObject,
    allowed: set[str],
    required: set[str],
    errors: list[ValidationDetail],
) -> None:
    for field in sorted(required - payload.keys()):
        errors.append({"field": field, "message": "Field is required"})
    for field in sorted(payload.keys() - allowed):
        errors.append({"field": field, "message": "Unexpected top-level field"})


def validate_coordinates(payload: JsonObject, errors: list[ValidationDetail]) -> None:
    for field, minimum, maximum in (
        ("latitude", -90, 90),
        ("longitude", -180, 180),
    ):
        if field not in payload:
            continue
        value = payload[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append({"field": field, "message": "Must be a finite JSON number"})
        # Large Python integers are finite but can overflow when coerced to float.
        elif isinstance(value, float) and not math.isfinite(value):
            errors.append({"field": field, "message": "Must be a finite JSON number"})
        elif not minimum <= value <= maximum:
            errors.append(
                {"field": field, "message": f"Must be between {minimum} and {maximum}, inclusive"}
            )


def validate_metadata(payload: JsonObject, errors: list[ValidationDetail]) -> None:
    if "metadata" in payload and not isinstance(payload["metadata"], dict):
        errors.append({"field": "metadata", "message": "Must be a JSON object when provided"})


def validate_interval(
    from_ms: int | None,
    to_ms: int | None,
    *,
    from_field: str,
    to_field: str,
    errors: list[ValidationDetail],
) -> None:
    if from_ms is not None and to_ms is not None and to_ms <= from_ms:
        errors.append({"field": to_field, "message": f"Must be later than {from_field}"})


def validate_observation(payload: JsonObject) -> JsonObject:
    errors: list[ValidationDetail] = []
    _check_fields(payload, OBSERVATION_FIELDS, OBSERVATION_REQUIRED, errors)
    for field in ("observation_id", "reported_identifier"):
        if field in payload:
            _nonempty_string(payload, field, errors)

    timestamp_text: str | None = None
    timestamp_ms: int | None = None
    if "observed_at" in payload:
        timestamp_text, timestamp_ms, timestamp_errors = _timestamp_to_milliseconds(
            payload["observed_at"], "observed_at"
        )
        errors.extend(timestamp_errors)

    validate_coordinates(payload, errors)
    validate_metadata(payload, errors)

    if errors:
        raise InputValidationError(errors)
    assert timestamp_text is not None and timestamp_ms is not None
    return {
        "observation_id": payload["observation_id"],
        "reported_identifier": payload["reported_identifier"],
        "observed_at_text": timestamp_text,
        "observed_at_ms": timestamp_ms,
        "latitude": payload["latitude"],
        "longitude": payload["longitude"],
    }


def validate_mapping(payload: JsonObject) -> JsonObject:
    errors: list[ValidationDetail] = []
    _check_fields(payload, MAPPING_FIELDS, MAPPING_FIELDS, errors)
    for field in ("mapping_id", "reported_identifier", "aircraft_id"):
        if field in payload:
            _nonempty_string(payload, field, errors)

    from_text: str | None = None
    from_ms: int | None = None
    if "valid_from" in payload:
        from_text, from_ms, timestamp_errors = _timestamp_to_milliseconds(
            payload["valid_from"], "valid_from"
        )
        errors.extend(timestamp_errors)

    to_text: str | None = None
    to_ms: int | None = None
    if "valid_to" in payload and payload["valid_to"] is not None:
        to_text, to_ms, timestamp_errors = _timestamp_to_milliseconds(
            payload["valid_to"], "valid_to"
        )
        errors.extend(timestamp_errors)

    validate_interval(
        from_ms,
        to_ms,
        from_field="valid_from",
        to_field="valid_to",
        errors=errors,
    )

    if errors:
        raise InputValidationError(errors)
    assert from_text is not None and from_ms is not None
    return {
        "mapping_id": payload["mapping_id"],
        "reported_identifier": payload["reported_identifier"],
        "aircraft_id": payload["aircraft_id"],
        "valid_from_text": from_text,
        "valid_from_ms": from_ms,
        "valid_to_text": to_text,
        "valid_to_ms": to_ms,
    }


def json_values_equal(left: Any, right: Any) -> bool:
    """Compare JSON values while keeping booleans distinct from numbers."""
    left_number = isinstance(left, (int, float)) and not isinstance(left, bool)
    right_number = isinstance(right, (int, float)) and not isinstance(right, bool)
    if left_number or right_number:
        return left_number and right_number and left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            json_values_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            json_values_equal(a, b) for a, b in zip(left, right)
        )
    return left == right
