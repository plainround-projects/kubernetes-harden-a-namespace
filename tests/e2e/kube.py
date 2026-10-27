"""A small typed wrapper around kubectl for the cluster tests: run, read JSON, wait, port-forward."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
Json = dict[str, Any]
ATTEMPTS = 120
RETRY_SECONDS = 8
SCRIPT_ATTEMPTS = 60
TRANSIENT = (
    "Unable to connect to the server",
    "TLS handshake timeout",
    "i/o timeout",
    "connection refused",
    "context deadline exceeded",
    "the server was unable to return a response",
    "etcdserver: request timed out",
    "net/http: request canceled",
)


def _transient(stderr: str) -> bool:
    """True when kubectl failed because the API server did not answer, as opposed to a real error."""
    return any(marker in stderr for marker in TRANSIENT)


class Kube:
    """kubectl against the project's own kubeconfig (never ~/.kube/config), scoped to one namespace."""

    def __init__(self, namespace: str = "counter") -> None:
        self.namespace = namespace
        self.env = {**os.environ, "KUBECONFIG": os.environ.get("KUBECONFIG", str(ROOT / ".kube" / "config"))}

    def run(self, *args: str, check: bool = True, timeout: float = 120) -> subprocess.CompletedProcess[str]:
        """Run kubectl in the namespace and return the finished process.

        A kubectl call that fails because the API server did not answer (a busy machine makes that happen) is
        retried for a few minutes; any other failure is returned or raised at once.
        """
        for attempt in range(1, ATTEMPTS + 1):
            try:
                result = subprocess.run(
                    ["kubectl", "-n", self.namespace, *args],
                    env=self.env,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                if attempt == ATTEMPTS:
                    raise
                continue
            if result.returncode == 0 or not _transient(result.stderr) or attempt == ATTEMPTS:
                if check:
                    result.check_returncode()
                return result
            time.sleep(RETRY_SECONDS)
        raise AssertionError("unreachable")

    def script(self, name: str, *args: str, timeout: float = 600) -> str:
        """Run one of the project's scripts and return its output; raise with the output if it fails.

        A script that stops because the cluster did not answer is run again, for up to half an hour.
        """
        for attempt in range(1, SCRIPT_ATTEMPTS + 1):
            result = subprocess.run(
                [str(ROOT / "scripts" / name), *args],
                env=self.env,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
            unreachable = "no cluster reachable" in result.stderr or _transient(result.stderr)
            if result.returncode == 0:
                return result.stdout
            if not unreachable or attempt == SCRIPT_ATTEMPTS:
                raise AssertionError(f"scripts/{name} failed:\n{result.stdout}\n{result.stderr}")
            time.sleep(30)
        raise AssertionError("unreachable")

    def get(self, *args: str) -> Json:
        """kubectl get ... -o json, parsed."""
        parsed: Json = json.loads(self.run("get", *args, "-o", "json").stdout)
        return parsed

    def pods(self, selector: str = "app=web") -> list[Json]:
        """The pods matching a label selector."""
        items: list[Json] = self.get("pods", "-l", selector)["items"]
        return items

    def events(self, pod_name: str) -> list[str]:
        """The event messages recorded against one pod."""
        events = self.get("events", "--field-selector", f"involvedObject.name={pod_name}")["items"]
        return [f"{event['reason']}: {event['message']}" for event in events]

    def logs(self, pod_name: str, *, previous: bool = False) -> str:
        """The container log of a pod, optionally of the previous (crashed) instance."""
        args = ["logs", pod_name] + (["--previous"] if previous else [])
        result = self.run(*args, check=False)
        return result.stdout + result.stderr


def wait_for[T](description: str, probe: Callable[[], T | None], *, timeout: float = 120, interval: float = 2) -> T:
    """Poll until probe returns something other than None or False; fail with the description on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if value is not None and value is not False:
            return value
        time.sleep(interval)
    raise AssertionError(f"timed out after {timeout:.0f}s waiting for: {description}")


def container_status(pod: Json) -> Json | None:
    """The first container's status block, if the kubelet has reported one."""
    statuses = pod.get("status", {}).get("containerStatuses")
    return statuses[0] if statuses else None


def is_ready(pod: Json) -> bool:
    """True when the pod's Ready condition is True."""
    conditions = pod.get("status", {}).get("conditions", [])
    return any(condition["type"] == "Ready" and condition["status"] == "True" for condition in conditions)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def port_forward(kube: Kube, target: str, port: int) -> Iterator[str]:
    """kubectl port-forward target to a free local port; yield the base URL."""
    local = _free_port()
    process = subprocess.Popen(
        ["kubectl", "-n", kube.namespace, "port-forward", target, f"{local}:{port}"],
        env=kube.env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with socket.socket() as probe:
                probe.settimeout(0.5)
                if probe.connect_ex(("127.0.0.1", local)) == 0:
                    break
            time.sleep(0.3)
        yield f"http://127.0.0.1:{local}"
    finally:
        process.terminate()
        process.wait(timeout=10)


def fetch_json(url: str, timeout: float = 5) -> Json:
    """GET a URL and parse the JSON body; raises OSError (URLError) on connection trouble."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        parsed: Json = json.loads(response.read())
        return parsed
