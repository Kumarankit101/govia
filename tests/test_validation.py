from __future__ import annotations

from copy import deepcopy

import pytest


@pytest.mark.parametrize("latitude", [-90, 90, 0, 1.5])
def test_valid_latitude_boundaries(client, observation, latitude):
    observation["observation_id"] = f"obs-{latitude}"
    observation["latitude"] = latitude
    assert client.post("/observations", json=observation).status_code == 201


@pytest.mark.parametrize("longitude", [-180, 180, 0, 1.5])
def test_valid_longitude_boundaries(client, observation, longitude):
    observation["observation_id"] = f"obs-{longitude}"
    observation["longitude"] = longitude
    assert client.post("/observations", json=observation).status_code == 201


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", -90.001),
        ("latitude", 90.001),
        ("longitude", -180.001),
        ("longitude", 180.001),
        ("latitude", 10**400),
        ("latitude", -(10**400)),
        ("longitude", 10**400),
        ("longitude", -(10**400)),
        ("latitude", "1"),
        ("longitude", True),
    ],
)
def test_invalid_coordinates(client, observation, field, value):
    observation[field] = value
    response = client.post("/observations", json=observation)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-01-10T10:00:00Z",
        "2026-01-10T10:00:00+00:00",
        "2026-01-10T10:00:00.1Z",
        "2026-01-10T10:00:00.12+00:00",
        "2026-01-10T10:00:00.123Z",
    ],
)
def test_supported_timestamp_forms_are_preserved(client, observation, timestamp):
    observation["observation_id"] = timestamp
    observation["observed_at"] = timestamp
    response = client.post("/observations", json=observation)
    assert response.status_code == 201
    assert response.json()["observation"]["observed_at"] == timestamp
    assert client.get(f"/observations/{timestamp}").json()["observation"]["observed_at"] == timestamp


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-01-10T10:00:00",
        "2026-01-10T10:00:00+05:30",
        "2026-01-10T10:00:00.1234Z",
        "2026-02-30T10:00:00Z",
        "2026-01-10T10:00:60Z",
        "2026-01-10 10:00:00Z",
    ],
)
def test_invalid_timestamps(client, observation, timestamp):
    observation["observed_at"] = timestamp
    assert client.post("/observations", json=observation).status_code == 400


def test_metadata_must_be_object_but_can_contain_any_json(client, observation):
    for invalid in (None, [], "value", 1):
        item = deepcopy(observation)
        item["metadata"] = invalid
        assert client.post("/observations", json=item).status_code == 400

    observation["metadata"] = {
        "nested": [{"a": None}, [True, False]],
        "string": "",
        "number": -1.25,
    }
    assert client.post("/observations", json=observation).status_code == 201


def test_required_nonempty_case_sensitive_and_untrimmed_strings(client, observation):
    observation["observation_id"] = ""
    assert client.post("/observations", json=observation).status_code == 400

    observation["observation_id"] = " obs "
    assert client.post("/observations", json=observation).status_code == 201
    assert client.get("/observations/%20obs%20").status_code == 200

    uppercase = deepcopy(observation)
    uppercase["observation_id"] = "OBS"
    lowercase = deepcopy(observation)
    lowercase["observation_id"] = "obs"
    assert client.post("/observations", json=uppercase).status_code == 201
    assert client.post("/observations", json=lowercase).status_code == 201


def test_mapping_requires_valid_to_and_later_end(client, mapping):
    del mapping["valid_to"]
    assert client.post("/identity-mappings", json=mapping).status_code == 400
    mapping["valid_to"] = mapping["valid_from"]
    assert client.post("/identity-mappings", json=mapping).status_code == 400
    mapping["valid_to"] = None
    assert client.post("/identity-mappings", json=mapping).status_code == 201


def test_body_must_be_json_object_and_unexpected_fields_are_rejected(client, observation):
    for raw in (b"[]", b"null", b"not json", b'{"latitude": NaN}'):
        response = client.post(
            "/observations", content=raw, headers={"content-type": "application/json"}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_request"

    observation["unexpected"] = "value"
    assert client.post("/observations", json=observation).status_code == 400
