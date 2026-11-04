from __future__ import annotations

from pathlib import Path

from app.database.connection import connect


DEFAULT_DB_PATH = Path("data/govia.db")
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema.sql"


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(db_path)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        connection.close()
