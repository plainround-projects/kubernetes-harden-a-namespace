#!/usr/bin/env bash
# Create the local k3d cluster (idempotent) and wait for its node to be Ready.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

"$ROOT/scripts/tools.sh" >/dev/null
mkdir -p "$(dirname "$KUBECONFIG")"
if "$K3D" cluster list --no-headers 2>/dev/null | awk '{print $1}' | grep -qx "$CLUSTER_NAME"; then
  log "cluster $CLUSTER_NAME already exists"
  "$K3D" cluster start "$CLUSTER_NAME" >/dev/null 2>&1 || true
else
  log "creating k3d cluster $CLUSTER_NAME (Kubernetes 1.35, one node)"
  # One cluster is created at a time on this machine: take the lock directory, wait if another run holds it.
  lock=/tmp/plainround-kind-create.lock
  until mkdir "$lock" 2>/dev/null; do
    holder="$(cat "$lock/pid" 2>/dev/null || true)"
    if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then rm -rf "$lock"; continue; fi
    log "another cluster is being created (pid ${holder:-unknown}); waiting 30 seconds"
    sleep 30
  done
  echo $$ >"$lock/pid"
  trap 'rm -rf "$lock"' EXIT
  # The project's own kubeconfig is written below; ~/.kube/config is left alone.
  "$K3D" cluster create "$CLUSTER_NAME" --config "$ROOT/cluster/k3d-config.yaml" \
    --kubeconfig-update-default=false --kubeconfig-switch-context=false
fi
"$K3D" kubeconfig write "$CLUSTER_NAME" --output "$KUBECONFIG" >/dev/null
kubectl wait --for=condition=Ready nodes --all --timeout=600s
kubectl get nodes
