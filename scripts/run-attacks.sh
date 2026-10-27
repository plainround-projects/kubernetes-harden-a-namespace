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
