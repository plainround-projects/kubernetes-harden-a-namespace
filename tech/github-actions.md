# GitHub Actions (CI)

## 1. What it is

**Continuous integration (CI)** means a server automatically builds and tests the project every time someone pushes a change. **GitHub Actions** is GitHub's CI service. A **workflow** is a YAML file (`yaml.md`) in `.github/workflows/`. It names the events that start it, and one or more **jobs**; each job runs on a fresh virtual machine called a **runner** and executes a list of **steps**. A step either runs a shell command (`run:`) or uses a ready-made **action** (`uses:`), a reusable piece of automation published as a repository.

## 2. Why this repository uses it

A reader who clones the project must be able to trust the README's claims. CI repeats the same commands (`make lint`, `make test`, `make up`, `make smoke`) on a clean machine on every push, so "works on my laptop" is not the only evidence. The file is not run during this lesson; it is the proof that the commands are scripted end to end.

## 3. Where it appears

The file `.github/workflows/ci.yml`.

## 4. How it works underneath

GitHub watches for the events in `on:`. For each, it starts the listed jobs; jobs without a `needs:` line run in parallel, each on its own runner (`ubuntu-latest` is an Ubuntu Linux virtual machine). `actions/checkout@v4` copies the repository's files onto the runner; `actions/setup-python@v5` installs the requested Python. The `@v4` after the name is the version tag of the action. A step with `if: failure()` runs only when an earlier step failed, `if: always()` runs even after failures; this is how cleanup and diagnostics are added. The pipe `|` after `run:` starts a multi-line shell script. The `timeout-minutes` limit cancels a job that hangs.

## 5. Walkthrough of this repository's use

### `.github/workflows/ci.yml`

```yaml
name: ci

on: [push, pull_request]

jobs:
  check:
    name: Lint (ruff, mypy, import rules, yamllint, shellcheck, hadolint, kubeconform), unit and policy tests, audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: make lint
      - run: make test
      - run: make audit
```

`name: ci` names the workflow. `on: [push, pull_request]` starts it on every push and on every pull request. `jobs:` begins the list. The job `check` has a display `name` listing what it does, `runs-on: ubuntu-latest`, and `steps`: check out the code; install Python 3.12 (`with:` passes options to an action; the quotes keep `"3.12"` from being read as a number); then three `run:` steps: `make lint`, `make test`, `make audit`.

```yaml
  integration:
    name: Postgres adapter, SQL scripts and the real gunicorn command against a Postgres container
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: make test-integration
```

The job `integration` repeats the checkout and Python setup and runs `make test-integration`. The Postgres container it needs is started by the tests themselves with Docker, which every GitHub runner has.

```yaml
  cluster:
    name: Every control proved by its attack, on a k3d cluster
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: make up
      - run: make run
      - run: make smoke
      - if: failure()
        run: |
          export KUBECONFIG="$PWD/.kube/config"
          kubectl get pods -A -o wide || true
          kubectl get events -A --sort-by=.lastTimestamp | tail -50 || true
      - if: always()
        run: make down
```

The job `cluster` has `timeout-minutes: 60`. After the same two setup steps it runs `make up`, `make run`, `make smoke`. Then two conditional steps. `if: failure()` with a `run: |` block runs only after a failure: it points `KUBECONFIG` at the project's file (`$PWD/.kube/config`), prints all pods of all namespaces (`-A`, `-o wide`) and the last 50 events of all namespaces sorted by time (`tail -50`). The `|| true` after each keeps this diagnostic step from failing. The last step, `if: always()`, runs `make down` whatever happened.


## 6. Try it yourself

```bash
.venv/bin/yamllint -s .github/workflows/ci.yml
```

Prints nothing when the workflow is valid YAML in the repository style.

```bash
make lint && make test && make audit
```

The first job's three steps, run locally; each ends without error.

```bash
make up && make run && make smoke; make down
```

The third job's steps (it takes about fifteen minutes).

## 7. Mistakes people make

- **A cleanup step without `if: always()`.** A failing test would leave the resources running.
- **Unpinned action versions** such as `@main`. A moving tag can change what runs.
- **Putting secrets in the file.** There are none here; none are needed.
- **Different commands in CI and locally.** CI here only calls `make` targets, so they cannot drift.

## 8. Check yourself

1. What starts this workflow? *Any push and any pull request.*
2. How many jobs are there and do they depend on each other? *Three, independent: check, integration, cluster.*
3. When does the `kubectl get pods` step run? *Only if an earlier step failed (`if: failure()`).*
4. Why does the last step run `make down` with `always()`? *The cluster must be deleted even when tests fail.*
5. What does `uses: actions/checkout@v4` do? *Fetches the repository's files onto the runner.*

## 9. Further reading

- GitHub Actions documentation: https://docs.github.com/en/actions
- Workflow syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- `actions/checkout`: https://github.com/actions/checkout
- `actions/setup-python`: https://github.com/actions/setup-python
