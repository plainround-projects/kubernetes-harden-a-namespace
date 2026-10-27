#!/usr/bin/env bash
# Delete the local kind cluster and its kubeconfig.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [ -x "$KIND" ] && "$KIND" get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  "$KIND" delete cluster --name "$CLUSTER_NAME" --kubeconfig "$KUBECONFIG"
else
  log "no cluster named $CLUSTER_NAME"
fi
rm -rf "$ROOT/.kube"
