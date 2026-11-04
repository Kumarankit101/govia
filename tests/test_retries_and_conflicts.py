from __future__ import annotations

from copy import deepcopy


def test_observation_identical_retry_ignores_nested_key_order_and_equal_numbers(client, observation):
    first = deepcopy(observation)
    first["latitude"] = 1
    first["metadata"] = {"outer": {"a": 1, "b": [1, 2]}, "enabled": True}
    retry = {
        "metadata": {"enabled": True, "outer": {"b": [1.0, 2.0], "a": 1.0}},
        "longitude": first["longitude"],
        "latitude": 1.0,
        "observed_at": first["observed_at"],
        "reported_identifier": first["reported_identifier"],
        "observation_id": first["observation_id"],
    }

    assert client.post("/observations", json=first).status_code == 201
    response = client.post("/observations", json=retry)
    assert response.status_code == 200
    assert response.json()["status"] == "existing"
    assert response.json()["observation"] == first

    history_count = client.get("/observations/obs-001").json()["observation"]["observation_id"]
    assert history_count == "obs-001"


def test_observation_same_id_different_content_conflicts_without_overwrite(client, observation):
    assert client.post("/observations", json=observation).status_code == 201
    changed = deepcopy(observation)
    changed["longitude"] = 12
    conflict = client.post("/observations", json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "id_conflict"
    assert client.get("/observations/obs-001").json()["observation"] == observation


def test_observation_retry_compares_timestamp_by_instant_and_preserves_original(client, observation):
    original = deepcopy(observation)
    original["observed_at"] = "2026-01-10T10:00:00.1Z"
    assert client.post("/observations", json=original).status_code == 201

    retry = deepcopy(original)
    retry["observed_at"] = "2026-01-10T10:00:00.100+00:00"
    response = client.post("/observations", json=retry)

    assert response.status_code == 200
    assert response.json()["observation"] == original
    assert client.get("/observations/obs-001").json()["observation"] == original

    different_instant = deepcopy(retry)
    different_instant["observed_at"] = "2026-01-10T10:00:00.101Z"
    assert client.post("/observations", json=different_instant).status_code == 409


def test_json_types_and_metadata_presence_are_content(client, observation):
    without_metadata = {key: value for key, value in observation.items() if key != "metadata"}
    assert client.post("/observations", json=without_metadata).status_code == 201
    with_empty_metadata = {**without_metadata, "metadata": {}}
    assert client.post("/observations", json=with_empty_metadata).status_code == 409

    typed = deepcopy(without_metadata)
    typed["observation_id"] = "typed"
    typed["metadata"] = {"value": 1}
    assert client.post("/observations", json=typed).status_code == 201
    typed["metadata"] = {"value": True}
    assert client.post("/observations", json=typed).status_code == 409


def test_mapping_retry_precedes_overlap_check(client, mapping):
    assert client.post("/identity-mappings", json=mapping).status_code == 201
    reordered = {
        "valid_to": mapping["valid_to"],
        "valid_from": mapping["valid_from"],
        "aircraft_id": mapping["aircraft_id"],
        "reported_identifier": mapping["reported_identifier"],
        "mapping_id": mapping["mapping_id"],
    }
    retry = client.post("/identity-mappings", json=reordered)
    assert retry.status_code == 200
    assert retry.json()["identity_mapping"] == mapping

def test_mapping_retry_compares_timestamps_by_instant_and_preserves_original(client, mapping):
    assert client.post("/identity-mappings", json=mapping).status_code == 201
    retry_payload = {
        **mapping,
        "valid_from": "2026-01-01T00:00:00.000+00:00",
        "valid_to": "2026-02-01T00:00:00+00:00",
    }

    retry = client.post("/identity-mappings", json=retry_payload)

    assert retry.status_code == 200
    assert retry.json()["identity_mapping"] == mapping

    different_interval = {**retry_payload, "valid_to": "2026-02-01T00:00:00.001Z"}
    assert client.post("/identity-mappings", json=different_interval).status_code == 409


def test_mapping_id_conflict_and_interval_overlap(client, mapping):
    assert client.post("/identity-mappings", json=mapping).status_code == 201
    changed_id_content = deepcopy(mapping)
    changed_id_content["aircraft_id"] = "another-aircraft"
    response = client.post("/identity-mappings", json=changed_id_content)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "id_conflict"

    overlapping = {
        **mapping,
        "mapping_id": "map-overlap",
        "aircraft_id": "another-aircraft",
        "valid_from": "2026-01-15T00:00:00Z",
        "valid_to": "2026-02-15T00:00:00Z",
    }
    response = client.post("/identity-mappings", json=overlapping)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "overlapping_mapping"
    assert response.json()["error"]["details"]["conflicting_mapping_ids"] == ["map-001"]


def test_adjacent_mapping_intervals_are_allowed(client, mapping):
    assert client.post("/identity-mappings", json=mapping).status_code == 201
    adjacent = {
        **mapping,
        "mapping_id": "map-002",
        "aircraft_id": "aircraft-002",
        "valid_from": mapping["valid_to"],
        "valid_to": None,
    }
    assert client.post("/identity-mappings", json=adjacent).status_code == 201
