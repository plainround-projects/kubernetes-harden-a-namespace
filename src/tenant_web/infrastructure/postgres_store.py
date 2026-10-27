"""The visit store adapter: Postgres through a small connection pool. The statements are in sql/003_queries.sql."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol

from psycopg import Error as PsycopgError
from psycopg_pool import ConnectionPool, PoolTimeout

from tenant_web.domain.errors import StoreUnavailableError
from tenant_web.infrastructure.settings import Settings

# Keep in step with the "record a visit" query in sql/003_queries.sql.
RECORD_VISIT = """
INSERT INTO visits (page, visit_count) VALUES (%s, 1)
ON CONFLICT (page) DO UPDATE SET visit_count = visits.visit_count + 1, last_visit_at = now()
RETURNING visit_count
"""


class Rows(Protocol):
    """The part of a cursor the store reads."""

    def fetchone(self) -> Any: ...


class Session(Protocol):
    """The part of a connection the store uses."""

    def execute(self, query: Any, params: Any = None) -> Rows: ...


class Connections(Protocol):
    """A source of pooled connections; psycopg_pool.ConnectionPool satisfies it and tests can stub it."""

    def connection(self) -> AbstractContextManager[Session]: ...


def build_pool(settings: Settings) -> ConnectionPool:
    """Open a pool that fails fast: a connection that cannot be made within the timeout is an error, not a hang."""
    conninfo = (
        f"host={settings.db_host} port={settings.db_port} dbname={settings.db_name} user={settings.db_user} "
        f"connect_timeout={max(1, round(settings.db_timeout_seconds))}"
    )
    return ConnectionPool(
        conninfo,
        kwargs={"password": settings.db_password},
        min_size=1,
        max_size=settings.pool_size,
        timeout=settings.db_timeout_seconds,
        open=False,
    )


class PostgresVisitStore:
    """Implements VisitStore. Every statement runs in its own short transaction on a pooled connection."""

    def __init__(self, pool: Connections) -> None:
        """Wrap a pool; opening and closing it is the composition root's job."""
        self._pool = pool

    def record_visit(self, page: str) -> int:
        """INSERT or increment the page's row and return its count. Not retried: the increment is not idempotent."""
        try:
            with self._pool.connection() as connection:
                row = connection.execute(RECORD_VISIT, (page,)).fetchone()
        except (PsycopgError, PoolTimeout) as error:
            raise StoreUnavailableError(f"database write failed: {error}") from error
        if row is None:
            raise StoreUnavailableError("database returned no row for the visit")
        return int(row[0])

    def ping(self) -> None:
        """SELECT 1; any failure means "not ready"."""
        try:
            with self._pool.connection() as connection:
                connection.execute("SELECT 1")
        except (PsycopgError, PoolTimeout) as error:
            raise StoreUnavailableError(f"database ping failed: {error}") from error
