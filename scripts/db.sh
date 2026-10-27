#!/usr/bin/env bash
# Run the numbered SQL scripts in order against a team's database in the cluster (default team-a).
#   db.sh [team]            001_schema.sql then 002_seed.sql (both idempotent)
#   db.sh [team] queries    003_queries.sql, the statements the service runs
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cluster

team="${1:-team-a}"
mode="${2:-apply}"
psql_in_pod() { kubectl -n "$team" exec -i deploy/db -- sh -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U app -d app -v ON_ERROR_STOP=1"; }
case "$mode" in
  apply) for file in "$ROOT"/sql/001_schema.sql "$ROOT"/sql/002_seed.sql; do log "$(basename "$file") in $team"; psql_in_pod <"$file"; done ;;
  queries) psql_in_pod <"$ROOT/sql/003_queries.sql" ;;
  *) die "usage: db.sh [team] [apply|queries]" ;;
esac
