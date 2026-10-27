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


@pytest.mark.parametrize("team", TEAMS)
def test_every_workload_would_pass_its_own_admission_policy_and_pod_security(hardened, team):
    for pod in _pods(hardened, team):
        assert pod["securityContext"]["runAsNonRoot"] is True
        assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
        assert pod["automountServiceAccountToken"] is False
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


def test_the_hardened_overlay_has_no_clusterrolebinding_and_the_baseline_has_the_careless_one(hardened, baseline):
    assert select(hardened, "ClusterRoleBinding") == []
    careless = select(baseline, "ClusterRoleBinding")
    assert sorted(binding["metadata"]["name"] for binding in careless) == ["team-a-convenience", "team-b-convenience"]
    assert all(binding["roleRef"]["name"] == "edit" for binding in careless)


@pytest.mark.parametrize("team", TEAMS)
def test_default_deny_covers_both_directions_and_every_pod(hardened, team):
    (policy,) = select(hardened, "NetworkPolicy", team, "default-deny")
    assert policy["spec"]["podSelector"] == {}
    assert sorted(policy["spec"]["policyTypes"]) == ["Egress", "Ingress"]


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


def test_the_two_teams_differ_only_in_their_names(hardened):
    def normalized(team: str) -> list[str]:
        import json

        docs = [
            doc for doc in hardened if doc["metadata"].get("namespace") == team or doc["metadata"].get("name") == team
        ]
        return sorted(json.dumps(doc, sort_keys=True).replace(team, "TEAM") for doc in docs)

    assert normalized("team-a") == normalized("team-b")
