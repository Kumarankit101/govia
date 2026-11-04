from __future__ import annotations

import json

from scripts.generate_scale_data import generate_database, inspect_database


def test_scale_generator_builds_rule_rich_database(tmp_path):
    database = tmp_path / "scale.db"
    summary = generate_database(
        database,
        observation_count=300,
        mapping_count=30,
    )

    assert summary["observations"] == 300
    assert summary["mappings"] == 30
    assert summary["open_ended_mappings"] == 3
    assert summary["unresolved_observations"] == 3

    import sqlite3

    connection = sqlite3.connect(database)
    try:
        reports = [
            json.loads(row[0])
            for row in connection.execute(
                "SELECT original_json FROM observations ORDER BY observation_id LIMIT 18"
            )
        ]
        assert any("metadata" not in report for report in reports)
        assert any(report.get("metadata") == {} for report in reports)
        assert any(report.get("metadata", {}).get("nested") for report in reports)
        assert {reports[0]["latitude"], reports[3]["latitude"]} <= {-90.0, 90.0}
        assert any(report["observed_at"].endswith("+00:00") for report in reports)
        assert any("." in report["observed_at"] for report in reports)

        # A report exactly at the second interval's start belongs only to that
        # interval, proving the generated boundary cases are half-open.
        boundary_mapping = connection.execute(
            """
            SELECT m.mapping_id
            FROM observations AS o
            JOIN identity_mappings AS m
              ON m.reported_identifier = o.reported_identifier
             AND m.valid_from_ms <= o.observed_at_ms
             AND (m.valid_to_ms IS NULL OR m.valid_to_ms > o.observed_at_ms)
            WHERE o.observation_id = 'obs-0000030'
            """
        ).fetchall()
        assert boundary_mapping == [("map-000001",)]
    finally:
        connection.close()

    assert inspect_database(database) == summary


def test_scale_generator_refuses_to_overwrite_without_replace(tmp_path):
    database = tmp_path / "scale.db"
    generate_database(database, observation_count=1, mapping_count=1)

    try:
        generate_database(database, observation_count=2, mapping_count=1)
    except FileExistsError:
        pass
    else:
        raise AssertionError("generator unexpectedly overwrote an existing database")

    replaced = generate_database(
        database,
        observation_count=2,
        mapping_count=1,
        replace=True,
    )
    assert replaced["observations"] == 2
