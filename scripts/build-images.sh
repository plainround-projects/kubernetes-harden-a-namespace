#!/usr/bin/env bash
# Build the web image and give the three images the approved registry's name, then import them into the
# node of the k3d cluster (there is no registry: the name is what the admission policy checks).
#   tenant-web  built from the Dockerfile
#   postgres    the official image, retagged
#   pause       the Kubernetes pause image, retagged; the attack pods run it because it does nothing
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "building $WEB_IMAGE"
docker build --tag "$WEB_IMAGE" "$ROOT"
retag() { # source target
  docker image inspect "$1" >/dev/null 2>&1 || docker pull "$1"
  docker tag "$1" "$2"
}
retag postgres:17-alpine "$DB_IMAGE"
retag registry.k8s.io/pause:3.10 "$PAUSE_IMAGE"
if "$K3D" cluster list --no-headers 2>/dev/null | awk '{print $1}' | grep -qx "$CLUSTER_NAME"; then
  log "importing the images into cluster $CLUSTER_NAME"
  "$K3D" image import "$WEB_IMAGE" "$DB_IMAGE" "$PAUSE_IMAGE" --cluster "$CLUSTER_NAME" --mode direct
fi
