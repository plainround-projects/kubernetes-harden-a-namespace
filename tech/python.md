# Python

## 1. What it is

Python is a programming language. You write instructions in plain text files that end in `.py`, and a program called the **interpreter** (the command `python`) reads those files and carries out the instructions one by one. This repository uses Python 3.13 on the developer's machine and in the container image (the project accepts 3.12 or newer, which is what `requires-python = ">=3.12"` in `pyproject.toml` says).

A few words used throughout this file:

- A **module** is one `.py` file. A **package** is a folder of modules that has an `__init__.py` file in it. Here `tenant_web` is a package, and `tenant_web/domain/values.py` is a module inside it.
- A **function** is a named piece of code that you can run by writing its name followed by brackets. A **class** is a recipe for making objects: it says what data an object holds and what it can do. A **method** is a function that belongs to a class.
- A **type hint** is a note such as `value: int` that says what kind of value a name holds. Python does not enforce hints when it runs; a separate tool (mypy, described in `mypy.md`) reads them and reports mistakes.
- An **exception** is a signal that something went wrong. Code can `raise` one, and other code can `catch` it with `try` and `except`. If nobody catches it the program stops and prints where it happened.

## 2. Why this repository uses it

The lesson hardens a namespace, so it needs a small but real workload to protect: a "tenant web service" that counts visits in Postgres, deployed once per team. Python keeps it readable, and the same language writes the tests that attack the namespace and look for the evidence. The app is laid out in layers (domain, application, infrastructure, interfaces) so you can see how a real service is organised, even though it only counts visits.

## 3. Where it appears

| File or folder | What it does with Python |
| --- | --- |
| `src/tenant_web/domain/` | The rules and values: a team name and a visit count. |
| `src/tenant_web/application/` | The use cases and the port they need. |
| `src/tenant_web/infrastructure/settings.py`, `logging.py` | Reading configuration from the environment and writing log lines. |
| `src/tenant_web/infrastructure/postgres_store.py` | The Postgres adapter (see `postgres.md`). |
| `src/tenant_web/interfaces/` | The web routes (`flask.md`) and the start-up code (`gunicorn.md`). |
| `tests/` | The tests (`pytest.md`). |
| `pyproject.toml` | Declares the package and the tools that check it (`toml.md`). |

## 4. How it works underneath

When you run `python something.py`, the interpreter does these things in order. It starts a **process** (a running program with its own memory). It reads the file, turns it into an internal form, and runs the top-level statements from the first line to the last. A statement such as `import json` finds the module named `json`, runs it once, and gives you its contents under that name. A `def` or `class` statement does not run its body; it creates the function or class and stores it under its name. The body runs later, when somebody calls it.

Names live in **scopes**. A name defined at the top of a module is visible in that whole module; a name defined inside a function exists only while that function runs. Values live in memory and are cleaned up automatically when nothing refers to them any more.

Python finds modules by searching a list of folders (`sys.path`). In this repository the package is installed into a **virtual environment**, a private copy of Python's libraries kept in the `.venv/` folder, so that the versions this project needs do not clash with anything else on the machine. `make install` creates it from the lock file.

Output goes to two numbered channels the operating system gives every process: **standard output** (for results) and **standard error** (for diagnostics). This app writes its log lines to standard error, which is the channel Kubernetes shows when you run `kubectl logs`.

Environment variables (named settings that a process inherits from whoever started it) are read with `os.environ`. A container platform passes configuration to a program this way, which is why `settings.py` reads them.

## 5. Walkthrough of this repository's use

Every file of the `tenant_web` package that is not a web or database detail is explained here, in the order domain, application, infrastructure. The web routes, the database calls and the start-up file have their own notes.

### `src/tenant_web/__init__.py`

```text
"""A small tenant web service backed by Postgres: the workload the namespace hardening protects."""

__version__ = "0.1.0"
```

The docstring (text in triple quotes at the top of a file, which Python stores as the module's documentation) says what the package is. `__version__ = "0.1.0"` is a variable holding the version number. The file's presence makes the folder a package.

### `src/tenant_web/domain/__init__.py`

```text
"""Domain: the team name and the visit count. Depends on nothing outside the standard library."""
```

A one-line docstring that states the layer's rule: the domain depends on nothing outside the standard library.

### `src/tenant_web/domain/errors.py`

```text
"""Named errors the layers above translate into responses, log lines and exit codes."""


class TenantError(Exception):
    """Base class of every error this service raises on purpose."""


class InvalidTeamNameError(TenantError):
    """A team name that is not a valid Kubernetes namespace label."""


class InvalidCountError(TenantError):
    """A visit count that is not a positive integer."""


class StoreUnavailableError(TenantError):
    """The database cannot be reached or refused the command."""
```

A base class `TenantError(Exception)` for every error the service raises on purpose; code that wants to catch "any error of ours" catches this one. The three subclasses are named after what went wrong: `InvalidTeamNameError` (the name is not a valid namespace label), `InvalidCountError` (the count is not a positive integer) and `StoreUnavailableError` (the database cannot be reached or refused the command). A class with only a docstring has no other behaviour; its name is its meaning.

### `src/tenant_web/domain/values.py`

```text
"""Immutable values: a team's name and a count of visits."""

from __future__ import annotations

import re
from dataclasses import dataclass

from tenant_web.domain.errors import InvalidCountError, InvalidTeamNameError

_DNS_LABEL = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?")


@dataclass(frozen=True, slots=True)
class TeamName:
    """A team's name, which is also its namespace: a lower-case DNS label."""

    value: str

    def __post_init__(self) -> None:
        """Reject anything Kubernetes would not accept as a namespace name."""
        if not _DNS_LABEL.fullmatch(self.value):
            raise InvalidTeamNameError(f"a team name must be a lower-case DNS label, got {self.value!r}")
```

`import re` loads regular expressions, the pattern language for text. `_DNS_LABEL = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?")` compiles the pattern once: a lower-case letter or digit, then optionally up to 61 letters, digits or hyphens, ending in a letter or digit; that is at most 63 characters, no capital letters, no underscores, and no hyphen at either end (the Kubernetes rule for names). The leading underscore marks the name as private to the module. `@dataclass(frozen=True, slots=True)` turns the class into a record: Python writes `__init__`, `__repr__` and equality for you; `frozen` forbids changing fields after creation; `slots` stores fields compactly. `TeamName` has one field, `value`. `__post_init__` runs right after creation: `fullmatch` requires the pattern to match the whole string, and if it does not, `InvalidTeamNameError` is raised with the offending text shown by `!r` (the `repr`, with quotes).

```text
@dataclass(frozen=True, slots=True)
class VisitCount:
    """How many times a page has been visited. The first visit is 1."""

    value: int

    def __post_init__(self) -> None:
        """Reject anything but a positive integer."""
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 1:
            raise InvalidCountError(f"a visit count must be a positive integer, got {self.value!r}")
```

`VisitCount` is another frozen record. Its check rejects `bool` first (since `True` is an `int` in Python), then anything that is not an `int`, then anything below 1. The first visit is 1, never 0.

### `src/tenant_web/application/__init__.py`

```text
"""Application: the use cases and the ports they need. Depends on the domain only."""
```

A one-line docstring: this layer holds use cases and ports and depends on the domain only.

### `src/tenant_web/application/ports.py`

```text
"""What the use cases need from the outside world."""

from __future__ import annotations

from typing import Protocol


class VisitStore(Protocol):
    """Where visit counts live."""

    def record_visit(self, page: str) -> int:
        """Add one visit to a page and return its new total. Raises StoreUnavailableError when the store is down."""
        ...

    def ping(self) -> None:
        """Return when the store answers. Raises StoreUnavailableError when it does not."""
        ...
```

A **port** is an interface the application needs from the outside. `Protocol` (from `typing`) defines a type by the methods it has; any object with these methods fits, without inheriting from anything. `VisitStore` needs two methods: `record_visit(page)` adds one to a page's counter and returns the new total (raising `StoreUnavailableError` when the store is down), and `ping()` returns when the store answers. The body `...` means "no code here, this is only the shape". `from __future__ import annotations` lets type hints be written freely.

### `src/tenant_web/application/use_cases.py`

```text
"""The service's three questions: count a visit, are you ready, are you alive."""

from __future__ import annotations

from dataclasses import dataclass

from tenant_web.application.ports import VisitStore
from tenant_web.domain.errors import StoreUnavailableError
from tenant_web.domain.values import TeamName, VisitCount


@dataclass(frozen=True, slots=True)
class VisitReceipt:
    """What a visit returns: whose service answered and the page's new total."""

    team: TeamName
    count: VisitCount


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """The answer to "should the Service send me traffic right now?"."""
```

`VisitReceipt` is a frozen record of the answer to one visit: the `team` (a `TeamName`) and the `count` (a `VisitCount`). `ReadinessReport` begins here, with the docstring explaining that it answers "should the Service send me traffic right now?".

```text
    ready: bool
    reason: str


class RecordVisit:
    """Count one visit to a page for this team's service."""

    def __init__(self, team: TeamName, store: VisitStore) -> None:
        """Bind the team and its store."""
        self._team = team
        self._store = store

    def __call__(self, page: str = "/") -> VisitReceipt:
        """Count the visit and return the receipt."""
        return VisitReceipt(self._team, VisitCount(self._store.record_visit(page)))


class CheckReadiness:
    """Ready means the database answers right now."""
```

Its two fields, `ready` (a bool) and `reason` (text). `RecordVisit` is a use case written as a class with `__call__`, so an instance is used like a function: `record_visit("/")`. The constructor stores the team and the store; calling it asks the store to record the visit for the page (default `"/"`) and wraps the number in a `VisitCount` (which validates it) and a `VisitReceipt`. `CheckReadiness` begins.

```text
    def __init__(self, store: VisitStore) -> None:
        """Bind the store."""
        self._store = store

    def __call__(self) -> ReadinessReport:
        """Ask the store; never raise, because a failing database is a normal answer here."""
        try:
            self._store.ping()
        except StoreUnavailableError as error:
            return ReadinessReport(ready=False, reason=str(error))
        return ReadinessReport(ready=True, reason="database reachable")
```

Its constructor stores the store. Calling it runs `ping()` in a `try`; if the store raises `StoreUnavailableError` it returns a report with `ready=False` and the error text as the reason; otherwise `ready=True`. It never raises, because "the database is down" is an ordinary answer for a readiness check.

### `src/tenant_web/infrastructure/__init__.py`

```text
"""Infrastructure: the Postgres adapter, environment settings and logging."""
```

A one-line docstring: this layer holds the Postgres adapter, the environment settings and the logging.

### `src/tenant_web/infrastructure/settings.py`

```text
"""Configuration from the environment (twelve-factor), validated once at startup."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from tenant_web.domain.errors import InvalidTeamNameError
from tenant_web.domain.values import TeamName

LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


class ConfigurationError(Exception):
    """An environment variable is missing or malformed. The message names the variable."""


@dataclass(frozen=True, slots=True)
class Settings:
    """What the service reads from its environment. The password never appears in a repr."""
```

The docstring names the idea (the "twelve-factor" rule: configuration lives in the environment). `Mapping` is the type of a read-only dictionary; `dataclass` and `field` build records. `LOG_LEVELS` is a `frozenset` (an immutable set) of the accepted level names. `ConfigurationError` is the error raised when a variable is missing or wrong; its message always names the variable. `Settings` is a frozen record of everything the service reads; the docstring notes the password never appears in a repr.

```text
    team: TeamName
    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "app"
    db_user: str = "app"
    db_password: str = field(default="", repr=False)
    db_timeout_seconds: float = 3.0
    pool_size: int = 4
    log_level: str = "INFO"
```

The fields and their defaults: `team` (required, a `TeamName`), `db_host="db"`, `db_port=5432` (Postgres's standard port), `db_name="app"`, `db_user="app"`, `db_password` (default empty, declared with `field(..., repr=False)` so it is left out of the printed form), `db_timeout_seconds=3.0`, `pool_size=4` (how many database connections are kept) and `log_level="INFO"`.

```text
    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        """Build settings from a mapping such as os.environ; TEAM_NAME and DB_PASSWORD are required."""
        try:
            team = TeamName(env.get("TEAM_NAME", ""))
        except InvalidTeamNameError as error:
            raise ConfigurationError(f"TEAM_NAME: {error}") from error
        password = env.get("DB_PASSWORD", "")
        if not password:
            raise ConfigurationError("DB_PASSWORD must be set (the cluster supplies it from a Secret)")
        log_level = env.get("LOG_LEVEL", "INFO").upper()
        if log_level not in LOG_LEVELS:
            raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(LOG_LEVELS)}, got {log_level!r}")
        return cls(
            team=team,
            db_host=_text(env, "DB_HOST", "db"),
            db_port=int(_number(env, "DB_PORT", 5432, 1, 65535)),
            db_name=_text(env, "DB_NAME", "app"),
            db_user=_text(env, "DB_USER", "app"),
            db_password=password,
            db_timeout_seconds=_number(env, "DB_TIMEOUT_SECONDS", 3.0, 0.1, 60),
            pool_size=int(_number(env, "DB_POOL_SIZE", 4, 1, 64)),
            log_level=log_level,
        )
```

`from_env` is a class method (it creates an instance) that takes any mapping such as `os.environ`. It builds the team name and turns a bad one into a `ConfigurationError` naming `TEAM_NAME`; requires a non-empty `DB_PASSWORD`; upper-cases and checks `LOG_LEVEL`; and finally builds the record, using two helper functions to read text and numbers with defaults and limits (for example the port must be between 1 and 65535, the timeout between 0.1 and 60 seconds, the pool size between 1 and 64).

```text
def _text(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, default).strip()
    if not value:
        raise ConfigurationError(f"{name} must not be empty")
    return value


def _number(env: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from None
    if not low <= value <= high:
        raise ConfigurationError(f"{name} must be between {low} and {high}, got {value}")
    return value
```

`_text` returns a variable's stripped text, or its default, and refuses an empty value. `_number` returns the default if the variable is absent; otherwise it converts to a float (a failure becomes a `ConfigurationError` naming the variable, with `from None` hiding the noisy original) and checks the value lies between `low` and `high`.

### `src/tenant_web/infrastructure/logging.py`

```text
"""Structured logging: one JSON object per line on standard error, never a secret."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

_RESERVED = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Render a record as {"ts", "level", "logger", "msg", ...extra fields}."""
```

The docstring says: one JSON object per line on standard error, never a secret. `_RESERVED` is the set of attribute names every log record already has (found by creating an empty record with `logging.makeLogRecord({})` and listing its attributes) plus `message` and `asctime`; anything else on a record is an "extra" field the caller added. `JsonFormatter` is a subclass of the standard `logging.Formatter`; its docstring lists the keys of the output.

```text
    def format(self, record: logging.LogRecord) -> str:
        """Return the record as one line of JSON; extra keyword fields become top-level keys."""
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        entry.update({key: value for key, value in record.__dict__.items() if key not in _RESERVED})
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str) -> None:
    """Send every log record to standard error as JSON at the given level."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
```

`format` builds a dictionary with `ts` (the record's creation time converted to UTC, in ISO text with millisecond precision), `level`, `logger` (the logger's name) and `msg` (the message with its arguments filled in). The extra fields are added as top-level keys; if the record carries exception information, the formatted traceback goes in `exc`. `json.dumps(entry, default=str)` turns the dictionary into one line of JSON, converting any value JSON does not know into text. `configure_logging(level)` creates a handler writing to standard error, gives it the JSON formatter, replaces the root logger's handlers with just that one and sets the level.

### `src/tenant_web/interfaces/__init__.py`

```text
"""Interfaces: the HTTP transport and the composition root. Nothing depends on this layer."""
```

A one-line docstring that states the layer's rule: the interfaces layer is the outermost one, so nothing else imports from it. The file makes the folder a package.


## 6. Try it yourself

All commands run from the repository folder after `make install`.

```bash
.venv/bin/python -c "from tenant_web.domain.values import TeamName; print(TeamName('team-a'))"
```

Prints `TeamName(value='team-a')`.

```bash
.venv/bin/python -c "from tenant_web.domain.values import TeamName; TeamName('Team A')" 2>&1 | tail -1
```

Ends with `InvalidTeamNameError: a team name must be a lower-case DNS label, got 'Team A'`.

```bash
.venv/bin/python -c "
from tenant_web.infrastructure.settings import Settings
print(Settings.from_env({'TEAM_NAME': 'team-a', 'DB_PASSWORD': 'x'}))"
```

Prints a `Settings(...)` line with `team=TeamName(value='team-a')`, `db_host='db'` and no password in it.

```bash
.venv/bin/python -c "
from tenant_web.infrastructure.settings import Settings
Settings.from_env({'TEAM_NAME': 'team-a'})" 2>&1 | tail -1
```

Ends with `ConfigurationError: DB_PASSWORD must be set (the cluster supplies it from a Secret)`.

```bash
.venv/bin/python -m pytest tests/unit -q
```

Runs the unit tests and prints a line such as `NN passed`.

## 7. Mistakes people make

- **Changing a value that should not change.** `@dataclass(frozen=True)` makes `TeamName` and `VisitCount` read-only.
- **Swallowing errors.** The code catches only the named errors it expects (`PsycopgError`, `PoolTimeout`, `ConfigurationError`) and turns each into another named error.
- **Putting settings in the code.** Every setting comes from the environment and is checked once at start-up.
- **Forgetting that `bool` is an `int`.** `VisitCount(True)` would pass a naive check; the code tests `isinstance(self.value, bool)` first.
- **Printing secrets.** The password field is declared `repr=False`, so no log line or traceback can show it.

## 8. Check yourself

1. What is the difference between a module and a package? *A module is one `.py` file; a package is a folder of modules with an `__init__.py`.*
2. Why must a team name be a DNS label? *The team name is also the Kubernetes namespace name, which only accepts lower-case letters, digits and hyphens, at most 63 characters.*
3. Why is the password marked `repr=False`? *So printing or logging a `Settings` object never shows the password.*
4. What does `from None` do in `raise ConfigurationError(...) from None`? *It hides the original `ValueError` from the traceback because the new message says everything.*
5. What does `CheckReadiness` do when the database is down? *It returns a report saying not ready instead of raising, because a down database is a normal answer.*

## 9. Further reading

- Python 3.13 documentation: https://docs.python.org/3.13/
- The tutorial: https://docs.python.org/3.13/tutorial/index.html
- `dataclasses`: https://docs.python.org/3.13/library/dataclasses.html
- `typing.Protocol`: https://docs.python.org/3.13/library/typing.html#typing.Protocol
- `logging`: https://docs.python.org/3.13/library/logging.html
