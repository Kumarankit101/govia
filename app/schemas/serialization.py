from __future__ import annotations

import json

from app.schemas.types import JsonObject


def load_json(value: str) -> JsonObject:
    return json.loads(value)


def dump_json(value: JsonObject) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
