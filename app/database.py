"""
Khabar AI — Database Connection
===================================================
WHY SQLAlchemy on top of Supabase?
  • Supabase exposes a standard PostgreSQL connection string, so we get
    full ORM power (migrations, relationships, complex queries) while
    still benefiting from Supabase's auth & dashboard.
  • For local development / CI without a live Supabase instance we
    fall back to a local SQLite file so the test suite can run offline.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Build the engine — Supabase (Postgres) or local SQLite fallback
# ---------------------------------------------------------------------------
_settings = get_settings()


def _build_database_url() -> str:
    """
    Construct the DB URL from Supabase credentials.

    Supabase connection strings follow the pattern:
        postgresql://postgres.<ref>:<password>@<host>:5432/postgres
    We derive it from SUPABASE_URL + SUPABASE_KEY when the full
    DATABASE_URL is not provided.

    Falls back to a local SQLite DB for development convenience.
    """
    if _settings.supabase_url and _settings.supabase_key:
        # Supabase REST URL looks like https://<ref>.supabase.co
        # The direct Postgres connection is on port 5432 at
        # db.<ref>.supabase.co — but for simplicity we also
        # accept a full DATABASE_URL env var.
        import os

        explicit = os.getenv("DATABASE_URL")
        if explicit:
            return explicit
        # Derive from Supabase URL (common convention)
        ref = _settings.supabase_url.replace("https://", "").split(".")[0]
        return (
            f"postgresql://postgres.{ref}:{_settings.supabase_key}"
            f"@db.{ref}.supabase.co:5432/postgres"
        )
    # Fallback: local SQLite (great for tests and demos)
    logger.warning("No Supabase credentials — using local SQLite database.")
    return "sqlite:///./khabar.db"


DATABASE_URL = _build_database_url()

# Create engine with sensible pool defaults
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # reconnect stale connections automatically
    # SQLite doesn't support pool_size — guard against that
    **({"pool_size": 5, "max_overflow": 10} if "sqlite" not in DATABASE_URL else {}),
)

# Enable WAL mode for SQLite (better concurrent read performance)
if "sqlite" in DATABASE_URL:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# Dependency / context-manager for clean session handling
# ---------------------------------------------------------------------------
@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Yield a SQLAlchemy session that auto-closes on exit.

    Usage::

        with get_db() as db:
            db.add(some_model)
            db.commit()
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create all tables defined in models.py (idempotent)."""
    from app.models import Base  # noqa: F811 — deferred import to avoid circular deps

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified / created.")
