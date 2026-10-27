# 0001. Each control is a Kustomize component, and each attack is built to break one rule

Date: 2026-10-27. Status: accepted.

## Context

The lesson adds five controls one at a time and says each must have a test that fails when the control is missing. A reader also wants to switch a control on and off without editing files, and to see that an attack is stopped by the control the threat model names, not by some other layer that happens to refuse it first.

## Decision

- `manifests/base` is the workloads for one team and nothing else. `manifests/controls/<name>` is a Kustomize **Component** per control (RBAC, Pod Security, NetworkPolicy, quota and defaults), each labeling its objects `platform.example/control=<name>`. `manifests/platform/admission-policy` is the cluster-wide fifth control. `manifests/identity/team-a` and `team-b` are components that set the team-specific names (the group, the cluster-scoped object names, the service's team name) and are listed last so the objects they patch exist.
- `overlays/baseline` is the careless platform (a ClusterRoleBinding to `edit`, no other control). `overlays/hardened` is every control. `scripts/stage.sh without <control>` generates hardened minus one control.
- Every attack is a manifest or command that violates exactly one rule: the pod for attack 4 is otherwise restricted, approved and limited; the pod for attack 5 is otherwise compliant; and so on. Admission plugins run in a fixed order (Pod Security, then limits and quota, then policies), so a pod that broke two rules would be refused by whichever came first and the test would credit the wrong control.
- The cluster test runs the whole attacks folder in three situations: in the baseline every attack succeeds, hardened every attack is blocked, and with control X off exactly the attacks owned by X succeed.

## Alternatives considered

- **One flat manifest per stage.** Four copies of the same objects drift apart.
- **Helm with a values flag per control.** Works, but Helm is not what the lesson teaches and templated conditionals hide which objects a control adds.
- **Test only the hardened state.** "Every attack is blocked" can pass because an attack is malformed. The baseline run proves the attacks are real.

## Consequences

`make prove-controls` takes minutes because each stage re-applies the namespaces and waits for pods. The generated stage directory lives in `.kube/stage` (ignored by git). The team-specific names are patched by `identity` components; adding a third team means a new identity component and two small overlay directories.
