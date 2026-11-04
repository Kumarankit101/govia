# Design decisions and tradeoffs

| Area | Selected approach | Why it fits | Alternatives considered | Tradeoff |
| --- | --- | --- | --- | --- |
| Backend | FastAPI | Compact API, automatic OpenAPI documentation, straightforward local testing | Django REST Framework; Express/NestJS; Go with Chi | Less built-in project structure than Django |
| Persistence | SQLite in WAL mode | Durable, local, no credentials or service setup, appropriate for 100k reports | PostgreSQL; MySQL; MongoDB | One writer at a time |
| Identity resolution | Resolve during history queries | Late mappings immediately apply to previously stored observations | Resolve during ingestion; background reconciliation; materialized association table | History requires an indexed join |
| Original preservation | Store original JSON plus derived indexed columns | Returns the accepted structure while supporting efficient queries | Fully normalized storage; JSON-only storage; event store with projections | Some values are stored twice |
| Time representation | Original string plus epoch milliseconds | Preserves spelling but compares equivalent UTC instants correctly | Native timestamp column; canonical ISO text; epoch microseconds | Precision is intentionally limited to the required milliseconds |
| Retry equality | Recursive semantic comparison | Ignores object-key order, preserves array order and JSON types, and compares timestamp fields by instant | Raw-body equality; canonical JSON hash; database JSON equality | More application logic |
| Mapping intervals | Half-open `[valid_from, valid_to)` | Makes adjacent assignments unambiguous and matches the brief | Closed intervals; start plus duration; version events | Boundary behavior requires explicit tests |
| Concurrency | Short `BEGIN IMMEDIATE` write transactions | Atomically performs retry/overlap checks and insertion | Optimistic retries; application mutex; PostgreSQL constraints | SQLite writes are serialized |
| Overlap integrity | Application check plus database trigger | Produces useful conflicts and protects against future writers bypassing the service | Application-only check; PostgreSQL exclusion constraint; advisory locks | Rule exists in two defensive layers |
| Frontend | HTML, CSS, and vanilla JavaScript served by FastAPI | One command, no build system, no external credentials | React; Vue; Svelte | Less suitable for a much larger interface |
| Unknown fields | Reject unexpected top-level fields | Detects producer mistakes while metadata remains arbitrary JSON | Preserve unknown fields; ignore them; versioned schemas | Less forward-compatible without a schema update |
| Pagination | Omitted | Explicitly outside scope and keeps the assessment focused | Cursor pagination; offset pagination; required time windows | A very large single-aircraft response could be large |

## Late mappings

Observations never store a permanent `aircraft_id`. A history query joins the
currently committed mappings to observations using the reported identifier and
observation instant:

```text
mapping.valid_from <= observation.observed_at
and (mapping.valid_to is null or observation.observed_at < mapping.valid_to)
```

A late mapping therefore applies without mutation, resubmission, or repair.

## Transaction and race-condition behavior

Each write executes this sequence in one `BEGIN IMMEDIATE` transaction:

```text
acquire SQLite writer lock
→ find existing record ID
→ return an identical retry or changed-content conflict
→ check mapping overlap when applicable
→ insert
→ commit
→ return success
```

Concurrent writers wait for the lock. Once the first transaction commits, the
next writer sees its result. Primary keys prevent duplicate IDs, and the mapping
trigger independently prevents overlapping intervals. WAL readers see the
committed state from before or after a write, never its partial state.

## Indexing strategy

The history query first scopes mappings by aircraft and then performs bounded
identifier/time lookups into observations:

```text
observations(reported_identifier, observed_at_ms, observation_id)
identity_mappings(aircraft_id, valid_from_ms, valid_to_ms, reported_identifier)
identity_mappings(reported_identifier, valid_from_ms, valid_to_ms)
```

This avoids scanning every report at the target scale of approximately 100,000
observations and 10,000 mappings.

## Production scaling path

For sustained high-write traffic, use PostgreSQL with:

- a bounded connection pool;
- `tstzrange` validity intervals;
- JSONB for original reports;
- multiple application workers; and
- cursor pagination for large histories.

A SQLite pool would not change its single-writer limit, so it was omitted.
