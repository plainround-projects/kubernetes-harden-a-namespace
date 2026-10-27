"""The lesson's Done when lines against the two-node Calico cluster (make up first).

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


def stage(kube: Kube, name: str, control: str = "") -> None:
    """Put both namespaces into a stage once; later tests that need the same stage reuse it."""
    label = f"{name} {control}".strip()
    if STATE["stage"] != label:
        kube.script("stage.sh", *([name, control] if control else [name]), timeout=900)
        STATE["stage"] = label


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


def kubectl_as_engineer(kube: Kube, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", *ENGINEER, *args], env=kube.env, capture_output=True, text=True, check=False, timeout=120
    )


def test_baseline_every_attack_succeeds(kube: Kube) -> None:
    """With no control in place all seven attacks land, so the attacks are real and the controls have work to do."""
    stage(kube, "baseline")
    verdicts = run_attacks(kube)
    assert {name: verdict for name, (verdict, _) in verdicts.items()} == dict.fromkeys(ATTACKS, "SUCCEEDED")


def test_done_when_2_rbac_gives_team_a_nothing_in_team_b_and_pods_have_no_token(kube: Kube) -> None:
    """`auth can-i --list` as team A shows nothing in team B, and a pod cannot read any Secret through the API."""
    stage(kube, "hardened")
    listing = kubectl_as_engineer(kube, "auth", "can-i", "--list", "-n", "team-b").stdout
    print(listing)
    resources = [line.split()[0] for line in listing.splitlines()[1:] if line.strip() and not line.startswith("/")]
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


def test_done_when_4_network_policy_allows_the_own_database_and_blocks_the_other_in_both_directions(kube: Kube) -> None:
    stage(kube, "hardened")
    forward = run_attacks(kube, "03-cross-namespace-db.sh")["03-cross-namespace-db.sh"]
    reverse = run_attacks(kube, "03-cross-namespace-db.sh", env={"ATTACKER_TEAM": "team-b", "VICTIM_TEAM": "team-a"})
    assert forward[0] == "BLOCKED", forward
    assert reverse["03-cross-namespace-db.sh"][0] == "BLOCKED", reverse
    for team in ("team-a", "team-b"):
        ready = Kube(team).run("get", "deployment", "web", "-o", "jsonpath={.status.readyReplicas}").stdout
        assert int(ready or 0) == 2, "readiness goes through the database, so the allowed flow works in " + team


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
