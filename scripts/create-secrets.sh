#!/usr/bin/env bash
# Create each team's namespace and its database Secret with a random password, unless they exist. The
# passwords are generated here, on the machine that runs the cluster, and are in no file of this repository.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cluster

read -ra team_list <<<"$TEAMS"
for team in "${team_list[@]}"; do
  kubectl create namespace "$team" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  if kubectl -n "$team" get secret db-credentials >/dev/null 2>&1; then
    log "secret db-credentials already exists in $team"
    continue
  fi
  password="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
  kubectl -n "$team" create secret generic db-credentials --from-literal=password="$password" >/dev/null
  log "created secret db-credentials in $team"
done
