import pytest
from psycopg import OperationalError
from psycopg_pool import PoolTimeout

from tenant_web.domain.errors import StoreUnavailableError
from tenant_web.infrastructure.postgres_store import PostgresVisitStore, build_pool
from tenant_web.infrastructure.settings import Settings


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, row=(5,), error=None):
        self.row, self.error, self.statements = row, error, []

    def __enter__(self):
        if self.error:
            raise self.error
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        return Result(self.row)


class Pool:
    def __init__(self, connection):
        self._connection = connection

    def connection(self):
        return self._connection


def test_recording_a_visit_returns_the_new_count_and_binds_the_page():
    connection = Connection(row=(7,))
    assert PostgresVisitStore(Pool(connection)).record_visit("/home") == 7
    assert connection.statements[0][1] == ("/home",)
    assert "ON CONFLICT (page)" in connection.statements[0][0]


@pytest.mark.parametrize("error", [OperationalError("refused"), PoolTimeout("no connection")])
def test_a_database_error_becomes_a_named_error(error):
    store = PostgresVisitStore(Pool(Connection(error=error)))
    with pytest.raises(StoreUnavailableError, match="write failed"):
        store.record_visit("/")
    with pytest.raises(StoreUnavailableError, match="ping failed"):
        store.ping()


def test_a_missing_row_is_an_error():
    with pytest.raises(StoreUnavailableError, match="no row"):
        PostgresVisitStore(Pool(Connection(row=None))).record_visit("/")


def test_ping_runs_select_one():
    connection = Connection()
    PostgresVisitStore(Pool(connection)).ping()
    assert connection.statements == [("SELECT 1", None)]


def test_the_pool_is_built_closed_with_the_settings_timeouts():
    pool = build_pool(Settings.from_env({"TEAM_NAME": "team-a", "DB_PASSWORD": "pw", "DB_TIMEOUT_SECONDS": "2"}))
    assert pool.closed
    assert pool.timeout == 2
    assert pool.max_size == 4
