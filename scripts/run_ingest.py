"""
CLI Ingestion runner: parses clinic export files and populates Continuum database tables.
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.continuum.db import get_session_factory, init_db
from src.continuum.ingest.loader import ingest_akola_dataset


def main():
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"

    print(f"[INGEST] Initializing DB schema and loading clinic data from {data_dir}...")
    init_db()

    Session = get_session_factory()
    with Session() as db:
        stats = ingest_akola_dataset(data_dir=data_dir, db=db, user="cli_runner")
        print("[SUCCESS] Ingestion completed:")
        for k, v in stats.items():
            print(f"  - {k}: {v}")


if __name__ == "__main__":
    main()
