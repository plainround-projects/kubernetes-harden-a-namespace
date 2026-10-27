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
