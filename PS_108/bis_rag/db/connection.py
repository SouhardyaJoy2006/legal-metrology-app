"""
bis_rag.db.connection
=====================
PostgreSQL connection management using psycopg v3.

get_connection()  — context manager for one-off scripts / CLI tools
get_pool()        — ConnectionPool for Flask (call once at app start)

pgvector's register_vector() is called on every new connection so that
psycopg can read/write the vector column type.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row

try:
    from pgvector.psycopg import register_vector
    _PGVECTOR_AVAILABLE = True
except ImportError:
    _PGVECTOR_AVAILABLE = False
    logging.warning("pgvector adapter not installed. Vector operations will not work.")

from bis_rag.config import settings

logger = logging.getLogger(__name__)


def _configure_connection(conn: psycopg.Connection) -> None:
    if _PGVECTOR_AVAILABLE:
        try:
            register_vector(conn)
        except psycopg.Error:
            pass
    conn.execute("SET application_name = 'bis_rag'")


@contextmanager
def get_connection(autocommit: bool = False) -> Generator[psycopg.Connection, None, None]:
    """Open a single psycopg connection, yield it, commit on clean exit, close it."""
    conn: psycopg.Connection | None = None
    try:
        conn = psycopg.connect(settings.db.dsn, row_factory=dict_row, autocommit=autocommit)
        _configure_connection(conn)
        yield conn
        if not autocommit and conn is not None and not conn.closed:
            conn.commit()
    except psycopg.OperationalError as exc:
        logger.error("Failed to connect to PostgreSQL: %s", exc)
        raise
    except Exception:
        if conn is not None and not conn.closed:
            conn.rollback()
        raise
    finally:
        if conn is not None and not conn.closed:
            conn.close()


def get_pool(min_size: int = 2, max_size: int = 10):
    """Return a ConnectionPool for use in a Flask app factory."""
    try:
        from psycopg_pool import ConnectionPool
    except ImportError as exc:
        raise ImportError("Install psycopg[pool] for connection pooling.") from exc

    pool = ConnectionPool(
        conninfo=settings.db.dsn,
        min_size=min_size,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
        configure=_configure_connection,
        open=True,
    )
    logger.info("Connection pool opened (%d–%d connections)", min_size, max_size)
    return pool
