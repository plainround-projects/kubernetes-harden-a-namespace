# PostgreSQL, SQL and psycopg

## 1. What it is

**PostgreSQL** ("Postgres") is a **relational database**: a server program that stores data in **tables** (like spreadsheets with strict columns), keeps it on disk, and lets many programs read and change it safely at the same time. Programs talk to it in **SQL** (Structured Query Language), a language of short statements such as `SELECT` (read rows), `INSERT` (add rows) and `UPDATE` (change rows). **psycopg** (version 3) is the Python library that opens a connection to Postgres and sends SQL; **psycopg_pool** adds a **connection pool**, a small set of already-open connections that requests borrow and return so each request does not pay the cost of connecting.

Words used throughout:

- A **table** has named, typed **columns**; each **row** is one record. A **primary key** is a column (or set) whose value is unique per row and identifies it.
- A **constraint** is a rule the database enforces itself (`NOT NULL`, `CHECK (visit_count >= 0)`, `PRIMARY KEY`).
- A **transaction** is a group of statements that succeed or fail together. Without an explicit one, each statement is its own transaction.
- **DDL** (Data Definition Language) statements create structure (`CREATE TABLE`); **DML** (Data Manipulation Language) statements change data (`INSERT`).
- **Idempotent** means running it twice has the same effect as once.

## 2. Why this repository uses it

The lesson hardens a namespace that holds a *database workload*, because a database is the thing worth stealing from: team A must not be able to read team B's data, reach its database port or read its password. Each team gets its own Postgres 17 pod with its own Secret. The web service stores one counter per page there, which also makes the tests about concurrency honest (80 simultaneous visits must all be counted).

## 3. Where it appears

| File | Role |
| --- | --- |
| `sql/001_schema.sql` | DDL: creates the `visits` table. |
| `sql/002_seed.sql` | DML: inserts the starting row. |
| `sql/003_queries.sql` | The statements the service runs, for reading and `make db-queries`. |
| `src/tenant_web/infrastructure/postgres_store.py` | The adapter: pool, `record_visit`, `ping`. |
| `manifests/base/db.yaml` | The database Deployment, Service and storage (see `kubernetes.md`). |
| `scripts/db.sh`, `scripts/create-secrets.sh` | Run the SQL in a pod; create each team's password Secret. |
| `tests/integration/` | A real Postgres in a container (`tests-integration.md`). |

## 4. How it works underneath

The Postgres server is one main process that listens on TCP port 5432 and starts one worker process per connection. A client connects, **authenticates** (here with a password) and sends statements; the server plans, runs them and returns rows. On first start the official image runs every `*.sql` and `*.sh` file in `/docker-entrypoint-initdb.d/` in name order (which is why the files are numbered `001`, `002`), then restarts the server once; the integration test waits for that.

`INSERT ... ON CONFLICT (page) DO UPDATE SET visit_count = visits.visit_count + 1 ... RETURNING visit_count` is an **upsert**: insert the row, or if a row with that primary key already exists, update it instead; `RETURNING` hands back the new value in the same step. The database locks the row for the update, so two simultaneous visits are applied one after the other and none is lost.

Parameters: the statement contains `%s` placeholders and the values are sent separately (`(page,)`), never pasted into the text. This stops **SQL injection**, where input like `'; DROP TABLE visits; --` is read as SQL.

A pool keeps `min_size` connections open and creates more up to `max_size` when busy. `timeout` is how long a request waits for a free connection before `PoolTimeout`. `open=False` creates the pool closed, and `pool.open(wait=False)` starts connecting in the background so the web process can start before the database is ready.

## 5. Walkthrough of this repository's use

### `sql/001_schema.sql`

```sql
-- DDL for a team's database. Idempotent: the Postgres image runs it from /docker-entrypoint-initdb.d on first
-- start, and `make db` can run it again against a running database.

CREATE TABLE IF NOT EXISTS visits (
    page          text        PRIMARY KEY,
    visit_count   bigint      NOT NULL DEFAULT 0 CONSTRAINT visits_count_not_negative CHECK (visit_count >= 0),
    last_visit_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE  visits               IS 'One row per page the team''s web service has served; the service increments visit_count.';
COMMENT ON COLUMN visits.page          IS 'The request path, for example /.';
COMMENT ON COLUMN visits.visit_count   IS 'Visits since the row was created. Only ever increased by the service.';
COMMENT ON COLUMN visits.last_visit_at IS 'When the service last counted a visit to this page.';
```

Lines starting `--` are SQL comments. `CREATE TABLE IF NOT EXISTS visits (...)` creates the table only if it is missing, which makes the script idempotent. The columns: `page text PRIMARY KEY` (the request path, unique per row); `visit_count bigint NOT NULL DEFAULT 0 CONSTRAINT visits_count_not_negative CHECK (visit_count >= 0)` (a 64-bit whole number, never empty, zero if not given, and never negative; the constraint is named so error messages say which rule broke); `last_visit_at timestamptz NOT NULL DEFAULT now()` (a time with its time zone, set to the current time if not given). The four `COMMENT ON` statements store a description of the table and each column inside the database itself (a doubled `''` inside a quoted string is one apostrophe).

### `sql/002_seed.sql`

```sql
-- DML: the starting data. The home page exists with zero visits, so the first request returns 1.
-- Idempotent: running it again changes nothing.

INSERT INTO visits (page, visit_count)
VALUES ('/', 0)
ON CONFLICT (page) DO NOTHING;
```

DML: `INSERT INTO visits (page, visit_count) VALUES ('/', 0)` adds the home page with zero visits, so the first request returns 1. `ON CONFLICT (page) DO NOTHING` makes it idempotent: if the row exists nothing changes.

### `sql/003_queries.sql`

```sql
-- The statements the service runs, each with a line on what it shows. Run them with `make db-queries`.

-- Record a visit: create the page's row on first use, otherwise add one. This is the service's only write.
INSERT INTO visits (page, visit_count) VALUES ('/', 1)
ON CONFLICT (page) DO UPDATE SET visit_count = visits.visit_count + 1, last_visit_at = now()
RETURNING visit_count;

-- Readiness: the cheapest statement that proves the database accepts this user's connection and answers.
SELECT 1;

-- Look at the counters: what the team's service has served so far.
SELECT page, visit_count, last_visit_at FROM visits ORDER BY page;
```

Three statements, each with a comment. The first is the service's only write, the upsert described above, here with the literal page `'/'` and starting value 1: create the row on first use, otherwise add one and refresh `last_visit_at`, and return the new count. The second, `SELECT 1;`, is the readiness query: the cheapest statement that proves the database accepts this user's connection and answers. The third lists the rows ordered by page: `SELECT page, visit_count, last_visit_at FROM visits ORDER BY page;`.

### `src/tenant_web/infrastructure/postgres_store.py`

```text
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
```

The docstring names the pool and says the statements are also in `sql/003_queries.sql`. The imports: `AbstractContextManager` and `Any`/`Protocol` for types; `Error as PsycopgError` (psycopg's base error class, imported under another name) and `ConnectionPool`, `PoolTimeout` from the pool library; the service's own error and the settings. `RECORD_VISIT` is the upsert as a text constant with a `%s` placeholder for the page; the comment reminds the reader to keep it identical to the query file.

```text
class Rows(Protocol):
    """The part of a cursor the store reads."""

    def fetchone(self) -> Any: ...


class Session(Protocol):
    """The part of a connection the store uses."""

    def execute(self, query: Any, params: Any = None) -> Rows: ...


class Connections(Protocol):
    """A source of pooled connections; psycopg_pool.ConnectionPool satisfies it and tests can stub it."""

    def connection(self) -> AbstractContextManager[Session]: ...
```

Three small `Protocol` types describe only the parts of psycopg that the store uses: `Rows.fetchone()`, `Session.execute(query, params)` and `Connections.connection()` (a context manager yielding a session). The real `ConnectionPool` fits these shapes and tests can pass simple stubs.

```text
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
```

`build_pool(settings)` builds a connection string `host=... port=... dbname=... user=... connect_timeout=N` (the timeout is the configured seconds rounded, at least 1), keeps the password separately in `kwargs` so it never appears in the string, and creates a `ConnectionPool` with `min_size=1`, `max_size` from the settings, `timeout` (how long a request waits for a connection) and `open=False` (do not connect yet). `PostgresVisitStore` implements the `VisitStore` port; its constructor wraps a pool, and the docstring says each statement runs in its own short transaction on a pooled connection.

```text
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
```

`record_visit` borrows a connection with `with self._pool.connection() as connection:`, runs `RECORD_VISIT` with the page as the parameter and reads one row. A psycopg error or a `PoolTimeout` becomes `StoreUnavailableError("database write failed: ...")`; a missing row is also an error; otherwise the first column is returned as an `int`. The docstring explains the write is not retried because an increment is not idempotent. `ping` runs `SELECT 1` and turns any failure into `StoreUnavailableError("database ping failed: ...")`.

### `scripts/db.sh`

```bash
#!/usr/bin/env bash
# Run the numbered SQL scripts in order against a team's database in the cluster (default team-a).
#   db.sh [team]            001_schema.sql then 002_seed.sql (both idempotent)
#   db.sh [team] queries    003_queries.sql, the statements the service runs
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cluster

team="${1:-team-a}"
mode="${2:-apply}"
psql_in_pod() { kubectl -n "$team" exec -i deploy/db -- sh -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U app -d app -v ON_ERROR_STOP=1"; }
case "$mode" in
  apply) for file in "$ROOT"/sql/001_schema.sql "$ROOT"/sql/002_seed.sql; do log "$(basename "$file") in $team"; psql_in_pod <"$file"; done ;;
  queries) psql_in_pod <"$ROOT/sql/003_queries.sql" ;;
  *) die "usage: db.sh [team] [apply|queries]" ;;
esac
```

The comment documents the two modes. After the usual header and `require_cluster`, `team="${1:-team-a}"` and `mode="${2:-apply}"` take the arguments with defaults. `psql_in_pod()` is a function that runs `psql` (Postgres's command-line client) inside the team's database pod through `kubectl exec -i` with standard input open; `PGPASSWORD="\$POSTGRES_PASSWORD"` reads the password from the pod's own environment (the backslash keeps the local shell from expanding it), `-U app -d app` choose the user and database and `-v ON_ERROR_STOP=1` stops at the first SQL error. The `case`: `apply` loops over the schema and seed files, logs each and feeds it to `psql_in_pod` through `<"$file"`; `queries` feeds the queries file; anything else prints usage.

### `scripts/create-secrets.sh`

```bash
#!/usr/bin/env bash
# Create each team's namespace and its database Secret with a random password, unless they exist. The
# passwords are generated here, on the machine that runs the cluster, and are in no file of this repository.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cluster

read -ra team_list <<<"$TEAMS"
for team in "${team_list[@]}"; do
  kubectl create namespace "$team" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  if kubectl -n "$team" get secret db-credentials >/dev/null 2>&1; then
    log "secret db-credentials already exists in $team"
    continue
  fi
  password="$(openssl rand -hex 16)"
  kubectl -n "$team" create secret generic db-credentials --from-literal=password="$password" >/dev/null
  log "created secret db-credentials in $team"
done
```

`read -ra team_list <<<"$TEAMS"` splits the space-separated list of teams (defined in `lib.sh`) into an array. For each team: `kubectl create namespace "$team" --dry-run=client -o yaml | kubectl apply -f -` creates the namespace if it is missing (render locally, then apply; applying twice is harmless). If the Secret `db-credentials` already exists, log and `continue` with the next team, so re-running keeps the same password. Otherwise `openssl rand -hex 16` generates 32 random hex characters and `kubectl create secret generic db-credentials --from-literal=password=...` stores it. The password exists only in the cluster.


## 6. Try it yourself

```bash
make up
make db-queries
```

Runs `sql/003_queries.sql` inside team A's database pod: the upsert returns a number, `SELECT 1` returns `1`, and the last query lists the `/` page with its count and time.

```bash
kubectl -n team-a exec deploy/db -- sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U app -d app -c "\d visits"'
```

Prints the table definition: three columns, the primary key on `page`, and the check constraint `visits_count_not_negative`.

```bash
kubectl -n team-a exec deploy/db -- sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U app -d app -c "UPDATE visits SET visit_count = -1"'
```

Fails with `violates check constraint "visits_count_not_negative"`: the database refuses bad data by itself.

```bash
.venv/bin/python -m pytest tests/integration -q -m integration
```

Needs Docker; starts a throwaway Postgres 17, applies the SQL files and runs the adapter tests, including 80 concurrent visits.

## 7. Mistakes people make

- **Building SQL with string formatting.** Always pass values as parameters.
- **A database user with more rights than the app needs.** Here the `app` user owns only its own database in its own namespace, and other teams cannot reach it at all (NetworkPolicy).
- **Connecting without a timeout.** The pool fails fast instead of hanging.
- **Retrying a non-idempotent write.** The increment is not idempotent, so `record_visit` is not retried.
- **Not waiting for the second start.** The image restarts the server after the init scripts; a test that connects between the two sees a refused connection.
- **Putting the password in a manifest.** It is generated by `scripts/create-secrets.sh` and lives only in a Secret.

## 8. Check yourself

1. What does `ON CONFLICT (page) DO UPDATE` do? *Updates the existing row when the primary key already exists, otherwise inserts.*
2. Why are SQL values passed separately from the statement? *To prevent SQL injection.*
3. What does `CHECK (visit_count >= 0)` do? *The database refuses any row with a negative count.*
4. Why are the SQL files numbered? *The image runs init scripts in name order: schema first, then seed.*
5. What does `open=False` plus `pool.open(wait=False)` achieve? *The pool is built without connecting, then connects in the background so start-up does not block.*

## 9. Further reading

- PostgreSQL 17 documentation: https://www.postgresql.org/docs/17/
- `INSERT ... ON CONFLICT`: https://www.postgresql.org/docs/17/sql-insert.html
- Constraints: https://www.postgresql.org/docs/17/ddl-constraints.html
- psycopg 3: https://www.psycopg.org/psycopg3/docs/
- psycopg_pool: https://www.psycopg.org/psycopg3/docs/advanced/pool.html
- The official image's init scripts: https://hub.docker.com/_/postgres
