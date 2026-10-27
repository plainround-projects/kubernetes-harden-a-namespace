#!/usr/bin/env bash
# Create the kind cluster with its default network plugin switched off and install Calico, which enforces
# NetworkPolicy (kindnet, kind's default, accepts the objects and silently enforces nothing). Idempotent.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

CALICO_VERSION="v3.33.0"
CALICO_SHA256="2de8f47595fb9c41b3f47d7b767a1f8e72ecf84057af834738ff12689a234da5"

"$ROOT/scripts/tools.sh" >/dev/null
mkdir -p "$(dirname "$KUBECONFIG")"
if "$KIND" get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  log "cluster $CLUSTER_NAME already exists"
  "$KIND" export kubeconfig --name "$CLUSTER_NAME" --kubeconfig "$KUBECONFIG"
else
  log "creating kind cluster $CLUSTER_NAME (Kubernetes 1.35, no default CNI)"
  "$KIND" create cluster --name "$CLUSTER_NAME" --config "$ROOT/cluster/kind-config.yaml" --kubeconfig "$KUBECONFIG"
fi
if ! kubectl -n kube-system get daemonset calico-node >/dev/null 2>&1; then
  log "installing Calico $CALICO_VERSION"
  manifest="$(mktemp)"
  curl -fsSL -o "$manifest" "https://raw.githubusercontent.com/projectcalico/calico/$CALICO_VERSION/manifests/calico.yaml"
  [ "$(shasum -a 256 "$manifest" | cut -d' ' -f1)" = "$CALICO_SHA256" ] || die "Calico manifest checksum mismatch"
  kubectl apply --server-side -f "$manifest" >/dev/null
  rm -f "$manifest"
fi
kubectl -n kube-system rollout status daemonset/calico-node --timeout=600s
kubectl -n kube-system rollout status deployment/calico-kube-controllers --timeout=600s
kubectl -n kube-system rollout status deployment/coredns --timeout=300s
kubectl wait --for=condition=Ready nodes --all --timeout=300s
kubectl get nodes
