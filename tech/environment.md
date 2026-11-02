# Environment variables and configuration

## 1. What it is

An **environment variable** is a named text value that the operating system hands to every program it starts: `DB_HOST=db`. A program reads it by name (in Python, `os.environ["DB_HOST"]`). The set of variables a process receives is its **environment**; it is copied from the parent that started it, which is how a Kubernetes pod, a Docker container, a shell and `make` can all steer the same program without changing its code.

## 2. Why this repository uses it

Container platforms deliver configuration this way. The same image runs for both teams; only the environment differs (`TEAM_NAME=team-a` or `team-b`). It also keeps secrets out of the code: each team's database password is delivered from a Kubernetes Secret into `DB_PASSWORD` at run time, never from a file in the repository.

## 3. Where it appears

| Place | Variables |
| --- | --- |
| `.env.example` | The documented list with defaults (walkthrough in `docker.md`). |
| `src/tenant_web/infrastructure/settings.py` | Reads and validates `TEAM_NAME`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_TIMEOUT_SECONDS`, `DB_POOL_SIZE`, `LOG_LEVEL` (see `python.md`). |
| `manifests/base/web.yaml` | `env` entries; `DB_PASSWORD` comes from the Secret `db-credentials`. |
| `manifests/identity/team-*/kustomization.yaml` | Replaces `TEAM_NAME` per team. |
| `scripts/lib.sh`, `attacks/lib.sh` | `CLUSTER_NAME`, `REGISTRY`, `KUBECONFIG`, `ATTACKER_TEAM`, `VICTIM_TEAM`, `ENGINEER`. |
| `Makefile` | `export KUBECONFIG` and `PATH`; `TEAM`, `PYTHON`. |

## 4. How it works underneath

When a process starts, the operating system gives it a block of `NAME=value` strings. A child process inherits a copy, so a change in the child never affects the parent. In a shell, `export NAME=value` marks a variable for inheritance; `NAME=value command` sets it for that one command only. In a Kubernetes pod, the kubelet builds the block from the pod spec: `env` entries one by one, and `valueFrom.secretKeyRef` takes a key from a Secret. Values from a Secret are base64-encoded when stored (an encoding, not encryption) and decoded when delivered.

The app validates its environment once at start. A bad value makes it print a `FATAL invalid configuration: ...` line and exit 1, which Kubernetes shows as a crash. The attack scripts use the same mechanism the other way round: `ATTACKER_TEAM=team-b VICTIM_TEAM=team-a bash attacks/03-cross-namespace-db.sh` runs the attack in the reverse direction.

## 5. Walkthrough of this repository's use



## 6. Try it yourself

```bash
TEAM_NAME=team-z DB_PASSWORD=x .venv/bin/python -c "from tenant_web.infrastructure.settings import Settings; import os; print(Settings.from_env(os.environ).team)"
```

Prints `TeamName(value='team-z')`: the one-command prefix set the variables only for that command.

```bash
kubectl -n team-a exec deploy/web -- env | grep -E "TEAM_NAME|DB_HOST|DB_PORT"
```

Shows `TEAM_NAME=team-a` and `DB_HOST=db`; `DB_PORT` is absent because service links are off (otherwise Kubernetes would inject `DB_PORT=tcp://...`).

```bash
ATTACKER_TEAM=team-b VICTIM_TEAM=team-a bash attacks/03-cross-namespace-db.sh
```

Runs the cross-namespace attack from team B to team A.

## 7. Mistakes people make

- **Committing a real `.env` file.** `.gitignore` excludes `.env`; `.env.example` has no secrets.
- **Reading a variable at import time.** Here settings are read by a function, so tests can pass a dictionary.
- **Assuming a number.** Every variable is text; the app converts and checks.
- **Letting Kubernetes inject names.** `enableServiceLinks: false` stops variables such as `DB_PORT=tcp://...` from replacing the app's own.

## 8. Check yourself

1. Does a child process change its parent's environment? *No, it has a copy.*
2. How does the password reach the pod? *From the Secret via `secretKeyRef` into `DB_PASSWORD`.*
3. How do both teams run the same image? *Each team's overlay sets a different `TEAM_NAME`.*
4. Why does `.env.example` have no password line? *The real one is generated in the cluster.*
5. What happens on an invalid value? *The app logs a FATAL line and exits with status 1.*

## 9. Further reading

- Python `os.environ`: https://docs.python.org/3.13/library/os.html#os.environ
- Kubernetes Secrets: https://kubernetes.io/docs/concepts/configuration/secret/
- Environment variables in pods: https://kubernetes.io/docs/tasks/inject-data-application/define-environment-variable-container/
- Twelve-factor app, config: https://12factor.net/config
