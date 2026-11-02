# gunicorn

## 1. What it is

gunicorn ("Green Unicorn") is a **WSGI HTTP server** for Python. A server here is a long-running program that listens on a network port, accepts connections, reads web requests and hands each one to your Python application. The command is `gunicorn`; this repository uses version 25.3 (pinned in `requirements.lock`).

## 2. Why this repository uses it

Flask can serve requests by itself, but only through a development server that is not meant for real traffic. gunicorn is the standard production choice: it starts the application, runs several worker threads, restarts a worker that dies, and shuts down cleanly when it receives the `SIGTERM` signal Kubernetes sends before it stops a pod.

## 3. Where it appears

| File | Role |
| --- | --- |
| `Dockerfile` | The `CMD` line that starts gunicorn with its options (see `docker.md`). |
| `src/tenant_web/interfaces/wsgi.py` | The factory `build_app()` that gunicorn calls to get the application. |
| `tests/unit/test_wsgi.py` | Checks the factory, including the FATAL exit. |
| `requirements.lock` | The exact version and hashes. |

## 4. How it works underneath

When gunicorn starts it runs a **master** process. The master reads the options, imports your application, opens the listening socket (a socket is the operating system's handle for a network port) and then starts one or more **worker** processes. Workers do the request handling; the master only watches them and restarts any that crash.

The `gthread` worker class used here lets each worker run several **threads**. A thread is a path of execution inside a process that shares the process's memory; four threads in one worker can handle four requests at once.

**Signals** are small messages the operating system sends to a process. `SIGTERM` means "please stop". gunicorn answers by finishing the requests it is working on, up to a time limit (`--graceful-timeout`), then exiting. That is what makes a rolling update in Kubernetes polite.

With `--preload`, the master imports (and so builds) the application *before* it starts the workers. If building the app fails, the master exits with an error instead of starting workers that fail one after another.

A command like `tenant_web.interfaces.wsgi:build_app()` is gunicorn's "application factory" syntax: `module:callable()` means "import the module and call this function to obtain the application".

## 5. Walkthrough of this repository's use

### `src/tenant_web/interfaces/wsgi.py`

```text
"""Composition root: read settings, open the pool, and build the WSGI app gunicorn serves.

gunicorn calls the factory (`tenant_web.interfaces.wsgi:build_app()`), so importing this module has no side
effects. The service does not insist on the database at start: it starts, reports not ready until the
database answers, and the Service sends it nothing until then. (A database that starts after the web pods is
normal when a namespace is created in one apply.)
"""

from __future__ import annotations

import logging
import os

from flask import Flask

from tenant_web.application.use_cases import CheckReadiness, RecordVisit
from tenant_web.infrastructure.logging import configure_logging
from tenant_web.infrastructure.postgres_store import PostgresVisitStore, build_pool
from tenant_web.infrastructure.settings import ConfigurationError, Settings
from tenant_web.interfaces.http import create_app

log = logging.getLogger("tenant_web")
```

The docstring states two facts. gunicorn calls the factory, so importing this module does nothing (no database connection is opened at import time). And start-up does not insist on the database: the service starts, reports not ready until the database answers, and the Service sends it nothing until then; the parenthesis explains why (a database that starts after the web pods is normal when a namespace is created in one apply). The imports gather the pieces: `logging`, `os`, `Flask`, the use cases, logging setup, the Postgres adapter and its pool builder, the settings and `create_app`. This file is the **composition root**: the one place where concrete pieces are chosen and connected.

```text
def build_app(env: dict[str, str] | None = None) -> Flask:
    """Assemble the app; exit with status 1 after one FATAL line if the environment is invalid."""
    environment = dict(os.environ) if env is None else env
    try:
        settings = Settings.from_env(environment)
    except ConfigurationError as error:
        configure_logging("INFO")
        log.critical(f"FATAL invalid configuration: {error}")
        raise SystemExit(1) from error
    configure_logging(settings.log_level)
    pool = build_pool(settings)
    pool.open(wait=False)
    store = PostgresVisitStore(pool)
    log.info("started", extra={"team": settings.team.value, "db_host": settings.db_host})
    return create_app(RecordVisit(settings.team, store), CheckReadiness(store), lambda: True)
```

`build_app(env=None)` reads the environment (`dict(os.environ)` copies the real one, or a test passes its own dictionary). If `Settings.from_env` raises `ConfigurationError`, it sets up logging at `INFO`, logs a critical line starting `FATAL invalid configuration:` and raises `SystemExit(1)`, which ends the process with exit code 1. After a good read it configures JSON logging, builds the connection pool with `build_pool(settings)` and calls `pool.open(wait=False)`: the pool starts opening connections in the background without making start-up wait. It wraps the pool in `PostgresVisitStore`, logs `started` with the team and database host, and returns `create_app(...)` with the two use cases and `lambda: True` for liveness (the process is alive if it can answer at all).


### The command line, option by option

The `CMD` in the `Dockerfile` (see `docker.md`) is the only place the options are written:

- `gunicorn` the program.
- `--bind 0.0.0.0:8080` listen on port 8080 on every network address of the container.
- `--workers 1` one worker process; the app is small.
- `--threads 4` four threads in that worker.
- `--worker-class gthread` the worker kind that supports threads.
- `--worker-tmp-dir /tmp` where workers keep the heartbeat files they use to tell the master they are alive. The container's root file system is read-only, so the Deployment mounts a writable `emptyDir` volume at `/tmp`.
- `--graceful-timeout 10` after `SIGTERM`, wait up to ten seconds for requests in progress.
- `--preload` build the app in the master before workers start.
- `--access-logfile -` write one line per request to standard output (`-` means standard output).
- `tenant_web.interfaces.wsgi:build_app()` the factory to call.

## 6. Try it yourself

```bash
kubectl -n team-a logs deploy/web | head -8
```

(after `make up`) Shows gunicorn's start-up lines: `Starting gunicorn`, `Listening at: http://0.0.0.0:8080`, `Using worker: gthread`, `Booting worker with pid: ...`, then the JSON line `"msg": "started"` with the team name.

```bash
.venv/bin/python -m pytest tests/unit/test_wsgi.py -q
```

Runs the factory tests: the pool is opened without waiting, and a bad configuration exits with status 1 after one FATAL line.

```bash
TEAM_NAME=BAD DB_PASSWORD=x .venv/bin/gunicorn --preload "tenant_web.interfaces.wsgi:build_app()"; echo "exit $?"
```

Prints a JSON line containing `FATAL invalid configuration: TEAM_NAME: ...` and `exit 1`-style failure: the master gave up instead of starting workers.

## 7. Mistakes people make

- **Starting the app lazily in the worker.** Without `--preload` a failing start leaves a master that keeps restarting workers.
- **Binding to `127.0.0.1` in a container.** Nothing outside the container can reach it.
- **A too-short graceful timeout.** Requests in progress are cut off when a pod is replaced.
- **Writing the heartbeat files to a read-only file system.** The worker cannot start; hence `--worker-tmp-dir /tmp` and the writable `/tmp` volume.
- **Too many workers for the memory limit.** Every worker is another copy of the interpreter.

## 8. Check yourself

1. What are the master and the workers? *The master watches and restarts; workers handle requests.*
2. What does `--preload` change? *The app is built once in the master, so a build failure stops the whole process with an error.*
3. What does `0.0.0.0` mean in `--bind`? *Listen on every network address of the machine.*
4. What happens on `SIGTERM`? *gunicorn stops accepting, finishes requests in progress (up to 10 seconds) and exits.*
5. Does this service insist on the database at start? *No: it starts, reports not ready until the database answers, and only a bad configuration is fatal.*

## 9. Further reading

- gunicorn 25.x documentation: https://gunicorn.org/
- Settings reference: https://gunicorn.org/reference/settings/
- Signals: https://gunicorn.org/signals/
- WSGI: https://wsgi.readthedocs.io/en/latest/
