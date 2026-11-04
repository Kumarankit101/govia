# Govia Aircraft History

FastAPI and SQLite service for ingesting position reports and resolving time-bounded aircraft identities.

## Quick start

Requires Python 3.11+ and no external services.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m scripts.init_db
uvicorn app.main:app --reload
```

Open the [interface](http://127.0.0.1:8000) or [API docs](http://127.0.0.1:8000/docs). The default database is `data/govia.db`. To change it:

```bash
GOVIA_DB_PATH=/absolute/path/to/govia.db uvicorn app.main:app
```

Run all automated tests:

```bash
pytest
```

The 57 tests cover validation, late and out-of-order data, retries, conflicts, boundaries, filtering, ordering, persistence, concurrency, and scale-data integrity.

## Generate the full scale database

```bash
python -m scripts.generate_scale_data
```

Creates `data/govia-scale.db` with 100,000 observations and 10,000 mappings. It does not overwrite an existing file without `--replace`. Custom counts:

```bash
python -m scripts.generate_scale_data \
  --database data/smoke.db --observations 1000 --mappings 100
```

Generated data covers timestamp variants, coordinate boundaries, metadata shapes, half-open intervals, reassignment, combined identifiers, and unresolved observations. Invalid cases remain in automated tests.

## Reproduce the required scenario

```bash
python -m scripts.replay_demo
```

Using the included [observations](sample-data/demo-observations.json) and [mappings](sample-data/demo-mappings.json), the script verifies:

- the January `A1B2C3` report under `aircraft-001`;
- the February report and the report at exactly `2026-02-01T00:00:00Z` under `aircraft-002`;
- an `aircraft-001` history combined from `A1B2C3` and `D4E5F6`;
- exact observation and mapping retries returning `200` without extra rows.

The replay is idempotent.

## API

All errors use this shape:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "Request validation failed",
    "details": [{"field": "latitude", "message": "Must be between -90 and 90, inclusive"}]
  }
}
```

The same envelope covers unknown paths and unsupported methods.

### `POST /observations`

Stores a position report. A new record returns `201`; an identical retry returns `200`. The response includes the untouched report and its currently available association:

```json
{
  "status": "created",
  "observation": {
    "observation_id": "obs-001",
    "reported_identifier": "A1B2C3",
    "observed_at": "2026-01-10T10:00:00Z",
    "latitude": 37.7749,
    "longitude": -122.4194,
    "metadata": {"source": "receiver-17"}
  },
  "association": null
}
```

Example:

```bash
curl -i http://127.0.0.1:8000/observations \
  -H 'Content-Type: application/json' \
  -d '{"observation_id":"quick-1","reported_identifier":"A1B2C3","observed_at":"2026-01-10T10:00:00Z","latitude":37.7749,"longitude":-122.4194}'
```

### `POST /identity-mappings`

Stores one mapping. A new mapping returns `201`, an identical retry returns `200`, and an overlapping interval or reused ID with changed content returns `409`.

```bash
curl -i http://127.0.0.1:8000/identity-mappings \
  -H 'Content-Type: application/json' \
  -d '{"mapping_id":"quick-map","reported_identifier":"A1B2C3","aircraft_id":"aircraft-001","valid_from":"2026-01-01T00:00:00Z","valid_to":"2026-02-01T00:00:00Z"}'
```

### `GET /aircraft/{aircraft_id}/history`

Returns `200` with an ordered `history` array, including the `mapping_id` used for every item. `from` is inclusive and `to` is exclusive. Unknown aircraft return an empty array.

```bash
curl 'http://127.0.0.1:8000/aircraft/aircraft-001/history?from=2026-01-01T00%3A00%3A00Z&to=2026-02-01T00%3A00%3A00Z'
```

```json
{
  "aircraft_id": "aircraft-001",
  "filters": {"from": null, "to": null},
  "count": 1,
  "history": [
    {
      "observation": {"observation_id": "obs-001", "reported_identifier": "A1B2C3", "observed_at": "2026-01-10T10:00:00Z", "latitude": 37.7749, "longitude": -122.4194},
      "mapping_id": "map-001"
    }
  ]
}
```

### `GET /observations/{observation_id}`

Returns the original accepted report plus its current association, or `404` if the report does not exist. `association` is `null` while unresolved.

```bash
curl http://127.0.0.1:8000/observations/obs-001
```

## Design decisions

- Store original JSON and separate indexed values.
- Resolve identities at query time so late mappings apply immediately.
- Use half-open millisecond intervals and semantic retry comparison.
- Serialize writes with `BEGIN IMMEDIATE`; enforce overlap rules with a trigger.
- Scope history queries through compound identifier/time indexes.

See [DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md) for alternatives and tradeoffs.

## Project layout

```text
app/main.py                  application factory and composition root
app/api/                     routes, HTTP errors, and response construction
app/services/                ingestion, idempotency, identity, and history rules
app/repositories/            observation and mapping SQL operations
app/schemas/                 JSON types, serialization, and strict validation
app/database/                connections, initialization, and transactions
app/validation.py            backward-compatible validation imports
app/schema.sql               tables, indexes, and overlap trigger
app/static/                  dependency-free responsive web interface
tests/                       API, persistence, and concurrency tests
sample-data/                 reproducible synthetic scenario
scripts/replay_demo.py       scenario replay and output verification
scripts/generate_scale_data.py deterministic 100k/10k scale dataset generator
```

## Known limitations and scope

- No authentication, deployment configuration, mapping corrections, pagination, or aircraft registry, all intentionally outside scope.
- Schema initialization is idempotent but there is no migration framework; future schema changes would need migrations.
- SQLite serializes writes. This is intentional and safe for the target volume, but a sustained high-write deployment would eventually warrant PostgreSQL.
- The UI uses manual refresh and accepts timestamp filters as RFC3339 text rather than a timezone-converting date picker.

## Time and assistance disclosure

Active time: approximately **3.5 hours**. No required work is known to be unfinished.

OpenAI Codex assisted with requirements analysis, implementation, tests, verification, and documentation. No external data, proprietary code, or paid service was used. See [AI_USAGE.md](docs/AI_USAGE.md).
