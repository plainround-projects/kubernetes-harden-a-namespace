# Pod Security (admission by namespace label)

## 1. What it is

**Pod Security Admission** is a built-in gatekeeper in the Kubernetes API server. When a pod is about to be created, the gatekeeper compares it with one of three standards chosen by labels on its **namespace**:

- **privileged**: no restrictions;
- **baseline**: blocks the known dangerous settings (privileged containers, host networking, host paths);
- **restricted**: the strictest: also requires running as non-root, no privilege escalation, all Linux capabilities dropped and a seccomp profile.

The label `pod-security.kubernetes.io/enforce: restricted` makes the API server **refuse** a pod that does not comply. `warn` only prints a warning to the person applying, and `audit` records the violation in the audit log. `-version: latest` means the rules of the current Kubernetes version.

Linux terms: a **privileged** container has almost the same powers as the host itself (it can see the host's devices). A **capability** is one slice of root's powers (such as changing the network). **seccomp** is a filter of allowed system calls (requests to the kernel).

## 2. Why this repository uses it

Control 2 of the lesson, stopping attack 1 (a privileged pod, which would hand the tenant the node) and attack 1b (a pod running as root). The same label set protects every future pod, including ones nobody has thought of yet.

## 3. Where it appears

| File | Role |
| --- | --- |
| `manifests/controls/pod-security/kustomization.yaml` | Adds the four labels to the namespace. |
| `attacks/01-privileged-pod.yaml`, `attacks/01b-root-pod.yaml` | The two pods the control refuses. |
| `manifests/base/db.yaml`, `web.yaml` | Our own pods already satisfy `restricted`. |

## 4. How it works underneath

The API server runs an **admission controller** after authentication and authorization and before storing an object. For a pod in a labelled namespace it evaluates the pod spec against the named standard. A violation returns an error such as `pods "evil" is forbidden: violates PodSecurity "restricted:latest": privileged (container "evil" must not set securityContext.privileged=true)`. Only the *pod* is checked: a Deployment is accepted and its ReplicaSet then fails to create the pod; `warn` mode reports it to `kubectl` when the Deployment is applied.

## 5. Walkthrough of this repository's use

### `manifests/controls/pod-security/kustomization.yaml`

```yaml
# Control 2, Pod Security admission: the namespace enforces the restricted standard, so a privileged pod or
# a pod running as root is refused at admission with the rule named. Warn and audit are set too, so a
# manifest that would be refused is flagged by kubectl before it is applied.
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component
labels:
  - pairs:
      platform.example/control: pod-security
    includeSelectors: false
patches:
  - target:
      kind: Namespace
    patch: |-
      - op: add
        path: /metadata/labels/pod-security.kubernetes.io~1enforce
        value: restricted
      - op: add
        path: /metadata/labels/pod-security.kubernetes.io~1enforce-version
        value: latest
      - op: add
        path: /metadata/labels/pod-security.kubernetes.io~1warn
        value: restricted
      - op: add
        path: /metadata/labels/pod-security.kubernetes.io~1audit
        value: restricted
```

The comment states the control and why `warn` and `audit` are also set: a manifest that would be refused is flagged by `kubectl` before it is applied. A Component labelled `platform.example/control: pod-security`. One patch on the Namespace adds four labels with the JSON6902 `add` operation. The path `/metadata/labels/pod-security.kubernetes.io~1enforce` uses `~1` to stand for a slash inside a key name (JSON Pointer escaping): the label name itself contains `/`. The values: `enforce: restricted`, `enforce-version: latest`, `warn: restricted`, `audit: restricted`.

### `attacks/01-privileged-pod.yaml`

```yaml
# Attack 1: a careless or malicious tenant runs a privileged pod, which would hand it the node.
# Everything else about this pod is acceptable (approved image, limits set), so only Pod Security can stop it.
apiVersion: v1
kind: Pod
metadata:
  name: evil
  labels:
    attack: "01"
spec:
  containers:
    - name: evil
      image: registry.example.test/platform/pause:3.10
      securityContext:
        privileged: true
      resources:
        requests: { cpu: 10m, memory: 16Mi }
        limits: { cpu: 50m, memory: 32Mi }
```

Attack 1: a Pod named `evil` with the label `attack: "01"` and one container using the approved-registry image `pause` with `securityContext: privileged: true`. The comment explains everything else is acceptable (approved image, limits set), so only Pod Security can stop it. `requests: { cpu: 10m, memory: 16Mi }` and `limits: { cpu: 50m, memory: 32Mi }` are written in YAML's short mapping form.

### `attacks/01b-root-pod.yaml`

```yaml
# Attack 1b: a pod that runs as root. It is otherwise as restricted as the standard asks (no privilege
# escalation, no capabilities, the default seccomp profile, approved image, limits set), so the only rule it
# breaks is the one about root.
apiVersion: v1
kind: Pod
metadata:
  name: rooty
  labels:
    attack: "01b"
spec:
  securityContext:
    runAsUser: 0
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: rooty
      image: registry.example.test/platform/pause:3.10
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
      resources:
        requests: { cpu: 10m, memory: 16Mi }
        limits: { cpu: 50m, memory: 32Mi }
```

Attack 1b: a Pod named `rooty` whose pod-level `securityContext` sets `runAsUser: 0` (root) and the default seccomp profile; its container disallows privilege escalation and drops all capabilities, and it has an approved image and limits. The comment says the only rule it breaks is the one about running as root, which makes the evidence unambiguous.


## 6. Try it yourself

```bash
kubectl get ns team-a --show-labels | tr ',' '\n' | grep pod-security
```

Four labels when hardened, none in the baseline.

```bash
make run   # every attack, as alice in team A
```

Attack 1 and 1b print `BLOCKED (PodSecurity restricted:latest)` and the text `violates PodSecurity`.

```bash
kubectl apply --dry-run=server -f attacks/01b-root-pod.yaml -n team-a
```

Refused with `runAsNonRoot != true` / `runAsUser=0` in the message.

## 7. Mistakes people make

- **Labelling with `warn` only** and believing it blocks.
- **Forgetting init containers**; they are checked too.
- **Relying on it for everything.** It says nothing about images, quotas or network traffic.
- **Granting `exec` or label changes to developers.** Whoever can edit the namespace's labels can switch the control off; the RBAC Role gives developers no right to change namespaces.

## 8. Check yourself

1. Which label turns the control on? *`pod-security.kubernetes.io/enforce: restricted`.*
2. What is the difference between `enforce`, `warn` and `audit`? *Refuse; warn the client; record in the audit log.*
3. Why does attack 1b set `allowPrivilegeEscalation: false` and drop capabilities? *So the only broken rule is running as root.*
4. Is a Deployment itself refused? *No, its pods are.*
5. Why is `latest` used for the version? *The standard follows the cluster's Kubernetes version.*

## 9. Further reading

- Pod Security Admission: https://kubernetes.io/docs/concepts/security/pod-security-admission/
- Pod Security Standards: https://kubernetes.io/docs/concepts/security/pod-security-standards/
- Security contexts: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
