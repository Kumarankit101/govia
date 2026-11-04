from __future__ import annotations

from copy import deepcopy


def report(observation_id: str, identifier: str, timestamp: str) -> dict:
    return {
        "observation_id": observation_id,
        "reported_identifier": identifier,
        "observed_at": timestamp,
        "latitude": 10,
        "longitude": 20,
        "metadata": {"sequence": observation_id},
    }


def identity_mapping(
    mapping_id: str,
    identifier: str,
    aircraft_id: str,
    valid_from: str,
    valid_to: str | None,
) -> dict:
    return {
        "mapping_id": mapping_id,
        "reported_identifier": identifier,
        "aircraft_id": aircraft_id,
        "valid_from": valid_from,
        "valid_to": valid_to,
    }


def test_late_mappings_and_out_of_order_reports(client):
    february = report("obs-feb", "A1B2C3", "2026-02-04T10:00:00Z")
    january = report("obs-jan", "A1B2C3", "2026-01-10T10:00:00Z")

    assert client.post("/observations", json=february).status_code == 201
    assert client.post("/observations", json=january).status_code == 201
    assert client.get("/aircraft/aircraft-001/history").json()["history"] == []

    january_mapping = identity_mapping(
        "map-jan", "A1B2C3", "aircraft-001", "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"
    )
    february_mapping = identity_mapping(
        "map-feb", "A1B2C3", "aircraft-002", "2026-02-01T00:00:00Z", None
    )
    assert client.post("/identity-mappings", json=january_mapping).status_code == 201
    assert client.post("/identity-mappings", json=february_mapping).status_code == 201

    history_1 = client.get("/aircraft/aircraft-001/history").json()["history"]
    history_2 = client.get("/aircraft/aircraft-002/history").json()["history"]
    assert [(item["observation"]["observation_id"], item["mapping_id"]) for item in history_1] == [
        ("obs-jan", "map-jan")
    ]
    assert [(item["observation"]["observation_id"], item["mapping_id"]) for item in history_2] == [
        ("obs-feb", "map-feb")
    ]


def test_half_open_mapping_boundary(client):
    before = report("obs-before", "A1B2C3", "2026-01-31T23:59:59.999Z")
    boundary = report("obs-boundary", "A1B2C3", "2026-02-01T00:00:00+00:00")
    for item in (before, boundary):
        assert client.post("/observations", json=item).status_code == 201
    assert client.post(
        "/identity-mappings",
        json=identity_mapping(
            "map-jan", "A1B2C3", "aircraft-001", "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"
        ),
    ).status_code == 201
    assert client.post(
        "/identity-mappings",
        json=identity_mapping(
            "map-feb", "A1B2C3", "aircraft-002", "2026-02-01T00:00:00Z", None
        ),
    ).status_code == 201

    assert [x["observation"]["observation_id"] for x in client.get("/aircraft/aircraft-001/history").json()["history"]] == ["obs-before"]
    assert [x["observation"]["observation_id"] for x in client.get("/aircraft/aircraft-002/history").json()["history"]] == ["obs-boundary"]


def test_history_combines_identifiers_and_orders_ties(client):
    mappings = [
        identity_mapping("map-a", "IDENT-A", "aircraft-001", "2026-01-01T00:00:00Z", None),
        identity_mapping("map-b", "IDENT-B", "aircraft-001", "2026-01-01T00:00:00Z", None),
    ]
    for item in mappings:
        assert client.post("/identity-mappings", json=item).status_code == 201
    reports = [
        report("obs-z", "IDENT-A", "2026-01-03T00:00:00Z"),
        report("obs-b", "IDENT-B", "2026-01-02T00:00:00Z"),
        report("obs-a", "IDENT-A", "2026-01-02T00:00:00+00:00"),
    ]
    for item in reports:
        assert client.post("/observations", json=item).status_code == 201

    body = client.get("/aircraft/aircraft-001/history").json()
    assert body["count"] == 3
    assert [x["observation"]["observation_id"] for x in body["history"]] == [
        "obs-a",
        "obs-b",
        "obs-z",
    ]
    assert {x["mapping_id"] for x in body["history"]} == {"map-a", "map-b"}


def test_history_filters_are_half_open(client):
    assert client.post(
        "/identity-mappings",
        json=identity_mapping("map", "IDENT", "aircraft", "2026-01-01T00:00:00Z", None),
    ).status_code == 201
    for timestamp, suffix in (
        ("2026-01-01T00:00:00Z", "start"),
        ("2026-01-02T00:00:00Z", "middle"),
        ("2026-01-03T00:00:00Z", "end"),
    ):
        client.post("/observations", json=report(f"obs-{suffix}", "IDENT", timestamp))

    response = client.get(
        "/aircraft/aircraft/history",
        params={"from": "2026-01-02T00:00:00+00:00", "to": "2026-01-03T00:00:00.000Z"},
    )
    assert response.status_code == 200
    assert [x["observation"]["observation_id"] for x in response.json()["history"]] == ["obs-middle"]

    invalid = client.get(
        "/aircraft/aircraft/history",
        params={"from": "2026-01-03T00:00:00Z", "to": "2026-01-03T00:00:00+00:00"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "invalid_request"


def test_original_report_and_current_association(client, observation, mapping):
    original = deepcopy(observation)
    original["metadata"] = {"nested": {"values": [1, "1", True, None, {"x": 2.5}]}}
    created = client.post("/observations", json=original)
    assert created.status_code == 201
    assert created.json()["association"] is None
    assert created.json()["observation"] == original

    unresolved = client.get("/observations/obs-001")
    assert unresolved.status_code == 200
    assert unresolved.json() == {"observation": original, "association": None}

    client.post("/identity-mappings", json=mapping)
    resolved = client.get("/observations/obs-001")
    assert resolved.json()["observation"] == original
    assert resolved.json()["association"] == {
        "aircraft_id": "aircraft-001",
        "mapping_id": "map-001",
    }


def test_unknown_aircraft_is_empty_and_missing_observation_is_404(client):
    history = client.get("/aircraft/does-not-exist/history")
    assert history.status_code == 200
    assert history.json()["count"] == 0
    assert history.json()["history"] == []

    missing = client.get("/observations/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
