# Threat model: two teams on one cluster

One page. It is the plan the controls were built from, and `tests/policy/test_threat_model.py` checks that it
and the `attacks/` folder still agree.

## Who and what

Two teams, `team-a` and `team-b`, share one cluster. Each has a namespace of the same name, a web service and a
Postgres database. A "tenant" below is a team's developers and its workloads. The platform team owns the
cluster, the namespaces and the controls.

## What each team must be able to do

- Deploy and update its own workloads (Deployments, Pods, Services, ConfigMaps) in its own namespace.
- Reach its own database from its own web service.
- Use the CPU and memory its quota allows.

## What each team must never do

- Read another team's Secrets or ConfigMaps through the Kubernetes API.
- Open a network connection to another team's pods.
- Run a privileged container, or run as root, on a shared node.
- Use more of the cluster than its quota, and so starve the other team.
- Run an image from outside the approved registry, or a container with no memory limit.

## The attacks, and the one control expected to stop each

| Attack (file in `attacks/`) | What the tenant tries | Primary control | Where it stops it |
| --- | --- | --- | --- |
| `01-privileged-pod.yaml`, `01b-root-pod.yaml` | Run a privileged pod, and a pod that runs as root | Pod Security admission (`restricted`) | Admission: the pod is refused and the message names the rule |
| `02-read-other-secret.sh` | Read team B's database Secret as team A's service account | RBAC (Roles in the team's own namespace only, no cluster-wide binding) | The API server answers `Forbidden` |
| `03-cross-namespace-db.sh` | Connect from team A's web pod to team B's database port | NetworkPolicy (default deny in both directions, then only the flows the app needs) | The connection never completes: it is refused at once or times out, depending on whether the policy controller rejects or drops |
| `04-exhaust-memory.yaml` | Ask for fifty replicas of 1 GiB each | ResourceQuota (a cap on the namespace's total requests) | The ReplicaSet stops creating pods at the cap |
| `05-unapproved-image.yaml`, `06-no-limits.yaml` | Run an image from an unapproved registry, and a container with no memory limit | ValidatingAdmissionPolicy in CEL | Admission: the pod is refused with the policy's own message |

Each attack is built to break exactly one rule. A pod for attack 4 is otherwise compliant (restricted settings,
approved image, limits set), so only the quota can hold it back. `make prove-controls` switches each control off
in turn and shows that its attack, and only its attack, then succeeds.

## Not stopped by any of these

A genuine remote-code-execution bug in an approved, correctly configured image. If the tenant's own web
service can be tricked into running an attacker's code, that code runs with the service's legitimate
permissions, inside every bound above: it can still reach the team's own database, use the team's own quota,
and read whatever the service can read. Pod Security, RBAC, network policy, quotas and an admission policy
limit the damage (no root, no other namespace, no cluster API, capped resources); none of them removes the
bug. That needs image scanning, patching, and runtime detection, which are out of scope here.
