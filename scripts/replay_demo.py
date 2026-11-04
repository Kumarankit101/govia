from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def request_json(base_url: str, method: str, path: str, payload: Any | None = None) -> tuple[int, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urlopen(request) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def print_history(base_url: str, aircraft_id: str, label: str) -> list[str]:
    status, body = request_json(base_url, "GET", f"/aircraft/{aircraft_id}/history")
    ids = [item["observation"]["observation_id"] for item in body.get("history", [])]
    print(f"{label}: GET {aircraft_id} -> {status}; reports={ids}")
    if status != 200 or body.get("count") != len(ids):
        raise SystemExit(f"Unexpected history response for {aircraft_id}: {body}")
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the required delayed-mapping scenario")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    observations = json.loads((ROOT / "sample-data/demo-observations.json").read_text())
    mappings = json.loads((ROOT / "sample-data/demo-mappings.json").read_text())

    try:
        print("1. Submit February first, then January, the exact boundary, and a second identifier")
        observation_statuses = []
        for observation in observations:
            status, _ = request_json(args.base_url, "POST", "/observations", observation)
            observation_statuses.append(status)
            print(f"   POST {observation['observation_id']} -> {status}")
            if status not in (200, 201):
                raise SystemExit(f"Observation ingestion failed with HTTP {status}")

        print("2. Before mappings, received reports are unresolved")
        before_1 = print_history(args.base_url, "aircraft-001", "   before mappings")
        before_2 = print_history(args.base_url, "aircraft-002", "   before mappings")
        if all(status == 201 for status in observation_statuses) and (before_1 or before_2):
            print("   note: mappings from an earlier run already exist in this database")

        print("3. Submit delayed identity mappings")
        for mapping in mappings:
            status, _ = request_json(args.base_url, "POST", "/identity-mappings", mapping)
            print(f"   POST {mapping['mapping_id']} -> {status}")
            if status not in (200, 201):
                raise SystemExit(f"Mapping ingestion failed with HTTP {status}")

        print("4. Histories resolve without resubmitting observations")
        resolved_1 = print_history(args.base_url, "aircraft-001", "   combined identifiers")
        resolved_2 = print_history(args.base_url, "aircraft-002", "   February + boundary")
        expected_1 = ["demo-jan-015", "demo-second-identifier"]
        expected_2 = ["demo-boundary", "demo-feb-005"]
        if resolved_1 != expected_1 or resolved_2 != expected_2:
            raise SystemExit("Resolved histories did not match the expected identity/time boundaries")

        print("5. Exact retries return 200 and create nothing new")
        observation_status, _ = request_json(
            args.base_url, "POST", "/observations", observations[0]
        )
        mapping_status, _ = request_json(
            args.base_url, "POST", "/identity-mappings", mappings[0]
        )
        print(f"   observation retry -> {observation_status}")
        print(f"   mapping retry -> {mapping_status}")
        if observation_status != 200 or mapping_status != 200:
            raise SystemExit("Exact retries should return HTTP 200")
        if print_history(args.base_url, "aircraft-001", "   still deduplicated") != expected_1:
            raise SystemExit("Observation retry changed aircraft-001 history")
        if print_history(args.base_url, "aircraft-002", "   still deduplicated") != expected_2:
            raise SystemExit("Observation retry changed aircraft-002 history")
        print("Demo verified successfully.")
    except URLError as exc:
        raise SystemExit(
            f"Could not reach {args.base_url}. Start the service first. ({exc.reason})"
        ) from exc


if __name__ == "__main__":
    main()
