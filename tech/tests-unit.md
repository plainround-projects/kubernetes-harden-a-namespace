# Unit tests

## 1. What it is

A **unit test** checks one small piece of the program (a class, a function) on its own, fast, with no network, no Docker and no cluster. Anything the piece would normally talk to is replaced by a **fake**: a simple stand-in written for the test. The tools are pytest (`pytest.md`) plus Python's `monkeypatch` and `capfd` helpers, explained below.

## 2. Why this repository uses it

The domain and application layers must stay above 95 percent coverage, and the behaviour the lesson relies on (what the app does when the database is down or the configuration is wrong) has to be exact. Unit tests prove it in seconds, so they run on every `make test`.

## 3. Where it appears

| File | Tests |
| --- | --- |
| `tests/unit/conftest.py` | Shared fake store and the `store` fixture. |
| `tests/unit/test_domain.py` | `TeamName` and `VisitCount` validation. |
| `tests/unit/test_use_cases.py` | The use cases. |
| `tests/unit/test_settings.py` | Reading and checking environment settings. |
| `tests/unit/test_logging.py` | JSON log lines and logging setup. |
| `tests/unit/test_postgres_store.py` | The adapter, with a stub pool and connection. |
| `tests/unit/test_http.py` | The Flask routes, via the test client. |
| `tests/unit/test_wsgi.py` | The start-up code, including the FATAL exit. |

## 4. How it works underneath

pytest looks for `conftest.py` in the test folder; fixtures defined there are available to every test file beside it without importing. A test asks for a fixture by naming a parameter: `def test_x(store):` receives whatever the `store` fixture returned.

`monkeypatch` is a built-in fixture that replaces an attribute (a function, a variable) for the length of one test and puts the original back afterwards. `capfd` captures what the program writes to file descriptors 1 and 2 (standard output and error), so the test can read the log lines, including ones written by libraries. `pytest.mark.parametrize` runs the same test body once per listed input. `pytest.raises(Error, match="text")` passes only when the block raises that error and the message contains `text` (a regular expression).

The fakes follow the **ports and adapters** idea: the application code depends on an interface (the `VisitStore` port), and the fake is another implementation of the same interface, so the test never needs the database.

## 5. Walkthrough of this repository's use

### `tests/unit/conftest.py`

```text
"""Shared fakes for the unit tests: an in-memory visit store that can be told to fail."""

from __future__ import annotations

import pytest

from tenant_web.domain.errors import StoreUnavailableError


class FakeStore:
    """Implements the VisitStore port in memory."""

    def __init__(self, *, down: bool = False) -> None:
        self.down = down
        self.pages: dict[str, int] = {}

    def record_visit(self, page: str) -> int:
        if self.down:
            raise StoreUnavailableError("fake store is down")
        self.pages[page] = self.pages.get(page, 0) + 1
        return self.pages[page]
```

The docstring says what the file is. `from __future__ import annotations` lets type hints be written freely. `class FakeStore` is a stand-in for Postgres. `__init__` takes the keyword-only option `down` (pretend the database is unreachable) and keeps `pages`, a dictionary from page name to count. `record_visit(page)` raises `StoreUnavailableError` when `down`, otherwise adds one to the page's count (starting at zero) and returns it.

```text
    def ping(self) -> None:
        if self.down:
            raise StoreUnavailableError("fake store is down")


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()
```

`ping()` also raises when `down`. `@pytest.fixture` above `def store()` turns the function into a fixture returning a fresh `FakeStore()` to any test with a parameter named `store`.

### `tests/unit/test_domain.py`

```text
import pytest

from tenant_web.domain.errors import InvalidCountError, InvalidTeamNameError
from tenant_web.domain.values import TeamName, VisitCount


@pytest.mark.parametrize("name", ["team-a", "a", "team-42", "x" * 63])
def test_a_dns_label_is_a_valid_team_name(name):
    assert TeamName(name).value == name


@pytest.mark.parametrize("name", ["", "Team-A", "team_a", "-team", "team-", "x" * 64, "team a", "team.a"])
def test_anything_else_is_rejected(name):
    with pytest.raises(InvalidTeamNameError):
        TeamName(name)


def test_a_visit_count_keeps_its_value():
    assert VisitCount(3).value == 3
```

`test_a_dns_label_is_a_valid_team_name` is run for four valid names: `team-a`, `a`, `team-42` and 63 letters (`"x" * 63`, the longest allowed). `test_anything_else_is_rejected` is run for eight invalid ones: empty, capitals, underscore, leading hyphen, trailing hyphen, 64 letters, a space and a dot; each must raise `InvalidTeamNameError`. `test_a_visit_count_keeps_its_value` checks `VisitCount(3).value`.

```text
@pytest.mark.parametrize("bad", [0, -1, 1.5, "2", None, True])
def test_a_visit_count_must_be_a_positive_integer(bad):
    with pytest.raises(InvalidCountError):
        VisitCount(bad)


def test_values_are_immutable():
    with pytest.raises(AttributeError):
        TeamName("team-a").value = "other"  # type: ignore[misc]
```

Six bad counts (zero, negative, a float, a string, `None`, `True`) must raise `InvalidCountError`. The last test shows assigning to a frozen record raises `AttributeError` (the `# type: ignore[misc]` tells mypy the line is deliberately wrong).

### `tests/unit/test_use_cases.py`

```text
import pytest

from tenant_web.application.use_cases import CheckReadiness, RecordVisit
from tenant_web.domain.errors import StoreUnavailableError
from tenant_web.domain.values import TeamName
from tests.unit.conftest import FakeStore


def test_a_visit_returns_the_team_and_the_next_total(store):
    record = RecordVisit(TeamName("team-a"), store)
    receipts = [record() for _ in range(3)]
    assert [receipt.count.value for receipt in receipts] == [1, 2, 3]
    assert receipts[0].team == TeamName("team-a")


def test_each_page_has_its_own_total(store):
    record = RecordVisit(TeamName("team-a"), store)
    record("/")
    record("/")
    assert record("/other").count.value == 1
```

The first test calls `RecordVisit` three times and checks the totals 1, 2, 3 and that the receipt carries the team. The second checks each page has its own total: two visits to `/` do not affect `/other`.

```text
def test_a_store_failure_passes_through(store):
    store.down = True
    with pytest.raises(StoreUnavailableError):
        RecordVisit(TeamName("team-a"), store)()


def test_ready_when_the_database_answers(store):
    assert CheckReadiness(store)().ready is True


def test_not_ready_when_the_database_is_down_and_the_reason_is_kept():
    report = CheckReadiness(FakeStore(down=True))()
    assert report.ready is False
    assert "down" in report.reason
```

A store failure passes through (`StoreUnavailableError` is raised). `CheckReadiness` says ready when the store answers, and not ready, with the reason kept (it contains `down`), when it does not.

### `tests/unit/test_settings.py`

```text
import pytest

from tenant_web.infrastructure.settings import ConfigurationError, Settings

MINIMAL = {"TEAM_NAME": "team-a", "DB_PASSWORD": "pw"}


def test_defaults_when_only_the_required_values_are_set():
    settings = Settings.from_env(MINIMAL)
    assert settings.team.value == "team-a"
    assert (settings.db_host, settings.db_port, settings.db_name, settings.db_user) == ("db", 5432, "app", "app")
    assert (settings.pool_size, settings.log_level) == (4, "INFO")


def test_values_come_from_the_environment():
    settings = Settings.from_env(
        {**MINIMAL, "DB_HOST": "pg", "DB_PORT": "6543", "DB_POOL_SIZE": "8", "LOG_LEVEL": "debug"}
    )
    assert (settings.db_host, settings.db_port, settings.pool_size, settings.log_level) == ("pg", 6543, 8, "DEBUG")
```

`MINIMAL` is the smallest valid environment: a team and a password. With only those, the defaults are host `db`, port 5432, database `app`, user `app`, pool size 4 and level `INFO`. A second test overrides host, port, pool size and level (`debug` becomes `DEBUG`).

```text
def test_the_password_never_appears_in_the_repr():
    assert "hunter2" not in repr(Settings.from_env({**MINIMAL, "DB_PASSWORD": "hunter2"}))


@pytest.mark.parametrize(
    ("env", "variable"),
    [
        ({"DB_PASSWORD": "pw"}, "TEAM_NAME"),
        ({"TEAM_NAME": "Not A Label", "DB_PASSWORD": "pw"}, "TEAM_NAME"),
        ({"TEAM_NAME": "team-a"}, "DB_PASSWORD"),
        ({**MINIMAL, "DB_PORT": "x"}, "DB_PORT"),
        ({**MINIMAL, "DB_PORT": "0"}, "DB_PORT"),
        ({**MINIMAL, "DB_HOST": " "}, "DB_HOST"),
        ({**MINIMAL, "DB_TIMEOUT_SECONDS": "0"}, "DB_TIMEOUT_SECONDS"),
        ({**MINIMAL, "LOG_LEVEL": "LOUD"}, "LOG_LEVEL"),
    ],
)
def test_a_bad_or_missing_value_names_the_variable(env, variable):
    with pytest.raises(ConfigurationError, match=variable):
        Settings.from_env(env)
```

The repr of the settings must not contain the password (`hunter2` is a dummy). Then a table of eight bad or missing inputs, each paired with the variable the error must name: no team, an invalid team, no password, a port that is not a number, port 0, a blank host, a zero timeout and a bad log level.

### `tests/unit/test_logging.py`

```text
import json
import logging

from tenant_web.infrastructure.logging import JsonFormatter, configure_logging


def _record(**extra):
    record = logging.LogRecord("tenant_web", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.__dict__.update(extra)
    return record


def test_a_record_becomes_one_json_line_with_extra_fields():
    line = JsonFormatter().format(_record(redis_host="redis"))
    entry = json.loads(line)
    assert (entry["level"], entry["logger"], entry["msg"], entry["redis_host"]) == (
        "INFO",
        "tenant_web",
        "hello world",
        "redis",
    )
    assert "\n" not in line
```

`_record(**extra)` builds a `logging.LogRecord` by hand and copies extra fields in. The first test formats it and parses the output back with `json.loads`: level, logger name, message with the placeholder filled, the extra field, and no newline in the line.

```text
def test_an_exception_is_included_as_text():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    assert "ValueError: boom" in json.loads(JsonFormatter().format(record))["exc"]


def test_configure_logging_installs_one_json_handler_at_the_level():
    configure_logging("WARNING")
    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
```

An exception record: the test raises and catches `ValueError("boom")` to get `sys.exc_info()` and checks the formatted line has an `exc` field containing `ValueError: boom`. `configure_logging("WARNING")` is checked to set the root level, leave exactly one handler and use the JSON formatter.

### `tests/unit/test_postgres_store.py`

```text
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
```

The imports include psycopg's `OperationalError` and the pool's `PoolTimeout`, the two failures the adapter translates. `Result` is a stub with `fetchone()`; `Connection` is a stub connection that remembers the statements it was given and may be told to return a row or to raise an error.

```text
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
```

The stub's `__enter__` raises the configured error or returns itself, `__exit__` returns false (do not swallow errors), `execute` records `(sql, params)` and returns a `Result`. `Pool.connection()` hands out the stub.

```text
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
```

Recording a visit returns the stub's number (7), binds the page as a parameter (`("/home",)`) and uses the upsert (`ON CONFLICT (page)` appears in the SQL). For each of two errors, `record_visit` raises `StoreUnavailableError` whose message contains `write failed` and `ping` one containing `ping failed`. A missing row raises an error containing `no row`.

```text
def test_ping_runs_select_one():
    connection = Connection()
    PostgresVisitStore(Pool(connection)).ping()
    assert connection.statements == [("SELECT 1", None)]


def test_the_pool_is_built_closed_with_the_settings_timeouts():
    pool = build_pool(Settings.from_env({"TEAM_NAME": "team-a", "DB_PASSWORD": "pw", "DB_TIMEOUT_SECONDS": "2"}))
    assert pool.closed
    assert pool.timeout == 2
    assert pool.max_size == 4
```

`ping` runs exactly `("SELECT 1", None)`. `build_pool` with a two-second timeout returns a pool that is closed, has `timeout` 2 and `max_size` 4.

### `tests/unit/test_http.py`

```text
import pytest

from tenant_web.application.use_cases import CheckReadiness, RecordVisit
from tenant_web.domain.values import TeamName
from tenant_web.interfaces.http import create_app


def _client(store, alive=True):
    app = create_app(RecordVisit(TeamName("team-a"), store), CheckReadiness(store), lambda: alive)
    return app.test_client()


@pytest.fixture
def client(store):
    return _client(store)


def test_each_visit_increments_and_names_the_team(client):
    answers = [client.get("/").get_json() for _ in range(3)]
    assert [answer["visits"] for answer in answers] == [1, 2, 3]
    assert {answer["team"] for answer in answers} == {"team-a"}
    assert answers[0]["pod"]
```

`_client(store, alive=True)` builds the app with a `RecordVisit` for `team-a`, a `CheckReadiness` and a liveness lambda, and returns the test client. The first test makes three visits and checks the counts `[1, 2, 3]`, that every answer names `team-a` and that a `pod` is present.

```text
def test_a_visit_is_a_503_when_the_database_is_down(store, client):
    store.down = True
    response = client.get("/")
    assert response.status_code == 503
    assert response.get_json() == {"error": "database unavailable"}


def test_healthz_is_alive_even_when_the_database_is_down(store, client):
    store.down = True
    assert client.get("/healthz").status_code == 200


def test_healthz_is_500_when_liveness_fails(store):
    assert _client(store, alive=False).get("/healthz").status_code == 500


def test_readyz_follows_the_database(store, client):
    assert client.get("/readyz").get_json() == {"status": "ready"}
    store.down = True
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.get_json()["status"] == "not ready"
```

The database being down gives 503 with body `{"error": "database unavailable"}` on `/`; `/healthz` stays 200 with the database down and is 500 when the liveness check fails; `/readyz` answers `{"status": "ready"}` and then, after `store.down = True`, status 503 with `not ready`.

### `tests/unit/test_wsgi.py`

```text
import pytest

from tenant_web.interfaces import wsgi


class FakePool:
    opened = False

    def open(self, wait=True):
        FakePool.opened = True

    def connection(self):
        raise AssertionError("no query in this test")


def test_the_factory_opens_the_pool_without_waiting_and_builds_the_app(monkeypatch):
    monkeypatch.setattr(wsgi, "build_pool", lambda settings: FakePool())
    app = wsgi.build_app({"TEAM_NAME": "team-a", "DB_PASSWORD": "pw"})
    assert FakePool.opened
    assert app.test_client().get("/healthz").status_code == 200
```

`FakePool` stands in for the connection pool: `open` records that it was called and `connection` fails if used. The test replaces `build_pool` inside the `wsgi` module with `monkeypatch.setattr`, builds the app and checks the pool was opened and `/healthz` answers 200 without a database.

```text
@pytest.mark.parametrize("env", [{}, {"TEAM_NAME": "team-a"}, {"TEAM_NAME": "BAD", "DB_PASSWORD": "pw"}])
def test_a_bad_configuration_exits_with_one_fatal_line(env, capfd):
    with pytest.raises(SystemExit) as exit_info:
        wsgi.build_app(env)
    assert exit_info.value.code == 1
    assert "FATAL invalid configuration" in capfd.readouterr().err
```

Three bad environments (empty, no password, an invalid team) must each make `build_app` raise `SystemExit` with code 1 and print `FATAL invalid configuration` on standard error.


## 6. Try it yourself

```bash
.venv/bin/python -m pytest tests/unit -q
```

All unit tests pass; the final line shows the count and the time.

```bash
.venv/bin/python -m pytest tests/unit/test_domain.py -v
```

Lists each test by name; the `parametrize` tests appear once per input, with the input in square brackets.

```bash
.venv/bin/python -m pytest tests/unit -q --cov=tenant_web --cov-report=term-missing | tail -20
```

Shows the percentages and the missing lines per file (every line of the package is covered).

## 7. Mistakes people make

- **Testing the fake instead of the code.** Each test here asserts something about the real class with a fake around it.
- **Leaking a patch.** `monkeypatch` is used so the original is always restored.
- **Asserting on a log message's exact words everywhere.** Only the FATAL lines the lesson tells the learner to look for are asserted exactly.
- **Skipping the failure paths.** About half the tests here are about what goes wrong.

## 8. Check yourself

1. Why is there a `FakeStore`? *So use cases and routes can be tested without a database.*
2. What does `capfd` do in `test_wsgi.py`? *Reads what start-up wrote to standard error to check the FATAL line.*
3. What does `parametrize` do in `test_domain.py`? *Runs the test once for each name or value listed.*
4. Why does `test_healthz_is_alive_even_when_the_database_is_down` matter? *It proves liveness does not depend on the database.*
5. Why does the adapter test use a hand-written `Pool` and `Connection`? *The adapter only needs a context manager with `execute`, so a stub is enough to test its error handling.*

## 9. Further reading

- pytest monkeypatch: https://docs.pytest.org/en/stable/how-to/monkeypatch.html
- Capturing output: https://docs.pytest.org/en/stable/how-to/capture-stdout-stderr.html
- Flask testing: https://flask.palletsprojects.com/en/stable/testing/
- Python `unittest.mock` background on fakes and stubs: https://docs.python.org/3.13/library/unittest.mock.html
