"""
Shared SQLAlchemy engine, session factory, and declarative Base.

Database URL is resolved in order:
  1. DATABASE_URL environment variable (or .env file via pydantic-settings)
  2. Default: SQLite at <project_root>/vi.db

For production, point to PostgreSQL:
  DATABASE_URL=postgresql+psycopg2://user:pass@host/dbname

All ORM models are defined in api/schema.py.  Import Base and engine from
here — never create additional engines or Bases in other modules.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(_project_root, 'vi.db')}",
)

_is_sqlite = DATABASE_URL.startswith("sqlite")

DB_SSL_CERT: str | None = os.environ.get("DB_SSL_CERT")

# SQLite uses check_same_thread=False because FastAPI runs handlers in a
# thread pool.  PostgreSQL uses pre-ping and connection recycling instead.
if _is_sqlite:
    _engine_kwargs: dict = {"connect_args": {"check_same_thread": False}}
else:
    _pg_connect_args: dict = {}
    if DB_SSL_CERT:
        _pg_connect_args = {"sslmode": "verify-ca", "sslrootcert": DB_SSL_CERT}
    else:
        _pg_connect_args = {"sslmode": "require"}
    _engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "connect_args": _pg_connect_args,
    }

engine = create_engine(DATABASE_URL, **_engine_kwargs)

# SQLite hardening applied at every new connection:
#   journal_mode=WAL   — allows concurrent reads during a write (no read-lock).
#   foreign_keys=ON    — SQLite disables FK constraints by default; enforce them.
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

# expire_on_commit=False: detached objects keep their attribute values after
# session.commit() / session.close(), so callers don't need an open session
# to read fields on returned model instances.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """
    Create all tables that are not yet present (idempotent — safe on every restart).

    Must be called after all ORM models have been imported so that
    Base.metadata knows about every table.  main.py calls this at startup.
    """
    import api.schema  # noqa: F401 — registers all models with Base.metadata
    Base.metadata.create_all(bind=engine)
