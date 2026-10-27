#!/usr/bin/env bash
# Put both team namespaces into a stage and wait until their workloads are ready.
#   stage.sh baseline          workloads only, plus the careless convenience binding: no control at all
#   stage.sh hardened          every control: RBAC, Pod Security, NetworkPolicy, quota, admission policy
#   stage.sh without <control> hardened with one control switched off (rbac, pod-security, network-policy,
#                              quota or admission-policy), to show that control is what stops its attack
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cluster

CONTROLS=(rbac pod-security network-policy quota admission-policy)
read -ra team_list <<<"$TEAMS"
stage="${1:-hardened}"
off="${2:-}"
case "$stage" in
  baseline | hardened) ;;
  without) printf '%s\n' "${CONTROLS[@]}" | grep -qx "${off:-none}" || die "usage: stage.sh without <${CONTROLS[*]// /|}>" ;;
  *) die "usage: stage.sh baseline|hardened|without <control>" ;;
esac

# Remove every object a control created, so a stage never inherits a control from the previous one. Pod
# Security labels live on the namespace, so they are removed from there.
reset_controls() {
  kubectl delete role,rolebinding,networkpolicy,resourcequota,limitrange -A -l platform.example/control --ignore-not-found >/dev/null
  kubectl delete clusterrolebinding,validatingadmissionpolicy,validatingadmissionpolicybinding -l platform.example/control --ignore-not-found >/dev/null
  for team in "${team_list[@]}"; do
    kubectl label namespace "$team" pod-security.kubernetes.io/enforce- pod-security.kubernetes.io/enforce-version- \
      pod-security.kubernetes.io/warn- pod-security.kubernetes.io/audit- >/dev/null 2>&1 || true
  done
}

# hardened minus one control, written to a throwaway kustomization next to the kubeconfig (git-ignored)
generate_without() {
  local dir="$ROOT/.kube/stage" team control
  rm -rf "$dir"
  for team in "${team_list[@]}"; do
    mkdir -p "$dir/$team"
    {
      printf 'apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nnamespace: %s\nresources:\n  - ../../../manifests/base\ncomponents:\n' "$team"
      if [ "$off" = "rbac" ]; then printf '  - ../../../manifests/controls/careless-rbac\n'; else printf '  - ../../../manifests/controls/rbac\n'; fi
      for control in pod-security network-policy quota; do
        [ "$control" = "$off" ] || printf '  - ../../../manifests/controls/%s\n' "$control"
      done
      printf '  - ../../../manifests/identity/%s\n' "$team"
    } >"$dir/$team/kustomization.yaml"
  done
  {
    printf 'apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n'
    printf '  - %s\n' "${team_list[@]}"
    [ "$off" = "admission-policy" ] || printf '  - ../../manifests/platform/admission-policy\n'
  } >"$dir/kustomization.yaml"
  echo "$dir"
}

"$ROOT/scripts/create-secrets.sh"
case "$stage" in
  baseline | hardened) source_dir="$ROOT/manifests/overlays/$stage" ;;
  without) source_dir="$(generate_without)" ;;
esac
log "stage: $stage ${off}"
reset_controls
# Server-side apply: an object this script just took a label or a field from is put back by the apply,
# where a client-side apply would believe nothing had changed.
render "$source_dir" | kubectl apply --server-side --force-conflicts -f - >/dev/null
for team in "${team_list[@]}"; do
  kubectl -n "$team" rollout status deployment/db --timeout=600s
  kubectl -n "$team" rollout status deployment/web --timeout=600s
done
