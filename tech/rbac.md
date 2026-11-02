# RBAC (Role-Based Access Control)

## 1. What it is

Every request to the Kubernetes API server (`kubectl get secret ...`, or a pod calling the API) is checked twice: first **authentication** (who are you?) and then **authorization** (are you allowed?). **RBAC** is the authorization system. It is built from four kinds of object:

- A **Role** is a list of permissions inside one namespace. Each rule names `apiGroups` (the family of the object, `""` for the core group, `apps` for Deployments), `resources` (what, such as `pods`) and `verbs` (which actions: `get`, `list`, `watch`, `create`, `update`, `patch`, `delete`).
- A **ClusterRole** is the same, but cluster-wide or reusable (the built-in `edit` role is a ClusterRole).
- A **RoleBinding** attaches a Role (or a ClusterRole) to **subjects** (a user, a group or a service account) *inside one namespace*.
- A **ClusterRoleBinding** attaches a ClusterRole to subjects in *every* namespace.

A **ServiceAccount** is an identity for a program running in a pod. Kubernetes can mount a token for it inside the pod (`automountServiceAccountToken`); with that token the program can call the API.

## 2. Why this repository uses it

Control 1 of the lesson. Without it, a developer of team A can read team B's database Secret. The baseline uses the shortcut the lesson warns about: a ClusterRoleBinding to the built-in `edit` role "just for convenience". The hardened version replaces it with a Role that lets the team run and inspect its own workloads in its own namespace and nothing else, and removes API tokens from pods that do not need them.

## 3. Where it appears

| File | Role |
| --- | --- |
| `manifests/controls/rbac/role.yaml` | What developers may do in their own namespace. |
| `manifests/controls/rbac/rolebinding.yaml` | Gives the team's group that Role. |
| `manifests/controls/rbac/kustomization.yaml` | The control as a Kustomize Component; also turns off token mounting. |
| `manifests/controls/careless-rbac/` | The baseline's shortcut. |
| `manifests/identity/team-*/kustomization.yaml` | Sets the group name per team. |
| `attacks/02-read-other-secret.sh` | The attack RBAC stops. |

## 4. How it works underneath

The API server computes the answer as: allowed if *any* binding grants the verb on the resource to the requester, otherwise denied. There is no "deny" rule; RBAC only adds permissions, so a careless wide binding cannot be undone by a careful narrow one (attack 2 demonstrates exactly that). A request is attributed to a subject: a human arrives with a user name and groups (here from impersonation, see `attacks.md`), a pod's service account is `system:serviceaccount:<namespace>:<name>`.

`kubectl --as=alice --as-group=team-a-humans` asks the API server to treat the request as that identity; it needs the caller to have the permission to impersonate (the cluster admin has it). A denied request returns `Error from server (Forbidden): secrets "db-credentials" is forbidden: User "alice" cannot get resource "secrets" in API group "" in the namespace "team-b"`.

## 5. Walkthrough of this repository's use

### `manifests/controls/rbac/role.yaml`

```yaml
# What a team's developers may do in their own namespace: run workloads and look at them. No Secrets, no
# RBAC objects, no exec, no namespace-level settings (quotas, policies), and nothing outside the namespace.
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["apps"]
    resources: ["replicasets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch", "create", "delete"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
  - apiGroups: [""]
    resources: ["services", "configmaps", "events"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
```

The comments say what developers may do: run workloads and look at them; no Secrets, no RBAC objects, no `exec`, no namespace-level settings (quotas, policies) and nothing outside the namespace. `kind: Role` named `developer` has five rules. Deployments (`apps` group): all common verbs, so developers can create and change their workloads. ReplicaSets (`apps`): `get`, `list`, `watch` only. Pods (core group `""`): `get`, `list`, `watch`, `create`, `delete`. The subresource `pods/log`: `get`, so `kubectl logs` works. Services, ConfigMaps and events: all common verbs. Secrets, `pods/exec` and RBAC objects appear nowhere, so they are denied.

### `manifests/controls/rbac/rolebinding.yaml`

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: developers
subjects:
  - apiGroup: rbac.authorization.k8s.io
    kind: Group
    name: PLACEHOLDER-set-by-identity
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: developer
```

A `RoleBinding` named `developers` with one subject, a `Group` whose name is the placeholder `PLACEHOLDER-set-by-identity`, and `roleRef` pointing at the Role `developer`. The identity component replaces the placeholder with `team-a-humans` or `team-b-humans`.

### `manifests/controls/rbac/kustomization.yaml`

```yaml
# Control 1, RBAC: the team's people get a Role in their own namespace and nothing anywhere else; no
# workload gets API permissions or a mounted token. The group name is set per team by manifests/identity.
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component
labels:
  - pairs:
      platform.example/control: rbac
    includeSelectors: false
resources:
  - role.yaml
  - rolebinding.yaml
patches:
  - target:
      kind: ServiceAccount
    patch: |-
      - op: add
        path: /automountServiceAccountToken
        value: false
  - target:
      kind: Deployment
    patch: |-
      - op: add
        path: /spec/template/spec/automountServiceAccountToken
        value: false
```

The comment states the control. `kind: Component` (Kustomize's reusable piece, see `kustomize.md`). `labels` adds `platform.example/control: rbac` to every object of the component; `includeSelectors: false` keeps the label out of selectors so it does not change which pods a Deployment owns. The stage script uses this label to find and delete the objects of each control. `resources` lists the Role and RoleBinding. Two patches: for ServiceAccounts, add `automountServiceAccountToken: false`; for Deployments, add the same field in the pod spec, so no pod gets an API token.

### `manifests/controls/careless-rbac/clusterrolebinding.yaml`

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: convenience
subjects:
  - apiGroup: rbac.authorization.k8s.io
    kind: Group
    name: PLACEHOLDER-set-by-identity
  - kind: ServiceAccount
    name: web
    namespace: placeholder
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: edit
```

The shortcut: a `ClusterRoleBinding` named `convenience` that gives the built-in ClusterRole `edit` (create, change and read almost everything, including Secrets) to two subjects: a placeholder group (replaced per team by the identity component) and the ServiceAccount `web` in a placeholder namespace (also replaced). Because it is a ClusterRoleBinding, the permissions apply in every namespace.

### `manifests/controls/careless-rbac/kustomization.yaml`

```yaml
# The shortcut the lesson warns about, used only by the baseline: the team's people and its web account are
# bound to the built-in edit ClusterRole for every namespace "just for convenience". It defeats the isolation
# however careful every other binding is, which attack 02 shows. The name is set per team by manifests/identity.
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component
labels:
  - pairs:
      platform.example/control: careless-rbac
    includeSelectors: false
resources:
  - clusterrolebinding.yaml
```

The comment explains this is used only by the baseline and why it defeats isolation (attack 02 shows it). A Component with the label `platform.example/control: careless-rbac` and the single resource above.


## 6. Try it yourself

```bash
make harden
kubectl auth can-i get secrets -n team-a --as=alice --as-group=team-a-humans
kubectl auth can-i create deployments -n team-a --as=alice --as-group=team-a-humans
kubectl auth can-i get secrets -n team-b --as=alice --as-group=team-a-humans
```

`no` (Secrets are not in the Role), `yes` (Deployments are), `no` (another namespace).

```bash
kubectl auth can-i get secret/db-credentials -n team-b --as=system:serviceaccount:team-a:web
```

`no` once the RBAC control is on; `yes` in the baseline, because of the ClusterRoleBinding.

```bash
kubectl get role,rolebinding -n team-a
kubectl get clusterrolebinding -l platform.example/control
```

The first lists `developer` and `developers`; the second lists the careless binding in the baseline and nothing when hardened.

## 7. Mistakes people make

- **Binding `edit` or `cluster-admin` "for convenience".** One wide binding defeats every narrow rule.
- **Giving developers read access to Secrets.** `get secrets` is a way to read every password in the namespace.
- **Using wildcards (`*`) in verbs or resources.** Future resource types are then included silently.
- **Leaving service-account tokens mounted** in pods that never call the API; stolen pods then hold a key.
- **Forgetting that RoleBindings are per namespace.** A group needs a binding in each namespace it should reach.

## 8. Check yourself

1. What is the difference between a Role and a ClusterRole? *A Role belongs to one namespace; a ClusterRole is cluster-wide or reusable.*
2. Why can a narrow Role not cancel a wide ClusterRoleBinding? *RBAC only grants; there are no deny rules.*
3. What does `automountServiceAccountToken: false` do? *No API credential is placed inside the pod.*
4. Which verbs does the developer Role give on Deployments? *get, list, watch, create, update, patch, delete.*
5. How is a person "alice in team A" represented here? *User `alice`, group `team-a-humans`, via impersonation.*

## 9. Further reading

- Using RBAC authorization: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- Service accounts: https://kubernetes.io/docs/concepts/security/service-accounts/
- Impersonation: https://kubernetes.io/docs/reference/access-authn-authz/authentication/#user-impersonation
- `kubectl auth can-i`: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/
