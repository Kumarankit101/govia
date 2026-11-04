from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    app = create_app(tmp_path / "test.db")
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def observation() -> dict:
    return {
        "observation_id": "obs-001",
        "reported_identifier": "A1B2C3",
        "observed_at": "2026-01-10T10:00:00Z",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "metadata": {
            "altitude_ft": 32000,
            "groundspeed_knots": 450,
            "source": "receiver-17",
        },
    }


@pytest.fixture
def mapping() -> dict:
    return {
        "mapping_id": "map-001",
        "reported_identifier": "A1B2C3",
        "aircraft_id": "aircraft-001",
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": "2026-02-01T00:00:00Z",
    }
