# End-to-end tests (every Done-when line on the cluster)

## 1. What it is

An **end-to-end (e2e) test** exercises the whole system the way a user would. Here that means: against the real k3s cluster from `make up`, put both team namespaces into a stage with `scripts/stage.sh`, run the attacks with `scripts/run-attacks.sh` as a developer of team A, and read the verdicts. The tests are marked `e2e` and run with `make smoke`. They take about fifteen minutes and are the proof behind the README's table.

## 2. Why this repository uses it

The claims are about a live cluster: "with no control every attack succeeds", "with every control every attack is blocked", "with one control off exactly its own attack succeeds". Only a real cluster can show these. The test names say which Done-when line each one proves, and the "baseline" and "one control off" tests are the other half of the proof: an attack that is blocked proves nothing unless it is shown to succeed when its control is absent.

## 3. Where it appears

| File | Role |
| --- | --- |
| `tests/e2e/kube.py` | A small wrapper that runs `kubectl` and the project's scripts, with retries (shared in shape with the sibling project; some helpers are not used here). |
| `tests/e2e/test_done_when.py` | The baseline test, one test per Done-when line, the one-control-off matrix and the final restore. |
| `Makefile` | `make smoke`; the CI job `cluster`. |

## 4. How it works underneath

The tests call the same scripts a learner would, so the scripts are tested too. The module keeps a small piece of state (`STATE["stage"]`) naming the stage the cluster is in, so a test that needs `hardened` does not reapply it if the previous test already did; a stage change costs a minute or two while the pods roll.

A busy laptop sometimes makes the Kubernetes API server slow to answer; `kubectl` then prints messages such as `TLS handshake timeout`. The wrapper recognises these **transient** errors and retries instead of failing the test, while a real error is returned at once.

Python features used: **context managers** (`with ...:` runs set-up and clean-up code), **`try`/`finally`** (the matrix restores the hardened stage even when an assertion fails), **regular expressions** (`re.match` to read verdict lines), **`dict.fromkeys(keys, value)`** (a dictionary with the same value for every key) and **generics** (`def wait_for[T](...)`).

## 5. Walkthrough of this repository's use

### `tests/e2e/kube.py`

```text
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
```

The docstring describes the module. The imports cover JSON, the environment, sockets, processes, time, URL fetching, callable types, `contextmanager`, paths and `Any`.

```text
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
```

`ROOT` is the repository folder. `Json` names a parsed JSON object. `ATTEMPTS = 120` and `RETRY_SECONDS = 8` mean a `kubectl` call that hits a transient error is retried up to 120 times, 8 seconds apart (about sixteen minutes at the limit); `SCRIPT_ATTEMPTS = 60` bounds script retries. `TRANSIENT` lists the error texts that mean "the API server did not answer": cannot connect, TLS handshake timeout, I/O timeout, connection refused, deadline exceeded, no response, an etcd (the cluster's key-value store) timeout, a cancelled HTTP request. `_transient(stderr)` is true when any of them appears in the error output.

```text
class Kube:
    """kubectl against the project's own kubeconfig (never ~/.kube/config), scoped to one namespace."""

    def __init__(self, namespace: str = "counter") -> None:
        self.namespace = namespace
        self.env = {**os.environ, "KUBECONFIG": os.environ.get("KUBECONFIG", str(ROOT / ".kube" / "config"))}

    def run(self, *args: str, check: bool = True, timeout: float = 120) -> subprocess.CompletedProcess[str]:
        """Run kubectl in the namespace and return the finished process.
```

`class Kube` runs `kubectl` against the project's own kubeconfig (never `~/.kube/config`) in one namespace. `__init__` copies the environment and sets `KUBECONFIG`. `run(...)` begins with a docstring that continues in the next chunk; it takes the arguments, whether to raise on failure (`check`) and a per-call timeout in seconds.

```text
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
```

The docstring finishes (transient failures are retried, other failures are raised at once). The loop calls `kubectl -n <namespace> <args>` with `subprocess.run`, capturing text. A `TimeoutExpired` is retried until the last attempt, then raised. If the command succeeded, or the error is not transient, or it was the last attempt, the result is returned (after `check_returncode()` raises if `check` is true); otherwise it sleeps `RETRY_SECONDS`. The final `raise AssertionError("unreachable")` is for the type checker: the loop always returns or raises first.

```text
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
```

`script(name, *args)` runs one of the project's scripts. It retries when the output says the cluster is unreachable or transient, sleeping 30 seconds, for up to 60 attempts; a success returns standard output; any other failure raises an `AssertionError` that includes both outputs so a test report shows why.

```text
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
```

Small helpers: `get` runs `kubectl get ... -o json` and parses it; `pods` returns the pod list for a label selector (default `app=web`); `events` returns `Reason: message` strings for the events about one pod, using a field selector (`involvedObject.name=<pod>`); `logs` returns a pod's log text (plus standard error), optionally of the `--previous` container instance that crashed.

```text
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
```

`wait_for[T](description, probe, timeout, interval)` calls `probe` every `interval` seconds until it returns something other than `None` or `False`, then returns that value; on timeout it raises an error that says what was awaited. `container_status(pod)` returns the first container's status block if the kubelet has reported one. `is_ready(pod)` is true when the pod's `Ready` condition has status `"True"`.

```text
def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
```

`_free_port()` is the same helper as in the integration tests: bind port 0, read the assigned port.

```text
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
```

`port_forward(kube, target, port)` is a context manager. It starts `kubectl port-forward <target> <local>:<port>` in the background with output discarded, then for up to 20 seconds tries to connect to the local port (`connect_ex` returns 0 when it works) until the tunnel is up, yields the base URL, and in `finally` stops the process.

```text
def fetch_json(url: str, timeout: float = 5) -> Json:
    """GET a URL and parse the JSON body; raises OSError (URLError) on connection trouble."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        parsed: Json = json.loads(response.read())
        return parsed
```

`fetch_json(url, timeout)` does an HTTP GET with `urllib` and parses the JSON body; connection trouble raises `OSError` (its subclass `URLError`), which the sixth-failure test relies on.

### `tests/e2e/test_done_when.py`

```text
"""The lesson's Done when lines against the one-node k3s cluster (make up first).

The cluster is put into a stage with scripts/stage.sh and the attacks are run with scripts/run-attacks.sh,
exactly as a reader would. Besides "every attack is blocked when every control is on", the tests show the other
half of the proof: with no control every attack succeeds, and with one control off exactly its own attack does.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from tests.e2e.kube import ROOT, Kube

pytestmark = pytest.mark.e2e
```

The docstring explains the design: the cluster is put into a stage with `stage.sh` and attacks run with `run-attacks.sh`, as a reader would, and the tests show both halves of the proof (no control: every attack succeeds; one control off: exactly its own attack does). Imports: `re`, `subprocess`, `pytest`, `ROOT` and `Kube` from the helper. `pytestmark = pytest.mark.e2e`.

```text
ATTACKS = {
    "01-privileged-pod.yaml": "pod-security",
    "01b-root-pod.yaml": "pod-security",
    "02-read-other-secret.sh": "rbac",
    "03-cross-namespace-db.sh": "network-policy",
    "04-exhaust-memory.yaml": "quota",
    "05-unapproved-image.yaml": "admission-policy",
    "06-no-limits.yaml": "admission-policy",
}
ENGINEER = ["--as=alice", "--as-group=team-a-humans", "-n", "team-a"]
STATE = {"stage": ""}


@pytest.fixture(scope="module")
def kube() -> Kube:
    cluster = Kube("team-a")
    if cluster.run("get", "nodes", check=False).returncode != 0:
        pytest.fail("no cluster reachable: run `make up` first")
    return cluster
```

`ATTACKS` maps each attack file to the control that owns it. `ENGINEER` is the list of `kubectl` options that impersonate Alice of team A in team A's namespace. `STATE` remembers the current stage. The module-scoped `kube` fixture creates a `Kube("team-a")` and fails with a clear message when no cluster answers.

```text
def stage(kube: Kube, name: str, control: str = "") -> None:
    """Put both namespaces into a stage once; later tests that need the same stage reuse it."""
    label = f"{name} {control}".strip()
    if STATE["stage"] != label:
        kube.script("stage.sh", *([name, control] if control else [name]), timeout=900)
        STATE["stage"] = label
```

`stage(kube, name, control="")` puts both namespaces in the named stage unless the cluster is already in it: it builds a label such as `without quota`, compares with `STATE`, and otherwise runs `stage.sh` through the helper (up to 900 seconds).

```text
def run_attacks(kube: Kube, *files: str, env: dict[str, str] | None = None) -> dict[str, tuple[str, str]]:
    """Run attacks/ (all, or the named files); return {file: (BLOCKED|SUCCEEDED|INCONCLUSIVE, the verdict line)}."""
    result = subprocess.run(
        [str(ROOT / "scripts" / "run-attacks.sh"), *[str(ROOT / "attacks" / name) for name in files]],
        env={**kube.env, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    print(result.stdout)
    verdicts: dict[str, tuple[str, str]] = {}
    current = ""
    for line in result.stdout.splitlines():
        header = re.match(r"== attacks/(\S+) ==", line)
        if header:
            current = header.group(1)
            continue
        verdict = re.match(r"(BLOCKED|SUCCEEDED|INCONCLUSIVE)\b(.*)", line)
        if verdict and current:
            verdicts[current] = (verdict.group(1), line)
    return verdicts
```

`run_attacks(kube, *files, env=None)` runs `scripts/run-attacks.sh` (all attacks or the named files), prints its output and parses it: a header line `== attacks/<name> ==` sets the current attack and a line starting `BLOCKED`, `SUCCEEDED` or `INCONCLUSIVE` is stored as its verdict. It returns a dictionary from file name to (verdict, line).

```text
def kubectl_as_engineer(kube: Kube, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", *ENGINEER, *args], env=kube.env, capture_output=True, text=True, check=False, timeout=120
    )


def test_baseline_every_attack_succeeds(kube: Kube) -> None:
    """With no control in place all seven attacks land, so the attacks are real and the controls have work to do."""
    stage(kube, "baseline")
    verdicts = run_attacks(kube)
    assert {name: verdict for name, (verdict, _) in verdicts.items()} == dict.fromkeys(ATTACKS, "SUCCEEDED")
```

`kubectl_as_engineer` runs `kubectl` as Alice. `test_baseline_every_attack_succeeds` puts the cluster in the baseline, runs all attacks and requires exactly `SUCCEEDED` for every key of `ATTACKS`.

```text
def test_done_when_2_rbac_gives_team_a_nothing_in_team_b_and_pods_have_no_token(kube: Kube) -> None:
    """`auth can-i --list` as team A shows nothing in team B, and a pod cannot read any Secret through the API."""
    stage(kube, "hardened")
    listing = kubectl_as_engineer(kube, "auth", "can-i", "--list", "-n", "team-b").stdout
    print(listing)
    resources = [
        line.split()[0] for line in listing.splitlines()[1:] if line.strip() and not line.split()[0].startswith("[")
    ]
    assert all(name.startswith("selfsubject") for name in resources), (
        f"team A can do more in team B than ask who it is: {resources}"
    )
    assert kubectl_as_engineer(kube, "auth", "can-i", "get", "secrets", "-n", "team-b").stdout.strip() == "no"
    assert kubectl_as_engineer(kube, "auth", "can-i", "get", "secrets", "-n", "team-a").stdout.strip() == "no"
    assert kubectl_as_engineer(kube, "auth", "can-i", "create", "deployments", "-n", "team-a").stdout.strip() == "yes"
    as_service_account = ["--as=system:serviceaccount:team-a:web"]
    cannot = kube.run(*as_service_account, "auth", "can-i", "get", "secrets", "-n", "team-b", check=False)
    assert cannot.stdout.strip() == "no"
    mount = kube.run("exec", "deploy/web", "--", "ls", "/var/run/secrets/kubernetes.io/serviceaccount", check=False)
    assert mount.returncode != 0, "no token is mounted, so the pod has nothing to call the API with"
    assert run_attacks(kube, "02-read-other-secret.sh")["02-read-other-secret.sh"][0] == "BLOCKED"
```

`test_done_when_2_...`: in the hardened stage, `kubectl auth can-i --list -n team-b` as Alice must list nothing but the `selfsubject...` entries (the right to ask who you are); `can-i get secrets` is `no` in team B and in team A; `can-i create deployments` in team A is `yes`; as the `web` service account, `get secrets` in team B is `no`; and `ls` of the token folder inside the web pod fails (no token is mounted). Attack 2 must be `BLOCKED`.

```text
def test_done_when_3_pod_security_refuses_a_privileged_and_a_root_pod_and_names_the_rule(kube: Kube) -> None:
    stage(kube, "hardened")
    privileged = kubectl_as_engineer(kube, "apply", "-f", str(ROOT / "attacks" / "01-privileged-pod.yaml"))
    root = kubectl_as_engineer(kube, "apply", "-f", str(ROOT / "attacks" / "01b-root-pod.yaml"))
    print(privileged.stderr, root.stderr)
    assert privileged.returncode != 0
    assert 'violates PodSecurity "restricted:latest"' in privileged.stderr
    assert "privileged" in privileged.stderr
    assert root.returncode != 0
    assert 'violates PodSecurity "restricted:latest"' in root.stderr
    assert "runAsUser=0" in root.stderr or "runAsNonRoot" in root.stderr
    assert kube.run("get", "pods", "-l", "attack", "-o", "name").stdout.strip() == "", "no attack pod was created"
```

`test_done_when_3_...`: applying the privileged and root pods as Alice fails with `violates PodSecurity "restricted:latest"`, the first mentioning `privileged` and the second `runAsUser=0` or `runAsNonRoot`; no pod labelled `attack` exists afterwards.

```text
def test_done_when_4_network_policy_allows_the_own_database_and_blocks_the_other_in_both_directions(kube: Kube) -> None:
    stage(kube, "hardened")
    forward = run_attacks(kube, "03-cross-namespace-db.sh")["03-cross-namespace-db.sh"]
    reverse = run_attacks(kube, "03-cross-namespace-db.sh", env={"ATTACKER_TEAM": "team-b", "VICTIM_TEAM": "team-a"})
    assert forward[0] == "BLOCKED", forward
    assert reverse["03-cross-namespace-db.sh"][0] == "BLOCKED", reverse
    for team in ("team-a", "team-b"):
        ready = Kube(team).run("get", "deployment", "web", "-o", "jsonpath={.status.readyReplicas}").stdout
        assert int(ready or 0) == 2, "readiness goes through the database, so the allowed flow works in " + team
```

`test_done_when_4_...`: attack 3 is `BLOCKED` from A to B and, with the environment variables swapped, from B to A; and both teams' `web` Deployments have two ready replicas (readiness queries the database, so this proves the allowed flow works).

```text
def test_done_when_5_quota_holds_fifty_replicas_and_a_pod_with_no_requests_gets_the_defaults(kube: Kube) -> None:
    stage(kube, "hardened")
    verdict = run_attacks(kube, "04-exhaust-memory.yaml")["04-exhaust-memory.yaml"]
    assert verdict[0] == "BLOCKED", verdict
    assert re.search(r"held at (\d+)/50", verdict[1]), verdict
    defaults = kubectl_as_engineer(
        kube, "run", "defaults-demo", "--image=registry.example.test/platform/pause:3.10", "--restart=Never",
        "--overrides=" + (
            '{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":65534,"seccompProfile":{"type":"RuntimeDefault"}},'
            '"containers":[{"name":"defaults-demo","image":"registry.example.test/platform/pause:3.10",'
            '"securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}},'
            '"resources":{"limits":{"memory":"32Mi"}}}]}}'
        ),
    )  # fmt: skip
    assert defaults.returncode == 0, defaults.stderr
    try:
        requests = kube.run(
            "get", "pod", "defaults-demo", "-o", "jsonpath={.spec.containers[0].resources.requests}"
        ).stdout
        print("requests of a pod that named only a memory limit:", requests)
        assert '"cpu":"50m"' in requests, "the LimitRange default request fills the missing cpu request"
    finally:
        kube.run("delete", "pod", "defaults-demo", "--ignore-not-found", "--wait=false", check=False)
```

`test_done_when_5_...`: attack 4 is `BLOCKED` with a message `held at N/50`. Then a pod that names only a memory limit is created as Alice (a JSON `--overrides` makes a compliant pod) and its resulting requests must contain `"cpu":"50m"`, the LimitRange default; the `finally` block deletes the demo pod.

```text
def test_done_when_6_admission_policy_refuses_both_bad_manifests_with_its_own_messages(kube: Kube) -> None:
    stage(kube, "hardened")
    image = kubectl_as_engineer(kube, "apply", "-f", str(ROOT / "attacks" / "05-unapproved-image.yaml"))
    limits = kubectl_as_engineer(kube, "apply", "-f", str(ROOT / "attacks" / "06-no-limits.yaml"))
    print(image.stderr, limits.stderr)
    assert (
        "image must come from registry.example.test/platform/, got: untrusted.example.test/tools/shell:1.0"
        in image.stderr
    )
    assert "every container must set a memory limit, missing on: unbounded" in limits.stderr
    verdicts = run_attacks(kube)
    assert {name: verdict for name, (verdict, _) in verdicts.items()} == dict.fromkeys(ATTACKS, "BLOCKED"), verdicts
```

`test_done_when_6_...`: applying attacks 5 and 6 fails with the admission policy's own messages (the unapproved image named, the container `unbounded` named); then all attacks together are `BLOCKED`.

```text
@pytest.mark.parametrize("control", ["pod-security", "rbac", "network-policy", "quota", "admission-policy"])
def test_each_control_is_the_one_that_stops_its_attack(kube: Kube, control: str) -> None:
    """With one control off, its attacks succeed and every other attack is still blocked."""
    try:
        stage(kube, "without", control)
        verdicts = run_attacks(kube)
        outcome = {name: verdict for name, (verdict, _) in verdicts.items()}
        expected = {name: ("SUCCEEDED" if owner == control else "BLOCKED") for name, owner in ATTACKS.items()}
        assert outcome == expected, verdicts
    finally:
        stage(kube, "hardened")


def test_the_cluster_is_left_hardened(kube: Kube) -> None:
    stage(kube, "hardened")
    verdicts = run_attacks(kube)
    assert {name: verdict for name, (verdict, _) in verdicts.items()} == dict.fromkeys(ATTACKS, "BLOCKED")
```

The matrix test is parametrized over the five controls: switch one off, run all attacks and require that the attacks owned by that control `SUCCEEDED` and every other one `BLOCKED`; `finally` restores the hardened stage. The last test leaves the cluster hardened and confirms all attacks are blocked.


## 6. Try it yourself

```bash
make up && make smoke
```

Runs the tests with `-v`; each prints `PASSED`. The matrix test appears five times, once per control. Finish with `make down`.

```bash
.venv/bin/python -m pytest tests/e2e -m e2e -s -v -k done_when_4
```

Runs only the NetworkPolicy test (needs the cluster).

```bash
make baseline && make run; make harden && make run
```

The same two stages by hand: every attack `SUCCEEDED`, then every attack `BLOCKED`.

## 7. Mistakes people make

- **Sleeping a fixed time.** The scripts wait for the rollouts themselves.
- **Leaving the cluster in a weakened stage after a failed test.** The matrix uses `try`/`finally` and the last test restores `hardened`.
- **Treating every `kubectl` error as a test failure.** The wrapper retries only the transient ones.
- **Checking only the verdict word.** Tests also check the refusal text (`violates PodSecurity "restricted:latest"`, the policy's own messages) and that no attack pod was created.
- **Proving a negative without a positive.** The NetworkPolicy test also requires both web Deployments to be ready, which they only are when the allowed flow works.

## 8. Check yourself

1. Why is there a baseline test? *To show the attacks are real: with no controls all seven succeed.*
2. What does the one-control-off matrix prove? *That each control is the one that stops its attack, and that no other control does.*
3. How is the engineer's lack of access shown in test 2? *`auth can-i --list` in team B shows nothing beyond asking who you are, and `get secrets` is `no` even in team A.*
4. Why does test 4 run the attack in both directions? *Isolation must hold from team A to B and from B to A.*
5. What does the last test do? *Puts the cluster back in the hardened stage and checks all attacks are blocked.*

## 9. Further reading

- Kubernetes pod lifecycle and container states: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Restart back-off: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#restart-policy
- EndpointSlices: https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/
- Python `contextlib`: https://docs.python.org/3.13/library/contextlib.html
- Python `itertools.pairwise`: https://docs.python.org/3.13/library/itertools.html#itertools.pairwise
