"""
bis_rag.db.manage
=================
Migration runner CLI.

Runs SQL files from bis_rag/db/migrations/ in lexicographic order.
Tracks applied migrations in a schema_migrations table.

Commands:
    python -m bis_rag.db.manage migrate   — apply all pending migrations
    python -m bis_rag.db.manage ping      — test database connectivity
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import psycopg

from bis_rag.db.connection import get_connection

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _ensure_tracking_table(conn: psycopg.Connection) -> None:
    conn.execute(_CREATE_TRACKING_TABLE)
    conn.commit()


def _applied_migrations(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    return {row["filename"] for row in rows}


def _run_migrations(conn: psycopg.Connection) -> None:
    _ensure_tracking_table(conn)
    applied = _applied_migrations(conn)
    pending = [f for f in sorted(MIGRATIONS_DIR.glob("*.sql")) if f.name not in applied]

    if not pending:
        print("All migrations already applied.")
        return

    for migration_file in pending:
        print(f"  Applying {migration_file.name} ...", end=" ", flush=True)
        try:
            conn.execute(migration_file.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (migration_file.name,))
            conn.commit()
            print("OK")
        except Exception as exc:
            conn.rollback()
            print(f"FAILED\n    Error: {exc}")
            raise SystemExit(1) from exc


def cmd_migrate() -> None:
    print(f"Running migrations from: {MIGRATIONS_DIR}")
    with get_connection(autocommit=False) as conn:
        _run_migrations(conn)
    print("Done.")


def cmd_ping() -> None:
    from bis_rag.config import settings
    print(f"Connecting to {settings.db.host}:{settings.db.port}/{settings.db.dbname} ...")
    try:
        with get_connection() as conn:
            row = conn.execute("SELECT version()").fetchone()
            print(f"OK. PostgreSQL: {row['version']}")
    except Exception as exc:
        print(f"Connection FAILED: {exc}")
        raise SystemExit(1) from exc


COMMANDS = {"migrate": cmd_migrate, "ping": cmd_ping}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python -m bis_rag.db.manage <command>")
        print(f"Commands: {', '.join(COMMANDS)}")
        raise SystemExit(1)
    COMMANDS[sys.argv[1]]()
