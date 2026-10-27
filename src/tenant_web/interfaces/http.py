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

    return app
