#!/usr/bin/env bash
# Delete the local k3d cluster and its kubeconfig.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [ -x "$K3D" ] && "$K3D" cluster list --no-headers 2>/dev/null | awk '{print $1}' | grep -qx "$CLUSTER_NAME"; then
  "$K3D" cluster delete "$CLUSTER_NAME"
else
  log "no cluster named $CLUSTER_NAME"
fi
rm -rf "$ROOT/.kube"
