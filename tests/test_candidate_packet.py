from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.database import connect
from app.main import create_app


PACKET = Path(__file__).resolve().parents[1] / "candidate-packet"


def load_json(name: str):
    return json.loads((PACKET / name).read_text(encoding="utf-8"))


def load_steps() -> list[dict]:
    return [
        json.loads(line)
        for line in (PACKET / "arrival-stream.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]


def send(client: TestClient, step: dict):
    content = step.get("raw_body")
    if content is None and "body" in step:
        content = json.dumps(step["body"], ensure_ascii=False)
    return client.request(
        step["method"],
        step["path"],
        content=content,
        headers={"Content-Type": "application/json"},
    )


def history_rows(body: dict) -> list[dict[str, str]]:
    return [
        {
            "observation_id": item["observation"]["observation_id"],
            "mapping_id": item["mapping_id"],
            "observed_at": item["observation"]["observed_at"],
        }
        for item in body["history"]
    ]


def test_candidate_packet_statuses_and_content(tmp_path):
    expected_statuses = {
        item["step_id"]: item["expected_status"]
        for item in load_json("expected-statuses.json")
    }
    checkpoints = {
        item["step_id"]: item["expected_rows"]
        for item in load_json("history-checkpoints.json")
    }
    accepted_observations: dict[str, dict] = {}
    accepted_mappings: dict[str, dict] = {}

    with TestClient(create_app(tmp_path / "packet.db")) as client:
        for step in load_steps():
            response = send(client, step)
            step_id = step["step_id"]
            assert response.status_code == expected_statuses[step_id], step_id

            if response.status_code >= 400:
                assert set(response.json()) == {"error"}, step_id

            if step["method"] == "POST" and "body" in step:
                payload = step["body"]
                if step["path"] == "/observations" and response.status_code in {200, 201, 409}:
                    assert isinstance(payload, dict)
                    record_id = payload["observation_id"]
                    if response.status_code == 201:
                        accepted_observations[record_id] = payload
                        assert response.json()["observation"] == payload
                    elif response.status_code == 200:
                        assert response.json()["observation"] == accepted_observations[record_id]
                    elif response.status_code == 409:
                        stored = client.get(f"/observations/{record_id}")
                        assert stored.json()["observation"] == accepted_observations[record_id]
                elif step["path"] == "/identity-mappings" and response.status_code in {
                    200,
                    201,
                    409,
                }:
                    assert isinstance(payload, dict)
                    record_id = payload["mapping_id"]
                    if response.status_code == 201:
                        accepted_mappings[record_id] = payload
                        assert response.json()["identity_mapping"] == payload
                    elif response.status_code == 200:
                        assert response.json()["identity_mapping"] == accepted_mappings[record_id]

            if step_id in checkpoints:
                body = response.json()
                assert body["count"] == len(body["history"])
                assert history_rows(body) == checkpoints[step_id]

                url = urlsplit(step["path"])
                query = parse_qs(url.query)
                assert body["aircraft_id"] == url.path.split("/")[2]
                assert body["filters"] == {
                    "from": query.get("from", [None])[0],
                    "to": query.get("to", [None])[0],
                }
                for item in body["history"]:
                    observation_id = item["observation"]["observation_id"]
                    assert item["observation"] == accepted_observations[observation_id]

            if step["method"] == "GET" and step["path"].startswith("/observations/"):
                observation_id = step["path"].rsplit("/", 1)[-1]
                if response.status_code == 200:
                    assert response.json()["observation"] == accepted_observations[observation_id]


def test_candidate_packet_concurrent_cases(tmp_path):
    app = create_app(tmp_path / "packet-races.db")

    for case in load_json("concurrent-cases.json"):
        barrier = Barrier(len(case["requests"]))

        def run(step):
            with TestClient(app) as client:
                barrier.wait(timeout=10)
                response = send(client, step)
                return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=len(case["requests"])) as pool:
            results = list(pool.map(run, case["requests"]))

        assert sorted(status for status, _ in results) == case["expected_status_multiset"]

        created = next(body for status, body in results if status == 201)
        if case["requests"][0]["path"] == "/observations":
            observation_id = case["requests"][0]["body"]["observation_id"]
            with TestClient(app) as client:
                stored = client.get(f"/observations/{observation_id}")
            assert stored.json()["observation"] == created["observation"]
        else:
            assert created["identity_mapping"] in [item["body"] for item in case["requests"]]

    connection = connect(app.state.db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM observations WHERE observation_id = 'race-same'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM observations WHERE observation_id = 'race-conflict'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM identity_mappings WHERE reported_identifier = 'RACE03'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM identity_mappings WHERE mapping_id = 'race-map-same'"
        ).fetchone()[0] == 1
    finally:
        connection.close()
