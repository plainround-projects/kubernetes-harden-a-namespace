# Flask

## 1. What it is

Flask is a **web framework** for Python: a library that lets a program answer web requests. A web request is a message a client (a browser, `curl`, another program) sends over the network using the **HTTP** protocol: it names a **method** (`GET` to read something) and a **path** (`/healthz`). The program replies with a **status code** (200 means success, 404 not found, 503 service unavailable) and usually a body. Flask matches the path of each request to a Python function you wrote (a **route**) and turns what the function returns into the reply. This repository uses Flask 3.1.

## 2. Why this repository uses it

The tenant service needs three HTTP endpoints: one that counts a visit and says which team answered, one for the "am I alive" probe and one for the "can I serve traffic" probe. Flask is the smallest well-known way to write that. The lesson attacks the namespace around this app, so the app itself stays tiny.

## 3. Where it appears

| File | Role |
| --- | --- |
| `src/tenant_web/interfaces/http.py` | Defines the app and its three routes. |
| `src/tenant_web/interfaces/wsgi.py` | Builds the app for the server (see `gunicorn.md`). |
| `tests/unit/test_http.py` | Calls the routes with Flask's test client, without a network. |
| `pyproject.toml`, `requirements.lock` | Pin Flask and its exact version. |

## 4. How it works underneath

A Flask application is a Python object (`Flask(__name__)`). It does not listen on the network itself. It follows **WSGI**, a standard that describes how a web server and a Python application talk: the server hands the application a description of the request, the application hands back the status, headers and body. That is why a separate server (gunicorn) is used in production. In tests there is no server: Flask offers a **test client** that builds the request description in memory and calls the application directly.

A route is registered with a **decorator**, a line starting with `@` above a function. `@app.get("/healthz")` tells the app "when a `GET` request for `/healthz` arrives, call this function". Whatever the function returns becomes the reply. `jsonify(...)` builds a reply whose body is JSON text and whose `Content-Type` header says so. Returning a tuple `(reply, 503)` sets the status code.

Each request is handled by a function call; between requests the process keeps its memory. The app here keeps no counter in memory: all state lives in the database, so many copies of the process can run at once and agree.

## 5. Walkthrough of this repository's use

### `src/tenant_web/interfaces/http.py`

```text
"""The HTTP surface: GET / counts a visit, GET /healthz is liveness, GET /readyz is readiness."""

from __future__ import annotations

import logging
import socket
from collections.abc import Callable

from flask import Flask, Response, jsonify

from tenant_web.application.use_cases import CheckReadiness, RecordVisit
from tenant_web.domain.errors import TenantError

log = logging.getLogger(__name__)


def create_app(record_visit: RecordVisit, check_readiness: CheckReadiness, check_liveness: Callable[[], bool]) -> Flask:
    """Build the Flask app around the use cases; it holds no state of its own."""
    app = Flask(__name__)
    pod = socket.gethostname()
```

The docstring lists the three routes. The imports: `logging`, `socket`, `Callable` (a type for "anything callable"), then from Flask the application class, the `Response` type and `jsonify` (builds a JSON reply). The use cases and the base error `TenantError` come from the inner layers. `log` is the module's logger. `create_app(record_visit, check_readiness, check_liveness)` is a **factory**: it receives the three things the routes need, so it never builds a database connection itself. Inside, `app = Flask(__name__)` creates the application and `pod = socket.gethostname()` stores the machine's host name once; in Kubernetes the host name of a container is the pod's name, so every answer shows which pod served it.

```text
    @app.get("/")
    def visit() -> Response | tuple[Response, int]:
        try:
            receipt = record_visit("/")
        except TenantError as error:
            log.warning("could not record a visit", extra={"error": str(error)})
            return jsonify(error="database unavailable"), 503
        return jsonify(team=receipt.team.value, visits=receipt.count.value, pod=pod)

    @app.get("/healthz")
    def healthz() -> Response | tuple[Response, int]:
        if check_liveness():
            return jsonify(status="alive")
        return jsonify(status="stuck"), 500

    @app.get("/readyz")
    def readyz() -> Response | tuple[Response, int]:
        report = check_readiness()
        if report.ready:
            return jsonify(status="ready")
        return jsonify(status="not ready", reason=report.reason), 503
```

`@app.get("/")` registers `visit()`. In a `try`, `record_visit("/")` counts a visit to the page `/`. If the database is down the use case raises a `TenantError` subclass; the handler logs a warning with the error attached as an extra field and returns `jsonify(error="database unavailable"), 503`. On success it returns `jsonify(team=..., visits=..., pod=pod)`. `@app.get("/healthz")` is liveness: if the injected check is true it answers `{"status": "alive"}`, otherwise 500 with `"stuck"`; it never touches the database. `@app.get("/readyz")` runs `check_readiness()` and answers `{"status": "ready"}` or, with status 503, `{"status": "not ready", "reason": ...}`. A 503 makes the kubelet mark the pod not ready and the Service stops sending it traffic.

```text
    return app
```

`return app` hands the finished application back to the caller.


## 6. Try it yourself

```bash
.venv/bin/python - <<'PY'
from tenant_web.application.use_cases import CheckReadiness, RecordVisit
from tenant_web.domain.values import TeamName
from tenant_web.interfaces.http import create_app
class Store:
    n = 0
    def record_visit(self, page): Store.n += 1; return Store.n
    def ping(self): return None
client = create_app(RecordVisit(TeamName("team-a"), Store()), CheckReadiness(Store()), lambda: True).test_client()
print(client.get("/").get_json(), client.get("/healthz").status_code, client.get("/readyz").get_json())
PY
```

Prints `{'pod': '<host name>', 'team': 'team-a', 'visits': 1} 200 {'status': 'ready'}`. No server and no database were involved.

```bash
.venv/bin/python -m pytest tests/unit/test_http.py -q
```

Five tests pass; each calls a route through the test client.

```bash
make up && make run
```

The attacks run as a developer of team A (the app's own routes are called by `make smoke`, which opens a port-forward to `svc/web`).

## 7. Mistakes people make

- **Using Flask's built-in development server in production.** This repository serves the app with gunicorn (`gunicorn.md`).
- **Keeping state in a global variable.** With several processes each would have its own copy. The counts live in Postgres.
- **Letting an exception become a 500 page.** `visit()` catches the service's own `TenantError` and answers `503` with a short JSON message.
- **Making the health check depend on everything.** `/healthz` never calls the database, so a database outage does not make Kubernetes restart healthy pods.
- **Starting the app on import.** `create_app` is a function; nothing starts until it is called.

## 8. Check yourself

1. What does `@app.get("/")` do? *It registers the function below it as the handler for `GET` requests to `/`.*
2. Why does `visit()` return `jsonify(...), 503` in one branch? *The second element of a returned tuple is the status code.*
3. Why is there no `app.run()` anywhere? *gunicorn runs the app; Flask only describes the routes.*
4. What is the test client for? *Calling routes in memory, with no network and no server.*
5. Which answer names the team? *`GET /` returns `team`, `visits` and `pod`.*

## 9. Further reading

- Flask 3.1 documentation: https://flask.palletsprojects.com/en/stable/
- Quickstart: https://flask.palletsprojects.com/en/stable/quickstart/
- Testing: https://flask.palletsprojects.com/en/stable/testing/
- WSGI: https://wsgi.readthedocs.io/en/latest/
