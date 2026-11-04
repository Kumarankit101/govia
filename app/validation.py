"""Backward-compatible imports for the validation module's original location."""

from app.schemas.serialization import dump_json, load_json
from app.schemas.validation import (
    EPOCH_ORDINAL,
    MAPPING_FIELDS,
    OBSERVATION_FIELDS,
    OBSERVATION_REQUIRED,
    UTC_TIMESTAMP,
    InputValidationError,
    json_values_equal,
    parse_json_object,
    parse_timestamp,
    validate_coordinates,
    validate_interval,
    validate_mapping,
    validate_metadata,
    validate_observation,
)

__all__ = [
    "EPOCH_ORDINAL",
    "InputValidationError",
    "MAPPING_FIELDS",
    "OBSERVATION_FIELDS",
    "OBSERVATION_REQUIRED",
    "UTC_TIMESTAMP",
    "dump_json",
    "json_values_equal",
    "load_json",
    "parse_json_object",
    "parse_timestamp",
    "validate_coordinates",
    "validate_interval",
    "validate_mapping",
    "validate_metadata",
    "validate_observation",
]
