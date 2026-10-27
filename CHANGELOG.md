# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-27

### Added

- Two team namespaces on a kind cluster with Calico, each running a small web service (Python, Flask, gunicorn) and a Postgres database, with the schema, seed and queries as numbered SQL files.
- Five controls as Kustomize components: RBAC with no mounted tokens, the `restricted` Pod Security standard, default-deny NetworkPolicy with DNS and web-to-database allowed, a ResourceQuota with a LimitRange, and a CEL ValidatingAdmissionPolicy for the approved registry and memory limits.
- Seven attacks (privileged pod, root pod, cross-team Secret, cross-team database, memory exhaustion, unapproved image, no limits), a runner that prints one verdict per attack, a baseline stage in which all of them succeed, and a mode that switches each control off in turn.
- A threat model whose table is checked against the attacks folder, a layered package with the dependency rule enforced by import-linter, unit, policy, integration and cluster tests, ruff, mypy, hadolint, yamllint, shellcheck, kubeconform, a hash-pinned lock file and a CI workflow.
