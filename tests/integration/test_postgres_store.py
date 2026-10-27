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


def test_the_queries_file_runs_to_the_end(postgres):
    result = postgres.psql(stdin=(SQL / "003_queries.sql").read_text())
    assert result.returncode == 0, result.stderr
    assert "visit_count" in result.stdout


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


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
        process.terminate()
        process.wait(timeout=15)
