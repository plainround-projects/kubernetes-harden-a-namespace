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
