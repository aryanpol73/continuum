"""
Database initialization script for Continuum.
Creates all schema tables and establishes write-ahead logging (WAL).
"""

from __future__ import annotations
import sys
from pathlib import Path

# Ensure continuum root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.continuum.db import init_db, get_session_factory
from src.continuum.audit import log_action


def main():
    drop = "--drop" in sys.argv
    print(f"[INIT] Initializing Continuum Database Schema (drop_existing={drop})...")
    init_db(drop_existing=drop)
    
    # Log system initialization event
    Session = get_session_factory()
    with Session() as db:
        log_action(
            db,
            action="SCHEMA_INITIALIZED",
            entity_type="Database",
            entity_id="continuum.db",
            user="system",
            details={"version": "1.0.0", "drop_existing": drop}
        )

    print("[SUCCESS] Continuum database tables created successfully.")


if __name__ == "__main__":
    main()
