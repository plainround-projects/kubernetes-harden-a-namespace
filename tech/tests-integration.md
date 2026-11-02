# Integration tests (a real Postgres in a container)

## 1. What it is

An **integration test** checks that two real parts work together, where a unit test would use a fake. Here the Postgres adapter talks to a real Postgres server started in a throwaway Docker container whose startup scripts are this repository's own SQL files, and the real `gunicorn` command is started as a subprocess and called over HTTP. The tests are marked `integration` and need Docker, but not Kubernetes.

## 2. Why this repository uses it

A fake database can only confirm what its author already believes. These facts are only real against Postgres: the upsert counts correctly under 80 concurrent visits, a wrong password fails, the schema script can run twice without changing anything, and the `CHECK` constraint refuses a negative count.

## 3. Where it appears

| File | Role |
| --- | --- |
| `tests/integration/conftest.py` | The `postgres` fixture starts and removes the container. |
| `tests/integration/test_postgres_store.py` | Adapter, SQL scripts and the real server command. |
| `Makefile` | `make test-integration`; the CI job `integration`. |

## 4. How it works underneath

The fixture runs `docker run -d --rm --name <unique> -p 127.0.0.1:<port>:5432 -e POSTGRES_USER=app -e POSTGRES_DB=app -e POSTGRES_PASSWORD=<pw> -v <file>:/docker-entrypoint-initdb.d/<file>:ro postgres:17-alpine`. `-e` sets environment variables the image reads to create the user, database and password; `-v host:container:ro` mounts a file read-only into the container, so the image runs `001_schema.sql` and `002_seed.sql` as its init scripts. The fixture then polls `psql` inside the container (`docker exec`) until `SELECT count(*) FROM visits` answers `1`, because the image restarts the server once after the scripts. The generator-style fixture `yield`s the details and removes the container in `finally`.

`concurrent.futures.ThreadPoolExecutor` runs 80 visits on 8 threads at once; the test then checks the next visit is exactly 81 higher, proving no update was lost.

## 5. Walkthrough of this repository's use

### `tests/integration/conftest.py`

```text
"""A real Postgres in a throwaway container with the repository's own SQL scripts applied as its init scripts."""

from __future__ import annotations

import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

POSTGRES_IMAGE = "postgres:17-alpine"
PASSWORD = "integration-test-password"
SQL = Path(__file__).resolve().parents[2] / "sql"
```

The docstring says what the file does. `POSTGRES_IMAGE = "postgres:17-alpine"`, a dummy `PASSWORD`, and `SQL`, the repository's `sql` folder (two levels up from this file).

```text
@dataclass(frozen=True)
class RunningPostgres:
    container: str
    host: str
    port: int
    password: str

    def psql(self, *arguments: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        """Run psql inside the container as the app user."""
        return subprocess.run(
            ["docker", "exec", "-i", "-e", f"PGPASSWORD={self.password}", self.container,
             "psql", "-U", "app", "-d", "app", "-v", "ON_ERROR_STOP=1", *arguments],
            input=stdin, capture_output=True, text=True, check=False,
        )  # fmt: skip


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
```

`RunningPostgres` is a frozen record of the container name, host, port and password, with a method `psql(*arguments, stdin=None)` that runs the `psql` client inside the container as the app user (`docker exec -i -e PGPASSWORD=... <container> psql -U app -d app -v ON_ERROR_STOP=1 ...`) and returns the finished process. `_free_port()` asks the operating system for a free port (bind port 0).

```text
@pytest.fixture(scope="session")
def postgres() -> Iterator[RunningPostgres]:
    name = f"harden-test-pg-{uuid.uuid4().hex[:8]}"
    port = _free_port()
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1:{port}:5432",
         "-e", "POSTGRES_USER=app", "-e", "POSTGRES_DB=app", "-e", f"POSTGRES_PASSWORD={PASSWORD}",
         "-v", f"{SQL / '001_schema.sql'}:/docker-entrypoint-initdb.d/001_schema.sql:ro",
         "-v", f"{SQL / '002_seed.sql'}:/docker-entrypoint-initdb.d/002_seed.sql:ro",
         POSTGRES_IMAGE],
        check=True, capture_output=True,
    )  # fmt: skip
    server = RunningPostgres(name, "127.0.0.1", port, PASSWORD)
    try:
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            # The image restarts the server once after running the init scripts, so wait for the real one.
            if server.psql("-tAc", "SELECT count(*) FROM visits").stdout.strip() == "1":
                break
            time.sleep(1)
        else:
            raise RuntimeError("postgres did not become ready within 300 seconds")
        yield server
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
```

The session-wide `postgres` fixture creates a unique container name, picks a port and starts the container with the environment variables and the two mounted SQL files. In the `try` block a loop of up to 300 seconds runs `SELECT count(*) FROM visits` until it prints `1` (the seed row exists, so the real server is up); `while ... else` raises an error if the deadline passes. It yields the record and, in `finally`, force-removes the container.

### `tests/integration/test_postgres_store.py`

```text
import concurrent.futures
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tenant_web.domain.errors import StoreUnavailableError
from tenant_web.infrastructure.postgres_store import PostgresVisitStore, build_pool
from tenant_web.infrastructure.settings import Settings

pytestmark = pytest.mark.integration
SQL = Path(__file__).resolve().parents[2] / "sql"
```

Imports for threads, processes, HTTP and the adapter; `pytestmark` marks all tests `integration`; `SQL` as before.

```text
def _settings(server, **overrides):
    env = {
        "TEAM_NAME": "team-a",
        "DB_HOST": server.host,
        "DB_PORT": str(server.port),
        "DB_PASSWORD": overrides.pop("password", server.password),
        "DB_TIMEOUT_SECONDS": "2",
    }
    return Settings.from_env(env)


@pytest.fixture
def store(postgres):
    pool = build_pool(_settings(postgres))
    pool.open(wait=True, timeout=20)
    yield PostgresVisitStore(pool)
    pool.close()
```

`_settings(server, **overrides)` builds `Settings` from an environment dictionary pointing at the container (a different password can be passed). The `store` fixture builds a pool, opens it waiting up to 20 seconds, yields a `PostgresVisitStore` and closes the pool afterwards.

```text
def test_the_seed_row_exists_and_the_first_visit_is_counted_as_one(postgres, store):
    postgres.psql("-c", "DELETE FROM visits")
    postgres.psql("-f", "/docker-entrypoint-initdb.d/002_seed.sql")
    assert store.record_visit("/") == 1
    assert store.record_visit("/") == 2


def test_each_page_is_counted_on_its_own(store):
    first = store.record_visit("/pages/one")
    assert store.record_visit("/pages/two") == 1
    assert store.record_visit("/pages/one") == first + 1


def test_concurrent_visits_are_not_lost(postgres, store):
    before = store.record_visit("/race")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: store.record_visit("/race"), range(80)))
    assert store.record_visit("/race") == before + 81


def test_ping_works(store):
    store.ping()
```

The first test empties the table, re-applies the seed script and checks visits return 1 then 2. The second checks pages are counted independently. The third, `test_concurrent_visits_are_not_lost`, records one visit, runs 80 more on a pool of 8 threads and expects the next to be exactly 81 higher. The fourth checks `ping()` works.

```text
def test_a_wrong_password_means_unavailable(postgres):
    pool = build_pool(_settings(postgres, password="wrong"))
    pool.open(wait=False)
    try:
        with pytest.raises(StoreUnavailableError):
            PostgresVisitStore(pool).ping()
    finally:
        pool.close()


def test_the_schema_and_seed_scripts_can_run_again_without_changing_anything(postgres, store):
    before = store.record_visit("/idempotent")
    for script in ("001_schema.sql", "002_seed.sql"):
        result = postgres.psql("-f", f"/docker-entrypoint-initdb.d/{script}")
        assert result.returncode == 0, result.stderr
    assert store.record_visit("/idempotent") == before + 1


def test_the_schema_refuses_a_negative_count(postgres):
    result = postgres.psql("-c", "UPDATE visits SET visit_count = -1 WHERE page = '/'")
    assert result.returncode != 0
    assert "visits_count_not_negative" in result.stderr
```

A wrong password: the pool is opened without waiting, and `ping()` must raise `StoreUnavailableError`. Running `001_schema.sql` and `002_seed.sql` again must exit with status 0 and not disturb the count. An `UPDATE` to a negative count must fail with the constraint name `visits_count_not_negative` in the error text.

```text
def test_the_queries_file_runs_to_the_end(postgres):
    result = postgres.psql(stdin=(SQL / "003_queries.sql").read_text())
    assert result.returncode == 0, result.stderr
    assert "visit_count" in result.stdout


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
```

The queries file runs to the end through `psql` with its text sent on standard input, and the output contains the column name `visit_count`. `_free_port` again.

```text
def test_the_real_gunicorn_command_serves_visits_and_reports_ready(postgres):
    port = _free_port()
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[2] / "src"),
        "TEAM_NAME": "team-a",
        "DB_HOST": postgres.host,
        "DB_PORT": str(postgres.port),
        "DB_PASSWORD": postgres.password,
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "--bind", f"127.0.0.1:{port}", "--workers", "1", "--threads", "2",
         "--worker-class", "gthread", "tenant_web.interfaces.wsgi:build_app()"],
        env=env, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        body = b""
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/readyz", timeout=3) as response:
                    body = response.read()
                    break
            except OSError:
                time.sleep(0.2)
        assert b"ready" in body
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
            assert b'"team":"team-a"' in response.read()
    finally:
```

The last test starts the real `gunicorn` command (same shape as the image's, one worker, two threads) with the container's address in the environment, polls `/readyz` for up to 100 tries until the body contains `ready`, then calls `/` and expects the JSON to name `team-a`.

```text
        process.terminate()
        process.wait(timeout=15)
```

In `finally` the server is terminated and waited for (up to 15 seconds).


## 6. Try it yourself

```bash
make test-integration
```

Needs Docker. Starts a Postgres container, runs the tests, removes the container. Afterwards `docker ps` shows no `harden-test-pg-*` container.

```bash
docker ps --filter name=harden-test-pg
```

While the tests run, shows the temporary container.

```bash
.venv/bin/python -m pytest tests/integration -q -m integration -k concurrent
```

Runs only the concurrency test.

## 7. Mistakes people make

- **A fixed port.** Two runs would collide; a random free port avoids it.
- **No cleanup on failure.** `try/finally` guarantees the container is removed.
- **Connecting between the two server starts.** The image restarts Postgres after the init scripts; the fixture waits for the real server.
- **Sharing rows between tests.** Tests use distinct page names (`/race`, `/idempotent`).
- **A real password in the test.** The one here is a dummy used only by a container that exists for seconds.

## 8. Check yourself

1. Why is the Postgres container started with `--rm`? *It disappears when stopped, leaving nothing behind.*
2. What do the `-v ...:ro` mounts do? *Place the SQL files where the image runs them as init scripts, read-only.*
3. What does the concurrency test prove? *Eighty parallel upserts are all counted.*
4. Why does a test run the schema and seed scripts again? *To prove they are idempotent.*
5. What does `test_the_schema_refuses_a_negative_count` prove? *The `CHECK` constraint is enforced by the database.*

## 9. Further reading

- Docker `run` reference: https://docs.docker.com/reference/cli/docker/container/run/
- pytest fixtures with yield: https://docs.pytest.org/en/stable/how-to/fixtures.html#yield-fixtures-recommended
- Python `subprocess.Popen`: https://docs.python.org/3.13/library/subprocess.html#popen-constructor
- Python `socket`: https://docs.python.org/3.13/library/socket.html
