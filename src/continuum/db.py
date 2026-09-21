"""
Database session management and engine initialization for Continuum.
"""

from __future__ import annotations
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from src.continuum.config import get_settings, get_base_dir

Base = declarative_base()

_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.get("paths", {}).get("db_url", "sqlite:///data/continuum.db")
        
        # Ensure directory for sqlite file exists
        if db_url.startswith("sqlite:///"):
            rel_path = db_url.replace("sqlite:///", "")
            full_path = get_base_dir() / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{full_path}"

        connect_args = {}
        if db_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}

        _engine = create_engine(db_url, connect_args=connect_args, echo=False)

        # Enable WAL mode and foreign keys for SQLite
        if db_url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return _engine


def get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        engine = get_engine()
        _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionFactory


def get_db() -> Generator[Session, None, None]:
    """
    Context manager / generator for database sessions.
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def init_db(drop_existing: bool = False) -> None:
    """
    Creates all tables in the database schema.
    Optionally drops existing tables first for a clean re-initialization.
    """
    import src.continuum.models  # Ensure models are imported
    engine = get_engine()
    if drop_existing:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Lightweight schema migration for SQLite if columns are missing
    if not drop_existing and engine.name == "sqlite":
        with engine.connect() as conn:
            cursor = conn.connection.cursor()
            existing_cols = [c[1] for c in cursor.execute("PRAGMA table_info(consents)").fetchall()]
            if existing_cols:
                if "consented_kin_name" not in existing_cols:
                    cursor.execute("ALTER TABLE consents ADD COLUMN consented_kin_name VARCHAR(128)")
                if "consented_kin_phone" not in existing_cols:
                    cursor.execute("ALTER TABLE consents ADD COLUMN consented_kin_phone VARCHAR(32)")
            cursor.close()
