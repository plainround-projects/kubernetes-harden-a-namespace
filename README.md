# kubernetes-harden-a-namespace

Two team namespaces on a local k3d cluster whose network layer enforces NetworkPolicy, each running a small web service and a Postgres database, hardened one control at a time and attacked as a careless or malicious tenant would: a privileged pod, the other team's Secret, the other team's database, memory exhaustion and an image from an unapproved registry. Every attack is a file you can rerun, and every one now fails.

| | |
| --- | --- |
| **Lesson** | `/prep/kubernetes/project-harden-a-namespace`, "Harden a shared namespace and attack it" (`data-structure-explainer/src/content/tracks/kubernetes/14-project-harden-a-namespace.md` in the Plainround app) |
| **Planned hours** | 12 |
| **Level** | Advanced |
| **Architecture** | [ARCHITECTURE.md](ARCHITECTURE.md), the one-page [threat model](docs/threat-model.md), decisions in [docs/adr](docs/adr) |

## Architecture

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/architecture-dark.svg">
  <img alt="A Team A engineer acting as alice calls the API server, where RBAC, Pod Security, ResourceQuota with LimitRange and a CEL policy decide what is admitted, the policy refuses an unapproved registry, the web pod in team-a reaches only its own database, and NetworkPolicy and RBAC stop it reaching the Team B database and Secret." src="docs/diagrams/architecture.svg">
</picture>

The web pod is the foothold for the attacks, and each amber path is one that a control refuses; the notes give the memory attack result and the three runs.

## How one run flows

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/flow-dark.svg">
  <img alt="One attack, memory exhaustion: alice applies a Deployment of fifty pods, the controllers create pods, each pod adds its requests to the quota, and in the amber rows the quota refuses the pod that would pass 4 GiB and the ReplicaSet records FailedCreate." src="docs/diagrams/flow.svg">
</picture>

The runner ends by counting fewer than fifty pods and reading the quota event, which is the verdict BLOCKED.

## Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| Docker | 24 or newer (tested with Docker Desktop 24.0.6 on an Apple-silicon Mac) | the k3d cluster (k3s in a container), building the image, the integration tests |
| kubectl | within one minor version of the cluster (tested with 1.35.3 against Kubernetes 1.35.8) | everything in the cluster |
| Python | 3.12 or 3.13 (tested with 3.13; the CI uses 3.12) | the tests and the lint tools |
| GNU Make | 3.81 or newer (the one on macOS works) | every command below |
| k3d | v5.9.0, downloaded by `make tools` into `.bin/` with its SHA-256 checked (nothing is installed system-wide) | the local cluster |
| kubeconform | v0.8.0, downloaded the same way | schema checks of the manifests |
| Network policy enforcement | the policy controller built into k3s (kube-router's), on by default | enforces NetworkPolicy next to k3s's flannel network; a cluster without one accepts the objects and enforces nothing |
| Cluster image | `rancher/k3s:v1.35.8-k3s1` (Kubernetes 1.35.8), set in `cluster/k3d-config.yaml` | pulled by Docker on first `make up` |
| Postgres | `postgres:17-alpine` | each team's database |
| Python packages | Flask, gunicorn, psycopg 3 and its pool at run time; pytest, ruff, mypy, import-linter, yamllint, shellcheck-py, pip-audit for development, all pinned with hashes in `requirements.lock` and `requirements-dev.lock`; `make` installs them into `.venv/` | the service and the checks |

No cloud account and no secrets: each team's database password is generated inside the cluster the first time you run `make up`. The cluster has its own kubeconfig (`.kube/config`, ignored by git); this project never reads or changes `~/.kube/config`. Plan on about 2 GB of memory for the k3s node and both teams.

## Setup, run, test, stop

```bash
make up                  # creates a one-node cluster, builds the images, imports them, creates both teams' Secrets, deploys both teams hardened
make run                 # runs every attack as a developer of team A; each prints BLOCKED with the control that stopped it
make baseline            # the careless stage: no control at all; make run now prints SUCCEEDED for every attack
make harden              # back to every control on
make prove-controls      # switches each control off in turn: its attacks, and only its attacks, succeed
make db                  # runs sql/001 and sql/002 against team A's database (idempotent); TEAM=team-b for the other
make db-queries          # runs the statements the service runs (sql/003_queries.sql)
make test                # unit tests with coverage, the manifest and threat-model policy checks (no cluster needed)
make lint                # ruff, format check, mypy, import rules, yamllint, shellcheck, hadolint, kubeconform
make smoke               # every Done when line on the cluster: baseline, hardened, then one control off at a time (about 7 minutes on an idle laptop, longer when the machine is busy)
make test-integration    # the Postgres adapter, the SQL scripts and the real gunicorn command against a Postgres container
make audit               # known-vulnerability check of the locked dependencies
make down                # deletes the cluster and its kubeconfig
```

`make help` lists every target. `make up` is idempotent. The first run pulls the k3s image (about 250 MB) and the Python and Postgres images.

`make run` acts as `alice`, a member of the group `team-a-humans`, by impersonation with your admin credentials (`kubectl --as=alice --as-group=team-a-humans`), which is how a platform team checks what a person can do without logging in as them. Everything the attacks do is done through that identity, so RBAC is in play for the attacks that need it.

## Done when: the lesson's checklist and the proof for each line

Every line is also checked by an automated cluster test, [tests/e2e/test_done_when.py](tests/e2e/test_done_when.py), which `make smoke` runs; its output is the evidence quoted here. Last full run (2026-11-02, k3d on a busy laptop): from a fresh clone, `make up`, `make run`, `make test` and `make lint` passed; `make smoke` passed with `12 passed in 403.75s`.

| # | Done when (from the lesson) | Command | What proves it |
| --- | --- | --- | --- |
| 1 | **Threat-model it.** Every attack maps to exactly one primary control, and you name one attack that none of these controls stops. | Read [docs/threat-model.md](docs/threat-model.md); `make test` | The table gives each attack file exactly one primary control; the last section, "Not stopped by any of these", names a remote-code-execution bug in an approved image. [tests/policy/test_threat_model.py](tests/policy/test_threat_model.py) fails if an attack file is missing from the table, appears twice, or a row names two controls. |
| 2 | **Least-privilege RBAC.** `kubectl auth can-i --list` as team A shows nothing in team B's namespace, and a pod in team A can't read any secret through the API. | `make harden`, then `kubectl --as=alice --as-group=team-a-humans auth can-i --list -n team-b`, `kubectl --as=system:serviceaccount:team-a:web auth can-i get secrets -n team-b`, `kubectl -n team-a exec deploy/web -- ls /var/run/secrets/kubernetes.io/serviceaccount` | `kubectl --as=alice --as-group=team-a-humans auth can-i --list -n team-b` lists only `selfsubjectreviews`, `selfsubjectaccessreviews` and `selfsubjectrulesreviews` (what every authenticated user may ask about itself) and the standard discovery URLs (`/api`, `/healthz`, `/version` and similar): no resource of team B. `auth can-i get secrets -n team-b` answers `no`, as does the same question as `system:serviceaccount:team-a:web`; `kubectl exec deploy/web -- ls /var/run/secrets/kubernetes.io/serviceaccount` fails because no token is mounted; attack 2 prints `BLOCKED (RBAC: Error from server (Forbidden): secrets "db-credentials" is forbidden: User "system:serviceaccount:team-a:web" ...`. Developers can still do their own work: `auth can-i create deployments -n team-a` answers `yes`. |
| 3 | **Pod Security admission.** A privileged pod and a pod running as root are both rejected with a message naming the rule. | `kubectl --as=alice --as-group=team-a-humans -n team-a apply -f attacks/01-privileged-pod.yaml` and `attacks/01b-root-pod.yaml` | Both applies fail at admission, before any pod exists: `Error from server (Forbidden): error when creating "attacks/01-privileged-pod.yaml": pods "evil" is forbidden: violates PodSecurity "restricted:latest": privileged (container "evil" must not set securityContext.privileged=true) ...` and the same for `rooty` with the rule about running as root. The test asserts both messages and that no attack pod was created. |
| 4 | **Default-deny networking.** Team A's web pod can reach its own database and not team B's, and the test folder proves both directions. | `bash attacks/03-cross-namespace-db.sh`; the same with `ATTACKER_TEAM=team-b VICTIM_TEAM=team-a` | ```text
team-a web -> team-a db:  connection succeeded
team-a web -> team-b db:  connect: [Errno 111] Connection refused
team-b web -> team-b db:  connection succeeded
team-b web -> team-a db:  connect: [Errno 111] Connection refused
```
Both directions, from the same pods in the same run. The rejected connection answers "refused" at once rather than timing out: k3s's policy controller rejects, where a Calico cluster drops silently and the connect would hang until its timeout. Both mean blocked. Both web deployments are ready, which they only are when the allowed flow works (readiness queries the database). |
| 5 | **Quotas and limits.** A deployment that asks for 50 replicas of 1 GiB each is held at the quota, and a pod with no requests gets the defaults. | `scripts/run-attacks.sh attacks/04-exhaust-memory.yaml`; then a pod with only a memory limit, as in the test | `attacks/04-exhaust-memory.yaml` is accepted and held at three pods: `BLOCKED (ResourceQuota: held at 3/50)`, with the ReplicaSet's event `exceeded quota: team-quota, requested: requests.memory=1Gi, used: requests.memory=3328Mi, limited: requests.memory=4Gi` (the other 256 MiB of the 4 GiB belongs to the team's own pods). A pod that names only a memory limit of 32Mi is admitted with requests `{"cpu":"50m","memory":"32Mi"}`: the CPU request came from the LimitRange default, the memory request from Kubernetes' own defaulting of the request to the limit. |
| 6 | **Admission policy in CEL.** Both bad manifests are rejected with your own messages, and every attack in the test folder now fails when you rerun it. | `scripts/run-attacks.sh attacks/05-unapproved-image.yaml attacks/06-no-limits.yaml`, then `make run` | ```text
The pods "outsider" is invalid: : ValidatingAdmissionPolicy 'approved-registry-and-limits' with binding 'approved-registry-and-limits' denied request: image must come from registry.example.test/platform/, got: untrusted.example.test/tools/shell:1.0
The pods "unbounded" is invalid: : ValidatingAdmissionPolicy 'approved-registry-and-limits' with binding 'approved-registry-and-limits' denied request: every container must set a memory limit, missing on: unbounded
```
`make run` then prints `BLOCKED` for all seven attacks: |

### The proof that each control is the one that stops its attack

An attack that fails proves little if it was never able to succeed, or if a different layer stopped it first. Two more runs close that gap, and `make smoke` asserts both:

- `make baseline` then `make run`: with no control at all (and the shortcut the lesson warns about: a team bound to the built-in `edit` role cluster-wide) every attack prints `SUCCEEDED`.
- `make prove-controls`: with one control switched off, exactly the attacks that control owns print `SUCCEEDED` and the rest stay `BLOCKED`.

| Controls on | Attacks that print `SUCCEEDED` | Attacks that print `BLOCKED` |
| --- | --- | --- |
| none (`make baseline`) | all seven (01, 01b, 02, 03, 04 with 50 of 50 pods created, 05, 06) | none |
| all but Pod Security | 01, 01b | 02, 03, 04, 05, 06 |
| all but RBAC | 02 | 01, 01b, 03, 04, 05, 06 |
| all but NetworkPolicy | 03 | 01, 01b, 02, 04, 05, 06 |
| all but the quota | 04 | 01, 01b, 02, 03, 05, 06 |
| all but the admission policy | 05, 06 | 01, 01b, 02, 03, 04 |
| all five (`make harden`) | none | all seven |

Each attack manifest is written to break one rule only (an approved image with limits for the privileged pod, restricted settings for the unapproved image, and so on), because Kubernetes runs its admission checks in a fixed order and a pod that broke two rules would be refused by whichever came first.

### Where this build differs from the lesson's text

- **The admission policy is a `ValidatingAdmissionPolicy`, not a webhook.** The rejection reads "ValidatingAdmissionPolicy ... denied request: image must come from registry.example.test/platform/, got: ..." rather than "admission webhook denied the request". [ADR 0002](docs/adr/0002-admission-policy-in-cel-not-a-webhook.md).
- **Limits are required for memory only.** The policy refuses a container with no memory limit; it does not force a CPU limit.
- **The quota caps requests, not limits.** A quota on limits would also demand limits on every pod, but the ResourceQuota runs after the admission policy, so the pod with no limits is still refused by the policy. The lesson's expected 12/50 depends on the limits you choose; here the quota is 4 GiB of memory requests, so the test reports whatever number of 1 GiB pods fits beside the team's own pods.
- **The rejected cross-team connection is "refused", not a timeout** (see the proof for line 4).
- **"A pod with no requests gets the defaults"** is shown with a pod that names only a memory limit: the memory request becomes the limit (Kubernetes' own defaulting) and the missing CPU request is filled from the LimitRange (`50m`). A pod with no resources at all is refused by the admission policy, which is attack 6.
- **Two extra attack files.** `01b-root-pod.yaml` (the lesson's step 3 asks for a root pod as well as a privileged one) and `06-no-limits.yaml` (step 6 asks for a container without limits to be rejected).
- **The approved registry is a name.** Images are tagged `registry.example.test/platform/...` and loaded into the nodes; nothing is pulled. [ADR 0003](docs/adr/0003-approved-registry-is-a-name-and-images-are-loaded-into-nodes.md).
- **`run-attacks.sh` lives in `scripts/`** and prints a verdict line per attack in the lesson's format.

## Stretch goals

| Stretch (from the lesson) | Built? |
| --- | --- |
| Add an audit policy and find each of your attacks in the API server's audit log. | No. It needs an audit policy file mounted into the k3s server and a way to read the log; the attacks folder is where the checks would go. |
| Swap the static registry rule for signature verification of images. | No. It needs a signing setup and a verifier (a policy engine or an admission controller) outside the built-in policy language. |
| Run a node-level escape attempt inside a VM-based sandbox runtime and compare with the default runtime. | No. It needs a sandbox runtime (gVisor or Kata) and a kernel that can run it, which Docker Desktop's VM does not offer to k3s. |

## What is simplified for teaching

Only what the lesson scopes out:

- One node. The controls are namespace-level, so more nodes would show nothing new.
- The databases keep their data in an `emptyDir`: it lives as long as the pod. A real database gets a PersistentVolumeClaim and a backup.
- No ingress or TLS: traffic reaches the web service through `kubectl port-forward` or from other pods.
- The attacker is a person impersonated with admin credentials, not a user behind an identity provider.
- The approved registry is a name; no registry exists and images are loaded into the nodes.
- Secrets are created by a script, not by an external secrets system, and are not encrypted at rest in this cluster.

## Project structure

```text
src/tenant_web/
  domain/            TeamName, VisitCount and named errors. Depends on nothing outside the standard library.
  application/       RecordVisit and CheckReadiness, and the port they need (VisitStore). Depends on domain only.
  infrastructure/    the Postgres adapter (pooled, with timeouts), settings from the environment, JSON logging.
  interfaces/        the Flask routes and the composition root gunicorn calls.
sql/                 001_schema.sql (DDL), 002_seed.sql (DML), 003_queries.sql: numbered, idempotent, run in order by
                     the Postgres image on first start and by `make db`.
manifests/
  base/              one team's workloads: namespace, service accounts, web, database, Services, PDB.
  controls/          one Kustomize component per control: rbac, careless-rbac (the baseline's shortcut), pod-security,
                     network-policy, quota.
  platform/          the cluster-wide admission policy and its binding.
  identity/          team-a and team-b: the group, the service's team name and the cluster-scoped object names.
  overlays/          baseline (no control) and hardened (every control), each with a directory per team.
attacks/             the attack files: 01, 01b, 04, 05, 06 manifests and 02, 03 shell attacks, and lib.sh.
scripts/             tools.sh, cluster-start.sh, build-images.sh, create-secrets.sh, stage.sh, run-attacks.sh, db.sh.
cluster/             the k3d cluster definition.
tests/
  unit/              domain, application (with an in-memory fake store), settings, logging, HTTP. No Docker, no cluster.
  policy/            the rendered overlays (what each control must contain and what the baseline lacks) and the threat
                     model against the attacks folder.
  integration/       the Postgres adapter, the SQL scripts and the real gunicorn command against a Postgres container.
  e2e/               baseline, hardened and one-control-off runs on the k3d cluster.
docs/                threat-model.md and the decision records in docs/adr/.
tech/                one note per technology, from first principles, with every file of this repository walked through (start at tech/README.md).
Dockerfile           multi-stage, non-root, base image pinned by digest.
Makefile             the only commands a reader needs (make help).
```

The dependency rule (domain depends on nothing; application on domain; infrastructure and interfaces on both; nothing on interfaces) is enforced by `make lint` through import-linter. A second contract keeps `psycopg` and `flask` out of `domain` and `application`.

## Troubleshooting

- **Every attack prints `SUCCEEDED` after `make harden`:** the cluster is not enforcing NetworkPolicy or the admission policy is not bound. Check that `--disable-network-policy` is not set in `cluster/k3d-config.yaml` and that `kubectl get validatingadmissionpolicybinding` lists the binding.
- **Attack 3 prints INCONCLUSIVE:** the team's own database is unreachable, so nothing was proven. Check `kubectl -n team-a get pods` and that `allow-dns` exists.
- **`make up` hangs pulling an image:** Docker Desktop's credential helper can block `docker pull` when many pulls run at once. Pull with an empty client configuration instead: `mkdir -p /tmp/anon-docker && echo '{}' > /tmp/anon-docker/config.json`, then `DOCKER_HOST=unix://$HOME/.docker/run/docker.sock docker --config /tmp/anon-docker pull rancher/k3s:v1.35.8-k3s1` (and `postgres:17-alpine`, `registry.k8s.io/pause:3.10`); the images land in the normal image store.
- **Pods stay `Pending` and the node has a `disk-pressure` taint:** Docker Desktop's disk is full. `cluster/k3d-config.yaml` already relaxes the kubelet's disk thresholds; free space with `docker system prune` if the disk is nearly full.
- **`make up` fails creating the cluster:** run `make down`, make sure Docker has memory to spare, and run `make up` again.
- **A namespace is stuck terminating after a hard stop:** `kubectl get namespace team-a -o json` and look for finalizers; `make down` and `make up` is the quick way out.

## Author and license

Written by Sumit Srivastava. Released under the MIT License, see [LICENSE](LICENSE). Changes are in [CHANGELOG.md](CHANGELOG.md).
