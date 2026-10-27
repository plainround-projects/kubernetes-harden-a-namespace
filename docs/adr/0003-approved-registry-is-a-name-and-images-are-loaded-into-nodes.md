# 0003. The approved registry is a name, and images are loaded into the nodes

Date: 2026-10-27. Status: accepted.

## Context

The admission policy allows images from one registry prefix. A local k3d cluster has no registry, and the project must run on a laptop with no account anywhere.

## Decision

The approved prefix is `registry.example.test/platform/` (`.test` is reserved and never resolves). `scripts/build-images.sh` builds the web image with that name, retags the official Postgres image and the Kubernetes pause image with it, and runs `k3d image import` so the node already holds them; the pods use `IfNotPresent`, so nothing is pulled. The unapproved image in attack 5 is `untrusted.example.test/tools/shell:1.0`, which is refused before any pull would happen.

## Alternatives considered

- **A real registry container on the cluster network** (k3d can create one). More moving parts than the lesson needs, and the admission rule is the same string check.
- **Allowing the public registries the workloads come from.** Then "unapproved" would need a made-up name anyway, and the allow-list would hide that the policy is a platform decision.

## Consequences

Retagging means the Postgres image the pods run is the official one under another name; in a real platform the approved registry is a mirror you populate after scanning. The README says so. The retag-and-load step is the only place the repository's scripts call `docker pull`.
