from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.database import connect, initialize_database
from app.schemas.serialization import dump_json
from app.schemas.validation import validate_mapping, validate_observation


DEFAULT_OUTPUT = Path("data/govia-scale.db")
DEFAULT_OBSERVATIONS = 100_000
DEFAULT_MAPPINGS = 10_000
INTERVALS_PER_IDENTIFIER = 10
INTERVAL_DAYS = 10
BASE_INSTANT = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _timestamp(instant: datetime, style: int, *, allow_fraction: bool = True) -> str:
    base = instant.strftime("%Y-%m-%dT%H:%M:%S")
    if not allow_fraction:
        return f"{base}Z" if style % 2 == 0 else f"{base}+00:00"
    return (
        f"{base}Z",
        f"{base}+00:00",
        f"{base}.1Z",
        f"{base}.12+00:00",
        f"{base}.123Z",
    )[style % 5]


def _coordinates(sequence: int, identifier_index: int) -> tuple[float, float]:
    if sequence % 100 == 0:
        return -90.0, -180.0
    if sequence % 100 == 1:
        return 90.0, 180.0
    latitude = ((identifier_index * 37 + sequence * 17) % 17_800) / 100 - 89
    longitude = ((identifier_index * 53 + sequence * 29) % 35_800) / 100 - 179
    return round(latitude, 6), round(longitude, 6)


def _metadata(sequence: int, identifier_index: int) -> dict[str, Any] | None:
    mode = sequence % 6
    if mode == 0:
        return None  # Omitted metadata is intentionally different from {}.
    if mode == 1:
        return {}
    if mode == 2:
        return {
            "source": f"receiver-{identifier_index % 97:02d}",
            "quality": {"score": round((sequence % 101) / 100, 2), "reviewed": False},
        }
    if mode == 3:
        return {
            "nested": [{"value": None}, [True, False, sequence]],
            "labels": ["synthetic", "boundary" if sequence % 10 == 0 else "interior"],
        }
    if mode == 4:
        return {"message": "case-sensitive ✓", "empty": "", "reading": -1.25}
    return {
        "tags": ["load-test", f"identifier-{identifier_index:04d}"],
        "payload": {"array_order_matters": [1, "1", True, None]},
    }


def mapping_payloads(mapping_count: int) -> Iterator[dict[str, Any]]:
    if mapping_count < 1:
        return
    identifier_count = (mapping_count + INTERVALS_PER_IDENTIFIER - 1) // INTERVALS_PER_IDENTIFIER
    for mapping_index in range(mapping_count):
        identifier_index = mapping_index // INTERVALS_PER_IDENTIFIER
        interval_index = mapping_index % INTERVALS_PER_IDENTIFIER
        group_end = min(
            (identifier_index + 1) * INTERVALS_PER_IDENTIFIER,
            mapping_count,
        )
        is_last_for_identifier = mapping_index == group_end - 1
        valid_from = BASE_INSTANT + timedelta(days=interval_index * INTERVAL_DAYS)
        valid_to = valid_from + timedelta(days=INTERVAL_DAYS)
        yield {
            "mapping_id": f"map-{mapping_index:06d}",
            "reported_identifier": f"RID-{identifier_index:05d}",
            # Aircraft are shared between identifiers and change between intervals.
            "aircraft_id": f"aircraft-{(identifier_index * 7 + interval_index) % 2500:05d}",
            "valid_from": _timestamp(valid_from, mapping_index, allow_fraction=False),
            "valid_to": (
                None
                if is_last_for_identifier
                else _timestamp(valid_to, mapping_index + 1, allow_fraction=False)
            ),
        }


def observation_payloads(
    observation_count: int,
    mapping_count: int,
) -> Iterator[dict[str, Any]]:
    if observation_count < 1:
        return
    identifier_count = max(
        1,
        (mapping_count + INTERVALS_PER_IDENTIFIER - 1) // INTERVALS_PER_IDENTIFIER,
    )
    for observation_index in range(observation_count):
        identifier_index = observation_index % identifier_count
        sequence = observation_index // identifier_count
        instant = BASE_INSTANT + timedelta(days=sequence % 100)
        latitude, longitude = _coordinates(sequence, identifier_index)
        # One record per identifier is deliberately unresolved.
        identifier = (
            f"UNMAPPED-{identifier_index:05d}"
            if sequence % 100 == 99
            else f"RID-{identifier_index:05d}"
        )
        payload: dict[str, Any] = {
            "observation_id": f"obs-{observation_index:07d}",
            "reported_identifier": identifier,
            # Exact ten-day boundaries use whole seconds; other records cover all
            # accepted timestamp spellings and fractional precisions.
            "observed_at": _timestamp(
                instant,
                sequence,
                allow_fraction=sequence % 10 != 0,
            ),
            "latitude": latitude,
            "longitude": longitude,
        }
        metadata = _metadata(sequence, identifier_index)
        if metadata is not None:
            payload["metadata"] = metadata
        yield payload


def _mapping_row(payload: dict[str, Any]) -> tuple[Any, ...]:
    values = validate_mapping(payload)
    return (
        values["mapping_id"],
        values["reported_identifier"],
        values["aircraft_id"],
        values["valid_from_text"],
        values["valid_from_ms"],
        values["valid_to_text"],
        values["valid_to_ms"],
        dump_json(payload),
    )


def _observation_row(payload: dict[str, Any]) -> tuple[Any, ...]:
    values = validate_observation(payload)
    return (
        values["observation_id"],
        values["reported_identifier"],
        values["observed_at_text"],
        values["observed_at_ms"],
        values["latitude"],
        values["longitude"],
        dump_json(payload),
    )


def _batches(values: Iterator[dict[str, Any]], size: int = 2_000) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for value in values:
        batch.append(value)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def _populate(path: Path, observation_count: int, mapping_count: int) -> None:
    initialize_database(path)
    connection = connect(path)
    try:
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("BEGIN IMMEDIATE")
        for batch in _batches(mapping_payloads(mapping_count)):
            connection.executemany(
                """
                INSERT INTO identity_mappings (
                    mapping_id, reported_identifier, aircraft_id,
                    valid_from_text, valid_from_ms, valid_to_text, valid_to_ms,
                    original_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (_mapping_row(payload) for payload in batch),
            )
        for batch in _batches(observation_payloads(observation_count, mapping_count)):
            connection.executemany(
                """
                INSERT INTO observations (
                    observation_id, reported_identifier, observed_at_text, observed_at_ms,
                    latitude, longitude, original_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (_observation_row(payload) for payload in batch),
            )
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def inspect_database(path: Path) -> dict[str, Any]:
    connection = connect(path)
    try:
        observations = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        mappings = connection.execute("SELECT COUNT(*) FROM identity_mappings").fetchone()[0]
        unresolved = connection.execute(
            """
            SELECT COUNT(*)
            FROM observations AS o
            WHERE NOT EXISTS (
                SELECT 1 FROM identity_mappings AS m
                WHERE m.reported_identifier = o.reported_identifier
                  AND m.valid_from_ms <= o.observed_at_ms
                  AND (m.valid_to_ms IS NULL OR m.valid_to_ms > o.observed_at_ms)
            )
            """
        ).fetchone()[0]
        open_ended = connection.execute(
            "SELECT COUNT(*) FROM identity_mappings WHERE valid_to_ms IS NULL"
        ).fetchone()[0]
        return {
            "database": str(path.resolve()),
            "observations": observations,
            "mappings": mappings,
            "unresolved_observations": unresolved,
            "open_ended_mappings": open_ended,
            "size_bytes": path.stat().st_size,
        }
    finally:
        connection.close()


def generate_database(
    path: Path,
    *,
    observation_count: int = DEFAULT_OBSERVATIONS,
    mapping_count: int = DEFAULT_MAPPINGS,
    replace: bool = False,
) -> dict[str, Any]:
    if observation_count < 0 or mapping_count < 1:
        raise ValueError("observation_count must be nonnegative and mapping_count must be positive")
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise FileExistsError(f"{path} already exists; pass --replace to replace it")
    if path.exists() and replace:
        # A clean WAL checkpoint distinguishes harmless leftover sidecars from a
        # database that is actively busy. The final rename remains atomic.
        existing = connect(path)
        try:
            checkpoint = existing.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        finally:
            existing.close()
        if checkpoint[0] != 0:
            raise RuntimeError(f"{path} is busy; stop the service before replacing it")

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink()
    try:
        _populate(temporary_path, observation_count, mapping_count)
        summary = inspect_database(temporary_path)
        if summary["observations"] != observation_count or summary["mappings"] != mapping_count:
            raise RuntimeError(f"generated row counts do not match the request: {summary}")
        for suffix in ("-wal", "-shm"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)
        os.replace(temporary_path, path)
        return inspect_database(path)
    finally:
        temporary_path.unlink(missing_ok=True)
        Path(f"{temporary_path}-wal").unlink(missing_ok=True)
        Path(f"{temporary_path}-shm").unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a deterministic SQLite dataset for Govia scale and rule testing"
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--observations", type=int, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--mappings", type=int, default=DEFAULT_MAPPINGS)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="atomically replace an existing database (the service must be stopped)",
    )
    args = parser.parse_args()
    summary = generate_database(
        args.database,
        observation_count=args.observations,
        mapping_count=args.mappings,
        replace=args.replace,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
