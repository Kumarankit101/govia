# Govia Aircraft History

A local backend and small web interface for ingesting aircraft position reports and resolving them through time-bounded identity mappings. Reports and mappings can arrive late, out of order, or repeatedly; the service preserves accepted reports and computes the current association when queried.

## Quick start

Requires Python 3.11+ and no external services.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m scripts.init_db
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) for the interface or [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for interactive API documentation. The default database is `data/govia.db`; it is initialized automatically on startup. To use another path:

```bash
GOVIA_DB_PATH=/absolute/path/to/govia.db uvicorn app.main:app
```

Run all automated tests:

```bash
pytest
```

The suite contains 45 tests covering late and out-of-order input, retries, changed-content conflicts, interval overlaps and boundaries, reassigned and combined identifiers, filtering and deterministic ordering, validation, original JSON preservation, restart persistence, and concurrent conflicting requests.

## Reproduce the required scenario

With the server running against a fresh database, run:

```bash
python -m scripts.replay_demo
```

The script uses [sample-data/demo-observations.json](sample-data/demo-observations.json) and [sample-data/demo-mappings.json](sample-data/demo-mappings.json). It submits the February report before the January report, verifies that both histories are initially empty, then adds mappings and shows:

- the January `A1B2C3` report under `aircraft-001`;
- the February report and the report at exactly `2026-02-01T00:00:00Z` under `aircraft-002`;
- an `aircraft-001` history combined from `A1B2C3` and `D4E5F6`;
- exact observation and mapping retries returning `200` without extra rows.

The replay is idempotent: a second run receives `200` for existing records and produces the same histories.

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

This envelope also applies to framework-level routing errors such as unknown
paths (`not_found`) and unsupported HTTP methods (`method_not_allowed`).

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

### Resolution and preservation

Associations are a query-time join between immutable observations and the mappings committed when the query begins. This makes a late mapping immediately expose older reports without a repair job or resubmission, and it avoids storing stale association fields on the original report. Mapping intervals and filters use integer UTC epoch milliseconds and half-open comparisons (`start <= instant < end`). The original timestamp spelling and complete original report are stored as JSON and returned from that JSON.

The JSON retry comparison is recursive: object key order is ignored, array order is preserved, booleans remain distinct from numbers, strings are exact, and numerically equal JSON numbers compare equal. Omitting `metadata` differs from supplying `{}`. IDs are not trimmed or case-normalized.

Unexpected top-level fields are rejected with `400`. This choice catches likely producer mistakes while arbitrary nested JSON inside `metadata` remains accepted. Duplicate object keys are left to the JSON parser, as allowed by the brief.

### Database and concurrency

SQLite runs in WAL mode with `synchronous=FULL` and a busy timeout. Each write executes in `BEGIN IMMEDIATE`, so the ID/retry check, overlap check, and insert occur under the single-writer lock. Primary keys prevent duplicate IDs, and a database trigger independently rejects overlapping mappings. A query sees a committed SQLite snapshot, never a partially applied write. The database therefore remains correct with concurrent threads or application processes sharing the file.

The schema is in [app/schema.sql](app/schema.sql) and startup initialization is idempotent.

### Indexing and expected scale

The two important indexes are:

```text
observations(reported_identifier, observed_at_ms, observation_id)
identity_mappings(aircraft_id, valid_from_ms, valid_to_ms, reported_identifier)
```

A history query first selects only mappings for the requested `aircraft_id`. For each of those mappings, SQLite performs a bounded lookup into the observation index by identifier and observation time; optional history filters further narrow the same range. It does not scan all 100,000 reports. A separate `(reported_identifier, valid_from_ms, valid_to_ms)` index supports association and overlap checks. Final ordering is by normalized observation instant, then `observation_id`.

At the stated scale of roughly 100,000 reports and 10,000 mappings, this layout keeps writes simple and scoped reads indexed. Pagination is deliberately omitted per the requirements.

## Project layout

```text
app/main.py                 API routes and response schemas
app/validation.py           strict JSON, timestamp, and semantic retry validation
app/database.py             connections and serialized transactions
app/schema.sql              tables, indexes, and overlap trigger
app/static/                 dependency-free responsive web interface
tests/                      API, persistence, and concurrency tests
sample-data/                reproducible synthetic scenario
scripts/replay_demo.py      scenario replay and output verification
```

## Known limitations and scope

- No authentication, deployment configuration, mapping corrections, pagination, or aircraft registry, all intentionally outside scope.
- Schema initialization is idempotent but there is no migration framework; future schema changes would need migrations.
- SQLite serializes writes. This is intentional and safe for the target volume, but a sustained high-write deployment would eventually warrant PostgreSQL.
- The UI uses manual refresh and accepts timestamp filters as RFC3339 text rather than a timezone-converting date picker.

## Time and assistance disclosure

Approximate active time: **2 hours** for requirements analysis, implementation, automated tests, manual verification, and documentation. Nothing required by the brief is known to be unfinished.

The implementation was produced with OpenAI Codex as an AI coding assistant. It helped interpret the supplied assessment, draft code and tests, execute the test suite, and review the result. No external data, proprietary code, or paid service was used. The complete AI prompt record is in [docs/AI_USAGE.md](docs/AI_USAGE.md).
