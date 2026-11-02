# Technology notes

These notes explain every technology used in this repository, from the first principle up, for a reader who has never met any of them. Each file has the same nine headings: what it is, why it is used here, where it appears, how it works underneath, a walkthrough of this repository's own files, commands to try, common mistakes, questions to check yourself, and further reading.

## Ten-minute shortlist

If you only read three files, read these, in this order:

1. [`attacks.md`](attacks.md): how every control is proved by an attack that succeeds without it and is blocked with it.
2. [`rbac.md`](rbac.md): the first control, and the one most often undone by a convenient shortcut.
3. [`network-policy.md`](network-policy.md): the control people most often believe they have when they do not.

## Reading order

| # | File | What it covers |
| --- | --- | --- |
| 1 | [`python.md`](python.md) | The language and the domain, application and settings code. |
| 2 | [`flask.md`](flask.md) | The three web routes. |
| 3 | [`gunicorn.md`](gunicorn.md) | The server and its start-up. |
| 4 | [`postgres.md`](postgres.md) | Postgres, the SQL files, psycopg and the connection pool. |
| 5 | [`environment.md`](environment.md) | How settings reach the program. |
| 6 | [`docker.md`](docker.md) | The image: Dockerfile, `.dockerignore`, `.env.example`. |
| 7 | [`yaml.md`](yaml.md) | The file format of almost everything else, and yamllint. |
| 8 | [`kubernetes.md`](kubernetes.md) | The workload manifests, line by line. |
| 9 | [`kustomize.md`](kustomize.md) | Base, Components, the two teams and the two stages. |
| 10 | [`rbac.md`](rbac.md) | Control 1: who may do what. |
| 11 | [`pod-security.md`](pod-security.md) | Control 2: what a pod may be. |
| 12 | [`network-policy.md`](network-policy.md) | Control 3: who may talk to whom. |
| 13 | [`quota.md`](quota.md) | Control 4: how much a team may take. |
| 14 | [`admission-policy.md`](admission-policy.md) | Control 5: rules in CEL. |
| 15 | [`attacks.md`](attacks.md) | The six attacks and how they are run. |
| 16 | [`kubectl.md`](kubectl.md) | The client commands used everywhere. |
| 17 | [`k3d.md`](k3d.md) | The local cluster. |
| 18 | [`bash.md`](bash.md) | Every script, line by line. |
| 19 | [`make.md`](make.md) | The Makefile targets. |
| 20 | [`toml.md`](toml.md) | `pyproject.toml`: the package and the tool settings. |
| 21 | [`pip.md`](pip.md) | Virtual environment, lock files and hashes. |
| 22 | [`pytest.md`](pytest.md) | The test runner and coverage. |
| 23 | [`tests-unit.md`](tests-unit.md) | The unit tests. |
| 24 | [`tests-policy.md`](tests-policy.md) | Rules checked on the rendered manifests and the threat model. |
| 25 | [`tests-integration.md`](tests-integration.md) | Real Postgres and the real server command. |
| 26 | [`tests-e2e.md`](tests-e2e.md) | The Done-when proofs on the cluster. |
| 27 | [`ruff.md`](ruff.md) | Linting and formatting. |
| 28 | [`mypy.md`](mypy.md) | Type checking. |
| 29 | [`import-linter.md`](import-linter.md) | The layer rules. |
| 30 | [`shellcheck.md`](shellcheck.md) | Checking the scripts. |
| 31 | [`hadolint.md`](hadolint.md) | Checking the Dockerfile. |
| 32 | [`kubeconform.md`](kubeconform.md) | Checking the manifests against the schemas. |
| 33 | [`github-actions.md`](github-actions.md) | The CI workflow. |
| 34 | [`git.md`](git.md) | `.gitignore`, `.editorconfig`, license and history. |

All versions named here are the ones pinned in this repository (Python 3.13, Flask 3.1, gunicorn 25.3, psycopg 3.2, Postgres 17, k3d 5.9.0, Kubernetes 1.35.8, kubeconform 0.8.0, hadolint 2.12.0).
