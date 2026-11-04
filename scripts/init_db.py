from __future__ import annotations

import argparse
from pathlib import Path

from app.database import DEFAULT_DB_PATH, initialize_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the Govia SQLite database")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    path = args.database.resolve()
    initialize_database(path)
    print(f"Initialized {path}")


if __name__ == "__main__":
    main()
