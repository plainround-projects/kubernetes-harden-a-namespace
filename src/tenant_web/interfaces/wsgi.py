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
