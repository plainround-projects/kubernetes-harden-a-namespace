# ValidatingAdmissionPolicy and CEL

## 1. What it is

An **admission policy** is a rule that the API server runs on every create or update of an object, before storing it. A **ValidatingAdmissionPolicy** is the built-in, no-extra-software way to write such a rule. It has:

- `matchConstraints`: which objects it looks at (here: pods, on create and update);
- `variables`: named helper values;
- `validations`: expressions that must be true, each with a message and a `reason`;
- `failurePolicy`: what to do if the policy itself fails (`Fail` means refuse).

A **ValidatingAdmissionPolicyBinding** attaches the policy to namespaces and chooses the `validationActions` (`Deny` refuses; `Warn` and `Audit` only report). The expressions are written in **CEL** (Common Expression Language), a small, safe language for yes/no questions: `object.spec.containers` is the pod's list of containers, `.all(c, test)` is true if the test holds for every item, `.filter(c, test)` keeps matching items, `.map(c, value)` transforms them, `has(field)` tests that a field exists, `startsWith('...')` and `in` do what they say.

## 2. Why this repository uses it

Controls 5, stopping attacks 5 and 6: a pod using an image from a registry that is not on the allow-list (anyone's tools, from anywhere), and a pod whose container sets no memory limit (it may use all the memory of its node). Pod Security cannot see either: it checks privilege, not where an image comes from or whether limits exist.

## 3. Where it appears

| File | Role |
| --- | --- |
| `manifests/platform/admission-policy/policy.yaml` | The two rules, in CEL. |
| `manifests/platform/admission-policy/binding.yaml` | Applies them to namespaces labelled as tenants. |
| `manifests/platform/admission-policy/kustomization.yaml` | The control as a Kustomization, cluster-wide (not per team). |
| `attacks/05-unapproved-image.yaml`, `attacks/06-no-limits.yaml` | The two pods it refuses. |
| `manifests/base/namespace.yaml` | Carries the label the binding selects. |

## 4. How it works underneath

The policy and binding are cluster-scoped objects owned by the platform team, not the tenants. When a pod is created in a namespace whose labels match the binding's `namespaceSelector`, the API server evaluates each `validation` expression with `object` set to the new pod. A false result produces the refusal, using `messageExpression` (itself CEL) to build a message that names the offending images or containers: `ValidatingAdmissionPolicy 'approved-registry-and-limits' with binding 'approved-registry-and-limits' denied request: every container must set a memory limit, missing on: unbounded`. CEL is evaluated inside the API server with bounded cost, so a bad expression cannot hang it.

## 5. Walkthrough of this repository's use

### `manifests/platform/admission-policy/policy.yaml`

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: approved-registry-and-limits
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods"]
  variables:
    - name: containers
      expression: >-
        object.spec.containers + (has(object.spec.initContainers) ? object.spec.initContainers : [])
  validations:
    - expression: >-
        variables.containers.all(c, c.image.startsWith('registry.example.test/platform/'))
      messageExpression: >-
        'image must come from registry.example.test/platform/, got: ' +
        variables.containers.filter(c, !c.image.startsWith('registry.example.test/platform/')).map(c, c.image).join(', ')
      reason: Invalid
    - expression: >-
        variables.containers.all(c, has(c.resources.limits) && 'memory' in c.resources.limits)
      messageExpression: >-
        'every container must set a memory limit, missing on: ' +
        variables.containers.filter(c, !(has(c.resources.limits) && 'memory' in c.resources.limits)).map(c, c.name).join(', ')
```

`apiVersion: admissionregistration.k8s.io/v1`, `kind: ValidatingAdmissionPolicy`, name `approved-registry-and-limits`. `failurePolicy: Fail` refuses requests if the policy cannot be evaluated. `matchConstraints.resourceRules` selects `pods` in the core group (`apiGroups: [""]`), version `v1`, for the operations `CREATE` and `UPDATE`. The variable `containers` is the CEL expression `object.spec.containers + (has(object.spec.initContainers) ? object.spec.initContainers : [])`: the containers plus the init containers when the pod has any (`cond ? a : b` is "if cond then a else b"); the `>-` after `expression:` is YAML's way to write a long value over several lines folded into one. The first validation requires `variables.containers.all(c, c.image.startsWith('registry.example.test/platform/'))`: every image name starts with the approved prefix. Its `messageExpression` builds the message by listing the images that do not (`filter` keeps the offenders, `map` takes their image, `join(', ')` glues them). The second validation requires `variables.containers.all(c, has(c.resources.limits) && 'memory' in c.resources.limits)`: every container has a limits section that includes memory; its message lists the container names that lack it.

```yaml
      reason: Invalid
```

`reason: Invalid` is the reason code attached to the second refusal (the first has the same).

### `manifests/platform/admission-policy/binding.yaml`

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: approved-registry-and-limits
spec:
  policyName: approved-registry-and-limits
  validationActions: [Deny]
  matchResources:
    namespaceSelector:
      matchLabels:
        platform.example/tenant: "true"
```

`kind: ValidatingAdmissionPolicyBinding`, name `approved-registry-and-limits`, `policyName` pointing at the policy, `validationActions: [Deny]` (refuse), and `matchResources.namespaceSelector` choosing namespaces by the label `platform.example/tenant: "true"`. Only tenant namespaces are affected, never `kube-system`.

### `manifests/platform/admission-policy/kustomization.yaml`

```yaml
# Control 5, admission policy in CEL, cluster-wide and bound to the namespaces that carry the tenant label.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - policy.yaml
  - binding.yaml
labels:
  - pairs:
      platform.example/control: admission-policy
    includeSelectors: false
```

The comment says: control 5, cluster-wide, bound to the namespaces that carry the tenant label. A `Kustomization` (not a Component, because it is applied once for the whole cluster) listing the policy and the binding and labelling both `platform.example/control: admission-policy` so the stage script can remove them.

### `attacks/05-unapproved-image.yaml`

```yaml
# Attack 5: an image from a registry that is not on the allow-list. The pod is compliant otherwise, so only
# the admission policy can stop it.
apiVersion: v1
kind: Pod
metadata:
  name: outsider
  labels:
    attack: "05"
spec:
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: outsider
      image: untrusted.example.test/tools/shell:1.0
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
      resources:
        requests: { cpu: 10m, memory: 16Mi }
        limits: { cpu: 50m, memory: 32Mi }
```

Attack 5: a Pod named `outsider` labelled `attack: "05"`. Everything is compliant (no token mounted, non-root user 65534, default seccomp, no escalation, capabilities dropped, requests and limits set) except the image `untrusted.example.test/tools/shell:1.0`, which is outside the approved registry. The comment says only the admission policy can stop it.

### `attacks/06-no-limits.yaml`

```yaml
# Attack 6: a container that names requests but no limits, so it may use all the memory of its node. The pod
# is compliant otherwise, so only the admission policy's second rule can stop it.
apiVersion: v1
kind: Pod
metadata:
  name: unbounded
  labels:
    attack: "06"
spec:
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: unbounded
      image: registry.example.test/platform/pause:3.10
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
      resources:
        requests: { cpu: 10m, memory: 16Mi }
```

Attack 6: a Pod named `unbounded` labelled `attack: "06"`, compliant like attack 5 and with the approved `pause` image, but its `resources` has `requests` and no `limits`, so it could use all the memory of its node. The comment says the policy's second rule stops it.


## 6. Try it yourself

```bash
kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding
```

Lists `approved-registry-and-limits` once each when hardened.

```bash
make run
```

Attack 5 prints `BLOCKED (ValidatingAdmissionPolicy)` with `image must come from registry.example.test/platform/, got: untrusted.example.test/tools/shell:1.0`; attack 6 prints the same verdict with `every container must set a memory limit, missing on: unbounded`.

```bash
kubectl label ns team-a platform.example/tenant- && kubectl apply -f attacks/05-unapproved-image.yaml -n team-a --as=alice --as-group=team-a-humans
```

With the label removed (a platform admin action) the policy no longer applies. Put it back with `kubectl label ns team-a platform.example/tenant=true`.

## 7. Mistakes people make

- **A binding with `Warn` or `Audit` only** and believing it blocks.
- **Forgetting init containers.** The policy joins `containers` and `initContainers` in a variable.
- **A policy that matches too little.** A policy for `pods` does not see Deployments; here Deployments' pods are still checked when created.
- **Letting tenants edit namespace labels.** The RBAC Role has no rights on namespaces, so tenants cannot remove the selector label.
- **Relying on image name prefixes alone.** A prefix check proves where the name points, not that the image is trustworthy; real platforms also verify signatures.

## 8. Check yourself

1. Who writes and owns this policy? *The platform team; it is cluster-scoped.*
2. What does `variables.containers.all(c, ...)` mean? *The test must hold for every container.*
3. What does `validationActions: [Deny]` do? *Refuses the request.*
4. Which label chooses the namespaces? *`platform.example/tenant: "true"`.*
5. Why can Pod Security not replace this? *It does not look at image registries or limits.*

## 9. Further reading

- Validating Admission Policy: https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/
- CEL in Kubernetes: https://kubernetes.io/docs/reference/using-api/cel/
- CEL language definition: https://cel.dev/
- Admission controllers: https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/
