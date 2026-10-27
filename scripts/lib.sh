#!/usr/bin/env bash
# shellcheck shell=bash
# Shared settings for the scripts. Sourced, not run.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-harden}"
TEAMS="team-a team-b"
# The approved registry is a name only. No registry exists: images are built or retagged with this prefix
# and loaded into the nodes, and the admission policy in manifests/platform allows nothing else.
REGISTRY="${REGISTRY:-registry.example.test/platform}"
WEB_IMAGE="$REGISTRY/tenant-web:0.1.0"
DB_IMAGE="$REGISTRY/postgres:17-alpine"
PAUSE_IMAGE="$REGISTRY/pause:3.10"
K3D="$ROOT/.bin/k3d"
export ROOT CLUSTER_NAME TEAMS REGISTRY WEB_IMAGE DB_IMAGE PAUSE_IMAGE K3D
# A kubeconfig of its own: this project never reads or changes ~/.kube/config.
export KUBECONFIG="${KUBECONFIG:-$ROOT/.kube/config}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

require_cluster() {
  kubectl get nodes >/dev/null 2>&1 || die "no cluster reachable through $KUBECONFIG; run: make up"
}

# Render a Kustomize directory. The database init scripts are read from sql/ at the repository root, which
# is outside the kustomization, so the load restrictor is relaxed (files only, and only inside this repository).
render() { kubectl kustomize --load-restrictor=LoadRestrictionsNone "$@"; }
