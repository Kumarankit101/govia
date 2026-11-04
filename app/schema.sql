PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    reported_identifier TEXT NOT NULL,
    observed_at_text TEXT NOT NULL,
    observed_at_ms INTEGER NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    original_json TEXT NOT NULL CHECK (json_valid(original_json))
);

CREATE TABLE IF NOT EXISTS identity_mappings (
    mapping_id TEXT PRIMARY KEY,
    reported_identifier TEXT NOT NULL,
    aircraft_id TEXT NOT NULL,
    valid_from_text TEXT NOT NULL,
    valid_from_ms INTEGER NOT NULL,
    valid_to_text TEXT,
    valid_to_ms INTEGER,
    original_json TEXT NOT NULL CHECK (json_valid(original_json)),
    CHECK (valid_to_ms IS NULL OR valid_to_ms > valid_from_ms)
);

-- A history query first finds a small set of mappings for one aircraft, then
-- performs an indexed time-range lookup for each reported identifier.
CREATE INDEX IF NOT EXISTS idx_observations_identifier_time
    ON observations (reported_identifier, observed_at_ms, observation_id);

CREATE INDEX IF NOT EXISTS idx_mappings_aircraft_interval
    ON identity_mappings (aircraft_id, valid_from_ms, valid_to_ms, reported_identifier);

CREATE INDEX IF NOT EXISTS idx_mappings_identifier_interval
    ON identity_mappings (reported_identifier, valid_from_ms, valid_to_ms);

-- The application serializes writes before checking overlaps. This trigger is
-- a second line of defense for every database writer, including future code.
CREATE TRIGGER IF NOT EXISTS reject_overlapping_identity_mapping
BEFORE INSERT ON identity_mappings
WHEN EXISTS (
    SELECT 1
    FROM identity_mappings AS existing
    WHERE existing.reported_identifier = NEW.reported_identifier
      AND (NEW.valid_to_ms IS NULL OR existing.valid_from_ms < NEW.valid_to_ms)
      AND (existing.valid_to_ms IS NULL OR existing.valid_to_ms > NEW.valid_from_ms)
)
BEGIN
    SELECT RAISE(ABORT, 'overlapping identity mapping');
END;
