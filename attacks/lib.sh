#!/usr/bin/env bash
# shellcheck shell=bash
# Shared by the attacks: who the attacker is, and how to report a verdict. Sourced, not run.
#
# The attacker is a developer of team A. The identity is impersonated with the admin credentials, which
# is how a platform team checks what a person can do without logging in as them.
ATTACKER_TEAM="${ATTACKER_TEAM:-team-a}"
VICTIM_TEAM="${VICTIM_TEAM:-team-b}"
ENGINEER="${ENGINEER:-alice}"

as_engineer() { kubectl --as="$ENGINEER" --as-group="$ATTACKER_TEAM-humans" -n "$ATTACKER_TEAM" "$@"; }

# blocked <control> <evidence>: the attack failed, which is what the controls are for.
blocked() { printf 'BLOCKED (%s)\n' "$1"; [ -n "${2:-}" ] && printf '    %s\n' "$2"; return 0; }
# succeeded <evidence>: the attack worked.
succeeded() { printf 'SUCCEEDED (%s)\n' "$1"; return 1; }
