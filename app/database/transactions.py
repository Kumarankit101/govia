from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.database.connection import connect


@contextmanager
def serialized_write(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a transaction that takes SQLite's single-writer lock up front."""
    connection = connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
