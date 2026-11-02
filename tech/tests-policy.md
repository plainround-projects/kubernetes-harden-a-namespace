# Policy tests (manifests as data)

## 1. What it is

A **policy test** checks the Kubernetes manifests against rules ("every container has resource limits", "no Secret is committed") without a cluster. The test renders each Kustomize overlay with `kubectl kustomize` (see `kustomize.md`), reads the resulting YAML into Python dictionaries with PyYAML (`yaml.md`) and uses plain `assert` statements on those dictionaries. A **fixture** with `scope="session"` renders once and shares the result with all tests.

## 2. Why this repository uses it

A rule written only in a README gets broken. Here each property of the hardened setup is a test that fails the moment a manifest drifts: the namespaces enforce `restricted`, the baseline really enforces nothing, every workload would pass its own admission policy, the Role grants no Secrets and no wildcards, default-deny covers both directions, DNS is allowed only to kube-dns on port 53, the quota caps requests but never limits. A second test file checks that the threat model document and the `attacks/` folder agree, so a new attack cannot be added without naming its control.

## 3. Where it appears

| File | Role |
| --- | --- |
| `tests/policy/conftest.py` | Renders overlays; fixtures `hardened` and `baseline`; the `select` helper. |
| `tests/policy/test_manifests.py` | Rules on the rendered manifests. |
| `tests/policy/test_threat_model.py` | Rules on `docs/threat-model.md` against `attacks/`. |
| `Makefile` | `make test` runs them with the unit tests. |

## 4. How it works underneath

`subprocess.run([...], capture_output=True, text=True, check=True)` starts the `kubectl` program, collects its output as text, and raises an error if its exit status is non-zero. `yaml.safe_load_all` parses a stream of documents separated by `---` into a sequence of dictionaries (`safe` means it refuses YAML that could construct arbitrary Python objects). `pathlib.Path` is Python's object for file paths; `.resolve().parents[2]` climbs two folders up from the test file to the repository root.

Kubernetes quantities such as `50m` (50 millicores) and `64Mi` (64 mebibytes, 64 x 1024 x 1024 bytes) are strings, so the test converts them to numbers with a regular expression (`re.fullmatch`) before comparing a request with a limit.

## 5. Walkthrough of this repository's use

### `tests/policy/conftest.py`

```text
"""Render the Kustomize overlays once per session so the policy tests read plain dictionaries."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
Doc = dict[str, Any]
```

The docstring says the overlays are rendered once per session. Imports: `subprocess`, `Path`, `Any`, `pytest`, `yaml` (PyYAML). `ROOT` is the repository folder and `Doc` names "one parsed object".

```text
def render(overlay: str) -> list[Doc]:
    """kubectl kustomize manifests/overlays/<overlay>, parsed into one dictionary per resource."""
    output = subprocess.run(
        [
            "kubectl",
            "kustomize",
            "--load-restrictor=LoadRestrictionsNone",
            str(ROOT / "manifests" / "overlays" / overlay),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [doc for doc in yaml.safe_load_all(output) if doc]
```

`render(overlay)` runs `kubectl kustomize --load-restrictor=LoadRestrictionsNone manifests/overlays/<overlay>` (the flag allows reading the SQL files outside the overlay folder), captures the text and returns the non-empty parsed objects.

```text
def select(docs: list[Doc], kind: str, namespace: str | None = None, name: str | None = None) -> list[Doc]:
    """The resources of a kind, optionally in one namespace and with one name."""
    return [
        doc
        for doc in docs
        if doc["kind"] == kind
        and (namespace is None or doc["metadata"].get("namespace") == namespace)
        and (name is None or doc["metadata"]["name"] == name)
    ]


@pytest.fixture(scope="session")
def hardened() -> list[Doc]:
    return render("hardened")


@pytest.fixture(scope="session")
def baseline() -> list[Doc]:
    return render("baseline")
```

`select(docs, kind, namespace=None, name=None)` returns the objects of one kind, optionally filtered by namespace and name (a list comprehension with `and` conditions). The session fixtures `hardened` and `baseline` render those two overlays once.

### `tests/policy/test_manifests.py`

```text
"""Policy checks on the rendered manifests: what the hardened overlay must contain, and what the baseline lacks."""

from __future__ import annotations

from typing import Any

import pytest

from tests.policy.conftest import Doc, select

pytestmark = pytest.mark.policy

TEAMS = ("team-a", "team-b")
APPROVED = "registry.example.test/platform/"


def _pods(docs: list[Doc], namespace: str) -> list[dict[str, Any]]:
    return [doc["spec"]["template"]["spec"] for doc in select(docs, "Deployment", namespace)]
```

The docstring states the purpose. `TEAMS` lists both teams, `APPROVED` is the approved registry prefix, and `_pods(docs, namespace)` returns the pod specs of the Deployments in a namespace. `pytestmark` labels the file `policy`.

```text
@pytest.mark.parametrize("team", TEAMS)
def test_each_namespace_enforces_the_restricted_standard_in_the_hardened_overlay(hardened, team):
    (namespace,) = select(hardened, "Namespace", name=team)
    labels = namespace["metadata"]["labels"]
    assert labels["pod-security.kubernetes.io/enforce"] == "restricted"
    assert labels["platform.example/tenant"] == "true", "the admission policy binds by this label"


@pytest.mark.parametrize("team", TEAMS)
def test_the_baseline_enforces_nothing(baseline, team):
    (namespace,) = select(baseline, "Namespace", name=team)
    assert not [key for key in namespace["metadata"]["labels"] if key.startswith("pod-security")]
    for kind in ("NetworkPolicy", "ResourceQuota", "LimitRange", "Role", "RoleBinding"):
        assert select(baseline, kind, team) == [], kind
    assert not select(baseline, "ValidatingAdmissionPolicy")
```

For each team (`parametrize`): the hardened namespace carries `pod-security.kubernetes.io/enforce: restricted` and the tenant label the admission policy binds by (`(namespace,) = ...` unpacks a list that must have exactly one element). In the baseline, no label starts with `pod-security`, no NetworkPolicy, ResourceQuota, LimitRange, Role or RoleBinding exists in the team's namespace, and no admission policy exists.

```text
@pytest.mark.parametrize("team", TEAMS)
def test_every_workload_would_pass_its_own_admission_policy_and_pod_security(hardened, team):
    for pod in _pods(hardened, team):
        assert pod["securityContext"]["runAsNonRoot"] is True
        assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
        assert pod["automountServiceAccountToken"] is False
        assert pod["enableServiceLinks"] is False, "a Service called db would otherwise set DB_PORT to a URL"
        for container in pod["containers"]:
            assert container["image"].startswith(APPROVED), container["image"]
            assert "memory" in container["resources"]["limits"]
            assert container["resources"]["requests"]
            context = container["securityContext"]
            assert context["allowPrivilegeEscalation"] is False
            assert context["capabilities"]["drop"] == ["ALL"]
            assert not context.get("privileged")


@pytest.mark.parametrize("team", TEAMS)
def test_service_accounts_have_no_mounted_token(hardened, team):
    accounts = select(hardened, "ServiceAccount", team)
    assert sorted(account["metadata"]["name"] for account in accounts) == ["db", "web"]
    assert all(account["automountServiceAccountToken"] is False for account in accounts)
```

Every workload in the hardened overlay would pass both its own Pod Security level and the admission policy: non-root, default seccomp, no token, service links off, an approved image, a memory limit, some request, no privilege escalation, all capabilities dropped, not privileged. Each team has exactly two ServiceAccounts, `db` and `web`, and neither mounts a token.

```text
@pytest.mark.parametrize("team", TEAMS)
def test_the_role_is_namespaced_and_grants_no_secrets_no_wildcards_and_no_rbac(hardened, team):
    (role,) = select(hardened, "Role", team, "developer")
    for rule in role["rules"]:
        assert "secrets" not in rule["resources"]
        assert "*" not in rule["resources"] + rule["verbs"] + rule["apiGroups"]
        assert "roles" not in rule["resources"]
        assert "pods/exec" not in rule["resources"]


@pytest.mark.parametrize("team", TEAMS)
def test_the_binding_is_a_rolebinding_for_this_teams_group_only(hardened, team):
    (binding,) = select(hardened, "RoleBinding", team, "developers")
    assert binding["subjects"] == [{"apiGroup": "rbac.authorization.k8s.io", "kind": "Group", "name": f"{team}-humans"}]
    assert binding["roleRef"]["kind"] == "Role"
```

The `developer` Role: no rule mentions Secrets, no wildcard `*` in resources, verbs or API groups, no `roles` and no `pods/exec`. The RoleBinding `developers` has exactly one subject, the Group `<team>-humans`, and refers to a Role (not a ClusterRole).

```text
def test_the_hardened_overlay_has_no_clusterrolebinding_and_the_baseline_has_the_careless_one(hardened, baseline):
    assert select(hardened, "ClusterRoleBinding") == []
    careless = select(baseline, "ClusterRoleBinding")
    assert sorted(binding["metadata"]["name"] for binding in careless) == ["team-a-convenience", "team-b-convenience"]
    assert all(binding["roleRef"]["name"] == "edit" for binding in careless)
    for team in TEAMS:
        (binding,) = select(baseline, "ClusterRoleBinding", name=f"{team}-convenience")
        assert {"kind": "ServiceAccount", "name": "web", "namespace": team} in binding["subjects"]


@pytest.mark.parametrize("team", TEAMS)
def test_default_deny_covers_both_directions_and_every_pod(hardened, team):
    (policy,) = select(hardened, "NetworkPolicy", team, "default-deny")
    assert policy["spec"]["podSelector"] == {}
    assert sorted(policy["spec"]["policyTypes"]) == ["Egress", "Ingress"]
```

The hardened overlay has no ClusterRoleBinding; the baseline has exactly the two careless ones (`team-a-convenience`, `team-b-convenience`), both bound to `edit`, each naming that team's `web` ServiceAccount. The default-deny policy selects all pods and lists both Ingress and Egress.

```text
@pytest.mark.parametrize("team", TEAMS)
def test_dns_is_allowed_to_kube_dns_only_on_port_53(hardened, team):
    (policy,) = select(hardened, "NetworkPolicy", team, "allow-dns")
    (rule,) = policy["spec"]["egress"]
    assert {(port["protocol"], port["port"]) for port in rule["ports"]} == {("UDP", 53), ("TCP", 53)}
    assert rule["to"][0]["podSelector"]["matchLabels"] == {"k8s-app": "kube-dns"}


@pytest.mark.parametrize("team", TEAMS)
def test_the_only_application_flow_is_web_to_its_own_db_on_5432_in_this_namespace(hardened, team):
    names = {policy["metadata"]["name"] for policy in select(hardened, "NetworkPolicy", team)}
    assert names == {"default-deny", "allow-dns", "web-egress-to-db", "db-ingress-from-web"}
    for name in ("web-egress-to-db", "db-ingress-from-web"):
        (policy,) = select(hardened, "NetworkPolicy", team, name)
        rule = (policy["spec"].get("egress") or policy["spec"]["ingress"])[0]
        peer = (rule.get("to") or rule["from"])[0]
        assert "namespaceSelector" not in peer, "no namespaceSelector: the peer is in this namespace only"
        assert rule["ports"] == [{"protocol": "TCP", "port": 5432}]
```

The DNS policy allows only UDP and TCP 53 to pods labelled `k8s-app: kube-dns`. Each team has exactly four NetworkPolicies, and the two application ones have no `namespaceSelector` (the peer is in this namespace only) and allow only TCP 5432.

```text
@pytest.mark.parametrize("team", TEAMS)
def test_quota_caps_requests_and_the_limit_range_defaults_requests_but_never_limits(hardened, team):
    (quota,) = select(hardened, "ResourceQuota", team)
    assert {"requests.cpu", "requests.memory", "pods"} <= quota["spec"]["hard"].keys()
    assert not [key for key in quota["spec"]["hard"] if key.startswith("limits.")], (
        "a quota on limits would refuse a pod with no limits before the admission policy could"
    )
    (limit_range,) = select(hardened, "LimitRange", team)
    (item,) = limit_range["spec"]["limits"]
    assert "defaultRequest" in item
    assert "default" not in item, "a default limit would make the admission policy's limits rule unreachable"


def test_the_admission_policy_fails_closed_denies_and_binds_to_the_tenant_label(hardened):
    (policy,) = select(hardened, "ValidatingAdmissionPolicy")
    (binding,) = select(hardened, "ValidatingAdmissionPolicyBinding")
    assert policy["spec"]["failurePolicy"] == "Fail"
    assert binding["spec"]["validationActions"] == ["Deny"]
    assert binding["spec"]["matchResources"]["namespaceSelector"]["matchLabels"] == {"platform.example/tenant": "true"}
    messages = " ".join(validation["messageExpression"] for validation in policy["spec"]["validations"])
    assert "image must come from" in messages
    assert "memory limit" in messages
```

The quota has `requests.cpu`, `requests.memory` and `pods`, and no key starting `limits.` (the message explains why). The LimitRange has `defaultRequest` and no `default` (limit) for the same reason. The admission policy has `failurePolicy: Fail`, the binding denies, selects by the tenant label, and the two messages mention the registry and the memory limit.

```text
def test_the_two_teams_differ_only_in_their_names(hardened):
    def normalized(team: str) -> list[str]:
        import json

        docs = [
            doc for doc in hardened if doc["metadata"].get("namespace") == team or doc["metadata"].get("name") == team
        ]
        return sorted(json.dumps(doc, sort_keys=True).replace(team, "TEAM") for doc in docs)

    assert normalized("team-a") == normalized("team-b")
```

The last test normalises each team's objects (select the objects of that namespace or the namespace itself, dump to sorted JSON text, replace the team name with `TEAM`) and requires that both teams are identical: they differ only in their names.

### `tests/policy/test_threat_model.py`

```text
"""The threat model and the attacks folder agree: every attack has exactly one primary control, and the gap is named."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.policy

ROOT = Path(__file__).resolve().parents[2]
MODEL = (ROOT / "docs" / "threat-model.md").read_text()
ATTACK_FILES = sorted(path.name for path in (ROOT / "attacks").iterdir() if re.match(r"0\d", path.name))
CONTROLS = ("Pod Security", "RBAC", "NetworkPolicy", "ResourceQuota", "ValidatingAdmissionPolicy")
```

The docstring says the threat model and the attacks folder agree. The model text is read from `docs/threat-model.md`; `ATTACK_FILES` lists the files in `attacks/` whose names start with `0` and a digit (a regular expression); `CONTROLS` names the five controls.

```text
def _table_rows() -> list[tuple[str, str]]:
    rows = []
    for line in MODEL.splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if line.startswith("| `") and len(cells) >= 3:
            rows.append((cells[0], cells[2]))
    return rows


def test_every_attack_file_appears_in_exactly_one_row():
    rows = _table_rows()
    for name in ATTACK_FILES:
        assert sum(name in attacks for attacks, _ in rows) == 1, name


def test_every_row_names_exactly_one_primary_control():
    for attacks, control in _table_rows():
        assert sum(known in control for known in CONTROLS) == 1, (attacks, control)
```

`_table_rows()` reads the model line by line and for each table row starting with a backtick returns the first cell (the attack files) and the third (the control). `test_every_attack_file_appears_in_exactly_one_row` and `test_every_row_names_exactly_one_primary_control` check the one-to-one mapping.

```text
def test_every_attack_in_the_table_exists_as_a_file():
    for attacks, _ in _table_rows():
        for name in re.findall(r"`([^`]+)`", attacks):
            assert (ROOT / "attacks" / name).exists(), name


def test_the_model_lists_what_teams_must_do_and_must_never_do_and_names_the_gap():
    for heading in (
        "## What each team must be able to do",
        "## What each team must never do",
        "## Not stopped by any of these",
    ):
        assert heading in MODEL
    assert "remote-code-execution" in MODEL
```

Every attack named in the table exists as a file; the model has the three headings the lesson requires (what each team must be able to do, must never do, and what is not stopped by any of these), and names the gap that remains (remote-code-execution in the application).


## 6. Try it yourself

```bash
.venv/bin/python -m pytest tests/policy -q
```

Passes with no cluster: each test name is a sentence describing a rule.

```bash
sed -i.bak 's/automountServiceAccountToken: false/automountServiceAccountToken: true/' manifests/controls/rbac/kustomization.yaml && .venv/bin/python -m pytest tests/policy -q -k token; mv manifests/controls/rbac/kustomization.yaml.bak manifests/controls/rbac/kustomization.yaml
```

The service-account test fails, and the last command restores the file.

```bash
kubectl kustomize --load-restrictor=LoadRestrictionsNone manifests/overlays/hardened | grep -c "^kind:"
```

Counts the objects of the hardened overlay (both teams plus the admission policy).

## 7. Mistakes people make

- **Testing the source instead of the rendered output.** Kustomize can add, rename or hash things; the rendered YAML is what the cluster gets.
- **Using unsafe YAML loading.** `yaml.load` can build arbitrary objects from a file; use `safe_load`.
- **Comparing `"64Mi"` and `"128Mi"` as text.** `"128Mi" < "64Mi"` as strings; the test converts to numbers.
- **A rule with no failing example.** Each rule here has been checked to fail when its manifest line is removed.

## 8. Check yourself

1. Why is `--load-restrictor=LoadRestrictionsNone` passed? *The database init scripts live in `sql/`, outside the kustomization folder.*
2. What does `select(docs, "Role", team, "developer")` return? *The list of Roles named `developer` in that namespace.*
3. Why must the quota never cap `limits.*`? *A pod without limits would be refused by the quota before the admission policy could give its clearer message.*
4. What does `test_the_two_teams_differ_only_in_their_names` prove? *After replacing the team name, both teams' objects are identical.*
5. What does the threat-model test guarantee? *Every attack file has exactly one row, each row names exactly one primary control, and the gap is stated.*

## 9. Further reading

- PyYAML: https://pyyaml.org/wiki/PyYAMLDocumentation
- Python `subprocess`: https://docs.python.org/3.13/library/subprocess.html
- Python `re`: https://docs.python.org/3.13/library/re.html
- Kubernetes resource quantities: https://kubernetes.io/docs/reference/kubernetes-api/common-definitions/quantity/
- `pathlib`: https://docs.python.org/3.13/library/pathlib.html
