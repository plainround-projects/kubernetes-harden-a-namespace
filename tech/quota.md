# ResourceQuota and LimitRange

## 1. What it is

A **ResourceQuota** is a ceiling on what a whole namespace may use or hold: total CPU and memory *requested* by its pods, the number of pods, the number of Deployments or Secrets. The API server counts what exists and refuses to create anything that would cross the ceiling. A **LimitRange** sets per-container defaults and bounds: for example, a container that names no CPU or memory request gets a default one, so it still counts against the quota.

Quantities: CPU is counted in cores, with `m` for a thousandth (`50m` is 5% of one core); memory in bytes with binary suffixes (`Mi` is mebibytes, 1,048,576 bytes; `Gi` is 1,073,741,824).

## 2. Why this repository uses it

Control 4, stopping attack 4: a tenant creates a Deployment of fifty replicas asking for 1 GiB each, enough to starve the other team of the cluster. The Deployment object itself is valid; the quota stops the ReplicaSet from creating pods beyond the cap.

## 3. Where it appears

| File | Role |
| --- | --- |
| `manifests/controls/quota/resourcequota.yaml` | The ceiling. |
| `manifests/controls/quota/limitrange.yaml` | Defaults for requests. |
| `manifests/controls/quota/kustomization.yaml` | The control as a Component. |
| `attacks/04-exhaust-memory.yaml` | The attack it stops. |
| `scripts/run-attacks.sh` | `run_quota_attack`: waits, counts pods, finds the event. |

## 4. How it works underneath

The quota is checked by an admission controller when a pod is created: it adds the pod's requests to the namespace's current total and compares with `hard`. If the sum would exceed it, the pod is refused with `exceeded quota: team-quota, requested: requests.memory=1Gi, used: ..., limited: requests.memory=4Gi`. When the pods come from a Deployment, the refusal happens inside the ReplicaSet controller, so the user sees an accepted Deployment and a record of `FailedCreate` events on the ReplicaSet; the number of pods that actually exist stops at the cap.

A quota on a resource (such as `requests.cpu`) makes that resource *required*: a pod that names no request would be refused. The LimitRange's `defaultRequest` fills the gap. Only requests are capped here on purpose: a quota on *limits* would reject a pod that sets no limits at the quota step, hiding the clearer message of the admission policy (see `admission-policy.md`).

## 5. Walkthrough of this repository's use

### `manifests/controls/quota/resourcequota.yaml`

```yaml
# Only requests are capped. A quota on limits would reject a pod with no limits at the quota step, before
# the admission policy (control 5) could refuse it with its own message.
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-quota
spec:
  hard:
    pods: "20"
    requests.cpu: "2"
    requests.memory: 4Gi
    count/deployments.apps: "10"
    count/secrets: "20"
```

The comment explains why only requests are capped. `kind: ResourceQuota`, name `team-quota`, `spec.hard` lists the ceilings: at most `pods: "20"`; the total of `requests.cpu` at most `"2"` cores; `requests.memory` at most `4Gi`; at most 10 Deployments (`count/deployments.apps`) and 20 Secrets (`count/secrets`). Numbers are written as quoted strings because the API stores quantities as text.

### `manifests/controls/quota/limitrange.yaml`

```yaml
# Defaults for what a container asks for when it says nothing, so it is counted by the quota. Limits get no
# default on purpose: the admission policy requires every container to state its own.
apiVersion: v1
kind: LimitRange
metadata:
  name: team-defaults
spec:
  limits:
    - type: Container
      defaultRequest:
        cpu: 50m
        memory: 64Mi
```

The comment explains the defaults and why limits get none. `kind: LimitRange`, name `team-defaults`; one limit of `type: Container` with `defaultRequest: cpu: 50m, memory: 64Mi`: a container that states no request gets these, so it is counted by the quota.

### `manifests/controls/quota/kustomization.yaml`

```yaml
# Control 4, quota and defaults: a ceiling on what the namespace can ask for in total, and defaults so a
# container that names no requests still counts against it.
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component
labels:
  - pairs:
      platform.example/control: quota
    includeSelectors: false
resources:
  - resourcequota.yaml
  - limitrange.yaml
```

The comment summarises the control: a ceiling on what the namespace can ask for in total, and defaults so a container that names no requests still counts. A Component labelled `platform.example/control: quota` with the two resources.

### `attacks/04-exhaust-memory.yaml`

```yaml
# Attack 4: fifty replicas asking for 1 GiB each. The Deployment itself is valid; what the namespace quota
# stops is the ReplicaSet creating the pods past the cap. The pods are fully compliant otherwise (restricted
# settings, approved image, limits set), so only the quota can hold this back.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hog
  labels:
    attack: "04"
spec:
  replicas: 50
  selector:
    matchLabels:
      attack: "04"
  template:
    metadata:
      labels:
        attack: "04"
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 65534
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: hog
          image: registry.example.test/platform/pause:3.10
```

Attack 4: a Deployment named `hog` labelled `attack: "04"` with 50 replicas. The comment says the Deployment is valid and only the quota stops the pods. The selector and the pod template use the same label so the ReplicaSet owns its pods. The pod spec turns off the service-account token, runs as user 65534 (`nobody`) non-root with the default seccomp profile, and the container `hog` uses the approved `pause` image.

```yaml
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          resources:
            requests: { cpu: 5m, memory: 1Gi }
            limits: { cpu: 10m, memory: 1Gi }
```

The container disallows privilege escalation and drops all capabilities (so Pod Security would accept it), and asks for `requests: { cpu: 5m, memory: 1Gi }` with `limits: { cpu: 10m, memory: 1Gi }`: fifty pods of 1 GiB each is 50 GiB, above the 4 GiB ceiling.


## 6. Try it yourself

```bash
kubectl -n team-a describe resourcequota team-quota
```

Shows each line with `Used` and `Hard` columns (pods 3 of 20, requests.memory used of 4Gi, and so on).

```bash
kubectl -n team-a describe limitrange team-defaults
```

Shows the default request of 50m CPU and 64Mi memory for containers.

```bash
make run
```

Attack 4 prints `BLOCKED (ResourceQuota: held at N/50)` with a `FailedCreate` event message containing `exceeded quota`; the baseline prints `SUCCEEDED (50 of 50 pods were created)` (they stay Pending if the node cannot hold them, but they exist).

## 7. Mistakes people make

- **No quota at all.** One team can take the whole cluster.
- **A quota with no LimitRange defaults.** Pods that name no request are refused with a confusing message.
- **Capping limits instead of requests** when another control owns the "limits required" message.
- **Reading an accepted Deployment as success.** The quota acts on the pods the ReplicaSet creates.
- **Forgetting object counts.** `count/secrets` and `count/deployments.apps` stop floods of cheap objects too.

## 8. Check yourself

1. What does `requests.memory: 4Gi` cap? *The sum of memory requests of all pods in the namespace.*
2. Why is the Deployment accepted in attack 4? *The Deployment is valid; the quota refuses pod creation by its ReplicaSet.*
3. What does a LimitRange `defaultRequest` do? *Gives requests to containers that name none, so they count against the quota.*
4. Why are limits not capped in the quota? *To let the admission policy refuse a pod without limits with its own message.*
5. How is "held at N/50" measured? *The script counts pods labelled `attack=04` after 15 seconds.*

## 9. Further reading

- Resource Quotas: https://kubernetes.io/docs/concepts/policy/resource-quotas/
- Limit Ranges: https://kubernetes.io/docs/concepts/policy/limit-range/
- Resource units: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/#resource-units-in-kubernetes
