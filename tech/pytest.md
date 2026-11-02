# pytest and coverage

## 1. What it is

pytest is the most used Python test runner. A **test** is a function whose name starts with `test_`; it calls the code under test and uses plain `assert` statements to state what must be true. pytest finds the tests, runs them, and prints which passed and which failed. A **fixture** is a function marked `@pytest.fixture` that prepares something a test needs (a fake, a temporary folder, a running container); a test asks for it by naming it as a parameter. A **marker** (`@pytest.mark.integration`) labels tests so a group can be selected. **coverage** measures which lines (and branches) of the program ran during the tests; `pytest-cov` joins the two.

## 2. Why this repository uses it

The README promises proof for each Done-when line, so there are four kinds of test here: unit tests (no network), policy tests (render the manifests and check them, no cluster), integration tests (a real Postgres in a container) and end-to-end tests (the real cluster: baseline, hardened, and one control off at a time).

## 3. Where it appears

| Folder | Kind | Needs |
| --- | --- | --- |
| `tests/unit/` | Domain, use cases, settings, logging, the Postgres adapter with stubs, HTTP routes, start-up | Nothing |
| `tests/policy/` | Rendered manifests obey the rules; the threat model matches `attacks/` | `kubectl` |
| `tests/integration/` | Postgres adapter, SQL scripts, real gunicorn | Docker |
| `tests/e2e/` | Every Done-when line | The cluster from `make up` |

## 4. How it works underneath

pytest imports each test file, collects every function (and class method) named `test_*`, resolves fixtures by name (looking in the test file, then `conftest.py` files in the folder and its parents), runs each test and records the result. An `assert x == y` that fails prints both sides. `@pytest.mark.parametrize` runs one test body with several inputs; each input is a separate test. `pytest.raises(SomeError)` passes only if the block raises that error.

`--strict-markers` makes an unregistered marker an error, so a typo does not silently select nothing. `-ra` prints a summary of every non-passing result. `testpaths` is where to look when no path is given.

Coverage works by tracing which lines run; with `branch = true` it also notes whether each `if` went both ways. `--fail-under=95` makes the command fail when the percentage is lower, and the Makefile applies it to the domain and application layers.

## 5. Walkthrough of this repository's use

The configuration is in `pyproject.toml`; the test files are explained in `tests-unit.md`, `tests-policy.md`, `tests-integration.md` and `tests-e2e.md`.

### `pyproject.toml`

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
    "integration: needs Docker to run a real Postgres (make test-integration)",
    "policy: renders the manifests with kubectl and checks them, no cluster needed",
    "e2e: needs the local cluster from make up (make smoke)",
]

[tool.coverage.run]
source = ["tenant_web"]
branch = true

[tool.coverage.report]
show_missing = true
skip_covered = false

[tool.importlinter]
root_package = "tenant_web"
include_external_packages = true
```

`[tool.pytest.ini_options]` is pytest's settings table. `testpaths = ["tests"]` makes a plain `pytest` look only in `tests`. `addopts = "-ra --strict-markers"` adds those two options to every run. `markers = [...]` registers the three labels with descriptions: `integration` (needs Docker for a real Postgres), `policy` (renders the manifests with `kubectl`, no cluster) and `e2e` (needs the cluster from `make up`). `[tool.coverage.run]` sets `source = ["tenant_web"]` (measure only the app package) and `branch = true`. `[tool.coverage.report]` sets `show_missing = true` (print the line numbers not covered) and `skip_covered = false` (list files even when fully covered). `[tool.importlinter]` starts the layer-rule settings explained in `import-linter.md`: `root_package = "tenant_web"` and `include_external_packages = true`, which lets rules mention outside libraries such as `redis`.


## 6. Try it yourself

```bash
.venv/bin/python -m pytest tests/unit -q
```

Prints dots for passing tests and a final line such as `43 passed in 0.5s`.

```bash
.venv/bin/python -m pytest tests/unit -q -k settings
```

Runs only tests whose name contains `settings`.

```bash
.venv/bin/python -m pytest tests/unit tests/policy --cov=tenant_web --cov-report=term
```

Adds a table of percentages per file with the missing line numbers.

```bash
.venv/bin/python -m pytest --markers | grep -E "integration|policy|e2e"
```

Lists the three project markers with their descriptions.

## 7. Mistakes people make

- **Tests that depend on each other's order.** Each test here builds what it needs.
- **Asserting on `True` only** (`assert result`) so a failure message says nothing. Prefer comparing to the expected value.
- **Mocking everything.** The adapter has a real Postgres integration test for exactly this reason.
- **A flaky clock.** One test used the real CPU time and failed under load; it now uses an injected clock.
- **Chasing 100 percent.** The bar here is 95 percent on the logic layers, not on glue.

## 8. Check yourself

1. What makes a function a test? *Its name starts with `test_` in a file that pytest collects.*
2. What does `--strict-markers` guard against? *Misspelled markers silently selecting no tests.*
3. Which tests need a cluster? *The ones in `tests/e2e/`, marked `e2e`.*
4. What does `branch = true` add to coverage? *It checks that both outcomes of each decision ran.*
5. Why do the policy tests need `kubectl` but no cluster? *They only render manifests locally.*

## 9. Further reading

- pytest documentation: https://docs.pytest.org/en/stable/
- Fixtures: https://docs.pytest.org/en/stable/how-to/fixtures.html
- Parametrize: https://docs.pytest.org/en/stable/how-to/parametrize.html
- coverage.py: https://coverage.readthedocs.io/en/latest/
- pytest-cov: https://pytest-cov.readthedocs.io/en/latest/
