# Kustomize

## 1. What it is

Kustomize is a tool, built into `kubectl` (`kubectl kustomize` and `kubectl apply -k`), that builds the final Kubernetes YAML from a **base** (the normal manifests) plus small **overlays** (a folder that says "take that base and change this"). It works without templates: the base stays valid YAML on its own, and overlays are patches. The file that drives it is always named `kustomization.yaml`.

## 2. Why this repository uses it

Two teams run the same workload, and five controls are switched on or off per stage. Kustomize makes that composable: `base` holds the workload, each control is a reusable **Component**, each team's identity is another Component, and the two overlays (`baseline`, `hardened`) are just lists of what to combine. `stage.sh` can even write a throwaway kustomization for "hardened minus one control".

## 3. Where it appears

| File | Role |
| --- | --- |
| `manifests/base/kustomization.yaml` | Lists the base files; generates the database init ConfigMap from the SQL files. |
| `manifests/controls/*/kustomization.yaml` | One Component per control (walkthroughs in the control notes). |
| `manifests/identity/team-a/`, `team-b/` | Components that set each team's group, name and cluster-scoped object names. |
| `manifests/overlays/baseline/`, `hardened/` | The two stages, each with a folder per team. |
| `manifests/platform/admission-policy/kustomization.yaml` | The cluster-wide policy (see `admission-policy.md`). |
| `scripts/lib.sh` | The `render` function (`--load-restrictor=LoadRestrictionsNone`). |

## 4. How it works underneath

`kubectl kustomize <folder>` reads `<folder>/kustomization.yaml`. `resources:` lists files or folders to include. `namespace:` sets the namespace of every namespaced object. A **Component** (`kind: Component`) is a Kustomization that is added with `components:`; unlike a base it is applied *on top of* the resources already collected, so its patches can change them. Components are applied in the order they are listed, which is why the identity component is listed last: the objects it patches must already exist.

`configMapGenerator` with `files:` builds a ConfigMap whose keys are the file names and whose values are the file contents, and adds a content-hash suffix to the name. By default Kustomize refuses to read files outside the folder tree of the kustomization (a safety rule called the load restrictor); the SQL files live in `sql/` at the repository root, so rendering is done with `--load-restrictor=LoadRestrictionsNone`.

`labels:` adds labels to every object; `includeSelectors: false` keeps them out of label selectors. `patches:` apply JSON6902 operations (`op`, `path`, `value`) to objects chosen by `target`.

## 5. Walkthrough of this repository's use

### `manifests/base/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
# The namespace is set by each team's overlay. Everything here is the same for both teams.
resources:
  - namespace.yaml
  - serviceaccounts.yaml
  - db.yaml
  - web.yaml
configMapGenerator:
  - name: db-init
    files:
      - ../../sql/001_schema.sql
      - ../../sql/002_seed.sql
```

`apiVersion` and `kind: Kustomization` identify the file; the comment says the namespace is set by each team's overlay and that everything here is the same for both teams. `resources:` lists the four base files. `configMapGenerator:` builds a ConfigMap named `db-init` from the two files `../../sql/001_schema.sql` and `../../sql/002_seed.sql`, so the database pod finds them in `/docker-entrypoint-initdb.d`.

### `manifests/identity/team-a/kustomization.yaml`

```yaml
# Who this team is: its people's group, its service name, and the names of its cluster-scoped objects.
# Listed last among a team's components, so the objects it patches already exist.
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component
patches:
  - target:
      kind: RoleBinding
      name: developers
    patch: |-
      - op: replace
        path: /subjects/0/name
        value: team-a-humans
  - target:
      kind: ClusterRoleBinding
      name: convenience
    patch: |-
      - op: replace
        path: /metadata/name
        value: team-a-convenience
      - op: replace
        path: /subjects/0/name
        value: team-a-humans
      - op: replace
        path: /subjects/1/namespace
        value: team-a
  - target:
      kind: Deployment
      name: web
```

The comment explains the component: who this team is (its people's group, its service name, the names of its cluster-scoped objects), listed last. `kind: Component`. Three patches. For the RoleBinding `developers`: replace the first subject's name with `team-a-humans`. For the ClusterRoleBinding `convenience` (present only in the baseline): rename it `team-a-convenience` (cluster-scoped names must be unique per team), set its first subject (the group) to `team-a-humans` and its second subject's namespace (the web ServiceAccount) to `team-a`. The third patch starts: it targets the Deployment `web`.

```yaml
    patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/env/0/value
        value: team-a
```

It replaces the first environment variable of the first container (`TEAM_NAME`) with the value `team-a`.

### `manifests/identity/team-b/kustomization.yaml`

```yaml
# Who this team is: its people's group, its service name, and the names of its cluster-scoped objects.
# Listed last among a team's components, so the objects it patches already exist.
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component
patches:
  - target:
      kind: RoleBinding
      name: developers
    patch: |-
      - op: replace
        path: /subjects/0/name
        value: team-b-humans
  - target:
      kind: ClusterRoleBinding
      name: convenience
    patch: |-
      - op: replace
        path: /metadata/name
        value: team-b-convenience
      - op: replace
        path: /subjects/0/name
        value: team-b-humans
      - op: replace
        path: /subjects/1/namespace
        value: team-b
  - target:
      kind: Deployment
      name: web
```

The same component for team B: the RoleBinding's group becomes `team-b-humans`; the ClusterRoleBinding is renamed `team-b-convenience` with group `team-b-humans` and the web account in namespace `team-b`; the third patch starts on the web Deployment.

```yaml
    patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/env/0/value
        value: team-b
```

The `TEAM_NAME` value becomes `team-b`. A policy test proves the two teams are otherwise identical.

### `manifests/overlays/baseline/kustomization.yaml`

```yaml
# Both teams as a careless platform would leave them. Every attack in attacks/ succeeds here.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - team-a
  - team-b
```

The comment: both teams as a careless platform would leave them; every attack succeeds. It simply includes the two team folders as resources.

### `manifests/overlays/baseline/team-a/kustomization.yaml`

```yaml
# Team a, the baseline: workloads and the careless convenience binding, none of the five controls.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: team-a
resources:
  - ../../../base
components:
  - ../../../controls/careless-rbac
  - ../../../identity/team-a
```

Team A in the baseline: `namespace: team-a`; resources: the base; components: the careless RBAC binding and team A's identity (identity last). No control is included.

### `manifests/overlays/baseline/team-b/kustomization.yaml`

```yaml
# Team b, the baseline: workloads and the careless convenience binding, none of the five controls.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: team-b
resources:
  - ../../../base
components:
  - ../../../controls/careless-rbac
  - ../../../identity/team-b
```

The same for team B (`namespace: team-b`, identity `team-b`).

### `manifests/overlays/hardened/kustomization.yaml`

```yaml
# Both teams with every control, plus the cluster-wide admission policy. Every attack in attacks/ is blocked.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - team-a
  - team-b
  - ../../platform/admission-policy
```

Both teams with every control plus the cluster-wide admission policy: the resources are the two team folders and `../../platform/admission-policy`. Every attack is blocked.

### `manifests/overlays/hardened/team-a/kustomization.yaml`

```yaml
# Team a, hardened: RBAC, Pod Security, NetworkPolicy and quota (the admission policy is cluster-wide, in platform/).
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: team-a
resources:
  - ../../../base
components:
  - ../../../controls/rbac
  - ../../../controls/pod-security
  - ../../../controls/network-policy
  - ../../../controls/quota
  - ../../../identity/team-a
```

Team A hardened: `namespace: team-a`, the base, and four components in order: `rbac`, `pod-security`, `network-policy`, `quota`, then the identity last. The comment notes the admission policy is cluster-wide, so it is not here.

### `manifests/overlays/hardened/team-b/kustomization.yaml`

```yaml
# Team b, hardened: RBAC, Pod Security, NetworkPolicy and quota (the admission policy is cluster-wide, in platform/).
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: team-b
resources:
  - ../../../base
components:
  - ../../../controls/rbac
  - ../../../controls/pod-security
  - ../../../controls/network-policy
  - ../../../controls/quota
  - ../../../identity/team-b
```

The same for team B.


## 6. Try it yourself

```bash
kubectl kustomize --load-restrictor=LoadRestrictionsNone manifests/overlays/hardened | grep -E "^kind:|^  name:" | head -30
```

Prints the objects: namespaces, accounts, roles, policies, deployments, services.

```bash
diff <(kubectl kustomize --load-restrictor=LoadRestrictionsNone manifests/overlays/baseline) <(kubectl kustomize --load-restrictor=LoadRestrictionsNone manifests/overlays/hardened) | head -40
```

Shows what the five controls add (and the careless ClusterRoleBindings they remove).

```bash
kubectl kustomize manifests/overlays/hardened 2>&1 | head -3
```

Without the flag it fails with an error about the `sql/001_schema.sql` file being outside the root: the load restrictor.

## 7. Mistakes people make

- **Listing the identity component first.** Its patches would find nothing to change.
- **Putting control labels into selectors.** Changing a Deployment's selector is not allowed after creation; `includeSelectors: false` avoids it.
- **Hand-editing hash suffixes.** Reference generated ConfigMaps by their original name.
- **Turning the load restrictor off for untrusted folders.** It is relaxed here only for this repository's own files.

## 8. Check yourself

1. What is a Component for? *A reusable piece that patches or adds to whatever is already collected.*
2. Why is the identity component last? *It patches objects created by the earlier ones.*
3. How do both teams share one base? *Each team overlay lists `../../../base` and sets its own `namespace`.*
4. Why the flag `LoadRestrictionsNone`? *The init SQL is outside the kustomization folder.*
5. Where is the admission policy included? *Only in the hardened overlay, once, because it is cluster-wide.*

## 9. Further reading

- Kustomize documentation: https://kubectl.docs.kubernetes.io/references/kustomize/
- `kustomization` file reference: https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/
- Patches: https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/patches/
- Kubernetes task page: https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/
