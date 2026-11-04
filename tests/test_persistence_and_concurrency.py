from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from fastapi.testclient import TestClient

from app.main import create_app


def test_data_survives_application_restart(tmp_path, observation, mapping):
    database = tmp_path / "persistent.db"
    with TestClient(create_app(database)) as first:
        assert first.post("/observations", json=observation).status_code == 201
        assert first.post("/identity-mappings", json=mapping).status_code == 201

    with TestClient(create_app(database)) as restarted:
        stored = restarted.get("/observations/obs-001")
        assert stored.status_code == 200
        assert stored.json()["observation"] == observation
        history = restarted.get("/aircraft/aircraft-001/history").json()
        assert history["count"] == 1
        assert history["history"][0]["mapping_id"] == "map-001"


def test_concurrent_overlapping_mappings_cannot_both_be_accepted(tmp_path, mapping):
    app = create_app(tmp_path / "concurrent-mappings.db")
    second = {
        **mapping,
        "mapping_id": "map-002",
        "aircraft_id": "aircraft-002",
        "valid_from": "2026-01-15T00:00:00Z",
        "valid_to": "2026-03-01T00:00:00Z",
    }

    def submit(payload):
        with TestClient(app) as request_client:
            response = request_client.post("/identity-mappings", json=payload)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, (mapping, second)))

    assert sorted(status for status, _ in results) == [201, 409]
    conflict = next(body for status, body in results if status == 409)
    assert conflict["error"]["code"] == "overlapping_mapping"


def test_concurrent_conflicting_observation_ids_preserve_one_complete_record(tmp_path, observation):
    app = create_app(tmp_path / "concurrent-observations.db")
    changed = deepcopy(observation)
    changed["longitude"] = 12.5

    def submit(payload):
        with TestClient(app) as request_client:
            return request_client.post("/observations", json=payload).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(submit, (observation, changed)))
    assert sorted(statuses) == [201, 409]

    with TestClient(app) as request_client:
        stored = request_client.get("/observations/obs-001").json()["observation"]
    assert stored in (observation, changed)


def test_many_concurrent_identical_retries_create_one_record(tmp_path, observation):
    app = create_app(tmp_path / "concurrent-retries.db")

    def submit(_):
        with TestClient(app) as request_client:
            return request_client.post("/observations", json=observation).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(submit, range(16)))
    assert statuses.count(201) == 1
    assert statuses.count(200) == 15
