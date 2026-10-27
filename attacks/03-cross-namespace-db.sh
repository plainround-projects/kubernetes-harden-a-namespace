#!/usr/bin/env bash
# Attack 3: from inside team A's web pod, open a connection to team B's database port. Only NetworkPolicy
# stands in the way. Team A's own database is tried first: if that fails too, the test says so instead of
# calling a broken namespace "blocked".
set -uo pipefail
# shellcheck source=attacks/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

probe() { # host -> connected | timed out | refused | <error>
  kubectl -n "$ATTACKER_TEAM" exec deploy/web -- python -c '
import socket, sys
connection = socket.socket()
connection.settimeout(4)
try:
    connection.connect((sys.argv[1], 5432))
    print("connection succeeded")
except TimeoutError:
    print("connect: Connection timed out")
except OSError as error:
    print("connect: " + str(error))
' "$1" 2>&1 | tail -1
}

own="$(probe "db.$ATTACKER_TEAM.svc.cluster.local")"
other="$(probe "db.$VICTIM_TEAM.svc.cluster.local")"
printf '    %s web -> %s db:  %s\n' "$ATTACKER_TEAM" "$ATTACKER_TEAM" "$own"
printf '    %s web -> %s db:  %s\n' "$ATTACKER_TEAM" "$VICTIM_TEAM" "$other"
if [ "$own" != "connection succeeded" ]; then
  echo "INCONCLUSIVE (the team's own database is unreachable too, so nothing was proven)"
  exit 2
fi
if [ "$other" = "connection succeeded" ]; then
  succeeded "reached $VICTIM_TEAM's database from $ATTACKER_TEAM"
else
  blocked "NetworkPolicy: $other"
fi
