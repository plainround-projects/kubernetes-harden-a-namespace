# The attacks (how the controls are proved)

## 1. What it is

A **security control** is only worth something if you can show it stops the thing it is for. This repository therefore ships the attacks as files in `attacks/`: six small Kubernetes manifests and shell scripts that a developer of team A runs against the cluster. In the careless baseline every one **succeeds**; in the hardened setup every one is **blocked**, and each can be shown to be blocked by exactly one control by switching that control off.

An attack is *run as* a person, not as the cluster admin: the admin's credentials are used only to **impersonate** (`kubectl --as=alice --as-group=team-a-humans`), which is how a platform team checks what a person can do without logging in as them.

## 2. Why this repository uses it

The lesson's rule is "each control is proved by an attack that must fail". An attack that has not been shown to succeed against the baseline proves nothing (it may fail for an unrelated reason), so the repository demonstrates both sides: baseline all `SUCCEEDED`, hardened all `BLOCKED`, and for each control off in turn only its own attack(s) `SUCCEEDED`.

## 3. Where it appears

| File | Attack | Control that stops it |
| --- | --- | --- |
| `attacks/01-privileged-pod.yaml` | A privileged pod | Pod Security (`pod-security.md`) |
| `attacks/01b-root-pod.yaml` | A pod running as root | Pod Security |
| `attacks/02-read-other-secret.sh` | Team A reads team B's database Secret | RBAC (`rbac.md`) |
| `attacks/03-cross-namespace-db.sh` | Team A's web pod connects to team B's database | NetworkPolicy (`network-policy.md`) |
| `attacks/04-exhaust-memory.yaml` | Fifty replicas of 1 GiB | ResourceQuota (`quota.md`) |
| `attacks/05-unapproved-image.yaml` | An image from an unapproved registry | Admission policy (`admission-policy.md`) |
| `attacks/06-no-limits.yaml` | A container with no memory limit | Admission policy |
| `attacks/lib.sh` | Shared identity and verdict helpers. | |
| `scripts/run-attacks.sh` | Runs all attacks and prints one verdict each (`make run`). | |

## 4. How it works underneath

`run-attacks.sh` applies each manifest as the engineer. If the API server refuses it, the refusal text says which control spoke, and the script maps that text to a name (`violates PodSecurity` is Pod Security, `ValidatingAdmissionPolicy` the admission policy, `exceeded quota` the quota, `is forbidden: User` RBAC). The shell attacks (2 and 3) print their own verdicts. The quota attack is different: the Deployment is accepted, so the script waits 15 seconds, counts the pods that exist, finds the `FailedCreate ... exceeded quota` event, deletes the Deployment and decides.

The scripts' exit status carries the result: `0` only if every attack was blocked, so `make run` can be used in CI, and `make prove-controls` loops over the controls with `stage.sh without <control>`. An attack that cannot reach a verdict returns status 2 (`INCONCLUSIVE`) rather than a false "blocked".

## 5. Walkthrough of this repository's use

### `attacks/lib.sh`

```bash
#!/usr/bin/env bash
# shellcheck shell=bash
# Shared by the attacks: who the attacker is, and how to report a verdict. Sourced, not run.
#
# The attacker is a developer of team A. The identity is impersonated with the admin credentials, which
# is how a platform team checks what a person can do without logging in as them.
ATTACKER_TEAM="${ATTACKER_TEAM:-team-a}"
VICTIM_TEAM="${VICTIM_TEAM:-team-b}"
ENGINEER="${ENGINEER:-alice}"

as_engineer() { kubectl --as="$ENGINEER" --as-group="$ATTACKER_TEAM-humans" -n "$ATTACKER_TEAM" "$@"; }

# blocked <control> <evidence>: the attack failed, which is what the controls are for.
blocked() { printf 'BLOCKED (%s)\n' "$1"; [ -n "${2:-}" ] && printf '    %s\n' "$2"; return 0; }
# succeeded <evidence>: the attack worked.
succeeded() { printf 'SUCCEEDED (%s)\n' "$1"; return 1; }
```

A sourced library. The comment says who the attacker is: a developer of team A, impersonated with the admin credentials. Three settings with overridable defaults: `ATTACKER_TEAM=team-a`, `VICTIM_TEAM=team-b`, `ENGINEER=alice`. `as_engineer()` runs `kubectl` as that person: `--as="$ENGINEER"` the user, `--as-group="$ATTACKER_TEAM-humans"` the group the RoleBinding names, `-n "$ATTACKER_TEAM"` the namespace, and `"$@"` appends whatever arguments the caller gave. `blocked()` prints `BLOCKED (<control>)` and, if a second argument is given (`[ -n "${2:-}" ] &&`), an indented evidence line; it returns 0 (success). `succeeded()` prints `SUCCEEDED (<evidence>)` and returns 1 (failure), so a script's exit status says whether the attack worked.

### `attacks/02-read-other-secret.sh`

```bash
#!/usr/bin/env bash
# Attack 2: the web service's account in team A reads the Secret holding team B's database password, through
# the Kubernetes API. Only RBAC stands in the way.
set -uo pipefail
# shellcheck source=attacks/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

identity="system:serviceaccount:$ATTACKER_TEAM:web"
if output="$(kubectl --as="$identity" -n "$VICTIM_TEAM" get secret db-credentials -o name 2>&1)"; then
  succeeded "read $output as $identity"
else
  blocked "RBAC: $(printf '%s' "$output" | tail -1 | cut -c1-110)"
fi
```

Attack 2: the web service's account in team A reads team B's database Secret through the API; only RBAC stands in the way. `set -uo pipefail` (no `-e`, as the script reports failure itself). `identity="system:serviceaccount:$ATTACKER_TEAM:web"` is how Kubernetes names a service account. The `if` runs `kubectl --as="$identity" -n "$VICTIM_TEAM" get secret db-credentials -o name` and captures its output; if it succeeds, the attack worked: `succeeded "read <name> as <identity>"`. Otherwise `blocked "RBAC: <last line of the error, first 110 characters>"` (`tail -1`, `cut -c1-110`).

### `scripts/run-attacks.sh`

```bash
#!/usr/bin/env bash
# Run every attack in attacks/ as a developer of team A and print one verdict per attack. Exit status 0 only
# if every attack was blocked. Usage: run-attacks.sh [attack-file ...]  (default: all)
#
# Pod and Deployment manifests are applied as the developer; a refusal at admission is the control working,
# and the refusal's own text says which control spoke. Shell attacks print their own verdict.
set -uo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
# shellcheck source=../attacks/lib.sh
source "$ROOT/attacks/lib.sh"
require_cluster

control_of() { # error text -> which control refused
  case "$1" in
    *"violates PodSecurity"*) echo "PodSecurity $(printf '%s' "$1" | grep -o 'restricted:[a-z0-9.]*' | head -1)" ;;
    *"ValidatingAdmissionPolicy"*) echo "ValidatingAdmissionPolicy" ;;
    *"exceeded quota"*) echo "ResourceQuota" ;;
    *"is forbidden: User"*) echo "RBAC" ;;
    *) echo "refused" ;;
  esac
}
```

The header explains the use (`run-attacks.sh [attack-file ...]`, default all; exit 0 only if every attack is blocked). `set -uo pipefail`, then it sources both libraries (`lib.sh` for settings, `attacks/lib.sh` for the engineer) and requires a cluster. `control_of` maps an error text to a control name with a `case` of text patterns: `*"violates PodSecurity"*` prints `PodSecurity` followed by the standard found with `grep -o 'restricted:[a-z0-9.]*'`; `ValidatingAdmissionPolicy`; `exceeded quota` gives `ResourceQuota`; `is forbidden: User` gives `RBAC`; anything else `refused`.

```bash
run_manifest() { # file -> verdict line on stdout, status 0 if blocked
  local file="$1" output
  if output="$(as_engineer apply -f "$file" 2>&1)"; then
    as_engineer delete -f "$file" --ignore-not-found --wait=false >/dev/null 2>&1
    printf 'SUCCEEDED (%s)\n' "$(printf '%s' "$output" | tail -1)"
    return 1
  fi
  printf 'BLOCKED (%s)\n    %s\n' "$(control_of "$output")" "$(printf '%s' "$output" | tail -1 | cut -c1-200)"
  return 0
}
```

`run_manifest file` applies the file as the engineer. If the apply succeeds, it deletes what it created (`--ignore-not-found --wait=false`), prints `SUCCEEDED (<last line>)` and returns 1. If it fails, it prints `BLOCKED (<control>)` and the last line of the error indented, cut to 200 characters, and returns 0.

```bash
run_quota_attack() { # file -> the Deployment is accepted; the quota holds the pods back
  local file="$1" created events
  if ! as_engineer apply -f "$file" >/dev/null 2>&1; then
    printf 'BLOCKED (%s)\n' "refused at apply"
    return 0
  fi
  sleep 15
  created="$(kubectl -n "$ATTACKER_TEAM" get pods -l attack=04 --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  events="$(kubectl -n "$ATTACKER_TEAM" get events --field-selector reason=FailedCreate -o jsonpath='{range .items[*]}{.message}{"\n"}{end}' 2>/dev/null | grep -m1 'exceeded quota')"
  as_engineer delete -f "$file" --ignore-not-found >/dev/null 2>&1
  kubectl -n "$ATTACKER_TEAM" wait --for=delete pod -l attack=04 --timeout=120s >/dev/null 2>&1
  if [ "$created" -lt 50 ] && [ -n "$events" ]; then
    printf 'BLOCKED (ResourceQuota: held at %s/50)\n    %s\n' "$created" "$(printf '%s' "$events" | cut -c1-200)"
    return 0
  fi
  printf 'SUCCEEDED (%s of 50 pods were created)\n' "$created"
  return 1
}
```

`run_quota_attack file` applies the Deployment; if the apply itself fails it reports blocked at apply. Otherwise it sleeps 15 seconds, counts the pods labelled `attack=04`, finds the first `FailedCreate` event message containing `exceeded quota` (`grep -m1`), deletes the Deployment and waits for its pods to go. If fewer than 50 pods exist and the quota event exists it prints `BLOCKED (ResourceQuota: held at N/50)` with the message; otherwise `SUCCEEDED (N of 50 pods were created)`.

```bash
if [ $# -gt 0 ]; then files=("$@"); else files=("$ROOT"/attacks/0*); fi
failed=0
for file in "${files[@]}"; do
  label="attacks/$(basename "$file")"
  printf '== %s ==\n' "$label"
  case "$file" in
    *04-*.yaml) run_quota_attack "$file" || failed=1 ;;
    *.yaml) run_manifest "$file" || failed=1 ;;
    *.sh) bash "$file" || failed=1 ;;
  esac
done
exit "$failed"
```

The main loop: files from the arguments or `attacks/0*`; `failed=0`; for each file it prints a header and dispatches by name: `*04-*.yaml` to the quota function, other `.yaml` files to `run_manifest`, `.sh` files run with `bash`; a non-zero result sets `failed=1`. `exit "$failed"`.


## 6. Try it yourself

```bash
make baseline && make run
```

Every attack prints `SUCCEEDED (...)`; the command exits non-zero.

```bash
make harden && make run
```

Every attack prints `BLOCKED (...)` with the control's own message; the exit status is 0.

```bash
make prove-controls
```

For each control in turn, switches that control off and runs the attacks; only that control's attack(s) print `SUCCEEDED`. At the end the hardened stage is restored.

```bash
bash attacks/02-read-other-secret.sh
```

Run by hand: `BLOCKED (RBAC: Error from server (Forbidden): secrets "db-credentials" is forbidden: ...)`.

## 7. Mistakes people make

- **Only testing that the attack fails.** It might fail because the cluster is broken. The scripts check the team's own path works first, and the baseline run shows the attacks can succeed.
- **Running attacks as the admin.** The admin can do anything; impersonating the engineer tests what the engineer can do.
- **Reading an accepted Deployment as a failed defence.** The quota acts when the ReplicaSet creates pods.
- **Leaving attack pods behind.** The script deletes what it created.
- **Treating the controls as complete.** The threat model names the remaining gap: a remote-code-execution flaw inside the application is not stopped by any of them.

## 8. Check yourself

1. Why impersonate instead of using the admin credentials directly? *To test the engineer's permissions, not the admin's.*
2. What does exit status 2 mean in attack 3? *Inconclusive: the team's own database was unreachable too.*
3. How does `run-attacks.sh` know which control refused? *It matches words in the API server's refusal text.*
4. Why does the quota attack sleep 15 seconds? *Pods are created by the ReplicaSet after the Deployment is accepted.*
5. What does `make prove-controls` show? *That each control, switched off alone, lets its own attack through.*

## 9. Further reading

- Authenticating, user impersonation: https://kubernetes.io/docs/reference/access-authn-authz/authentication/#user-impersonation
- Kubernetes threat model overview: https://kubernetes.io/docs/concepts/security/
- Multi-tenancy: https://kubernetes.io/docs/concepts/security/multi-tenancy/
