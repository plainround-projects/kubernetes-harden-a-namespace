# TOML (pyproject.toml)

## 1. What it is

TOML is a text format for configuration files. It looks like an INI file with more types: `[table]` headings start a group, `key = value` lines fill it, text goes in double quotes, lists in square brackets (`["a", "b"]`), numbers and `true`/`false` are written plainly, and `#` starts a comment. `[[name]]` (double brackets) adds one more entry to a list of tables. `pyproject.toml` is the standard file where a Python project describes itself (name, version, dependencies) and where tools keep their settings under `[tool.<name>]`.

## 2. Why this repository uses it

One file holds the package definition and the settings of every checking tool (ruff, mypy, pytest, coverage, import-linter). A newcomer finds all rules in one place and the CI uses the same file as a developer.

## 3. Where it appears

The file `pyproject.toml` at the repository root. It is read by `pip` when installing, by `setuptools` when building and by each tool named in a `[tool.*]` heading.

## 4. How it works underneath

When `pip install .` runs, pip reads `[build-system]` to learn which build tool to use (`setuptools`, version 75 or newer) and how to call it (`setuptools.build_meta`). It then asks that tool for the project metadata from the `[project]` table, builds the package and installs it together with the `dependencies` list. `optional-dependencies` define **extras**: extra groups, here `dev`, installed with `pip install '.[dev]'`.

Version ranges: `flask>=3.1,<4` accepts any 3.x from 3.1. The exact installed versions are fixed separately in `requirements.lock` (see `pip.md`). `requires-python = ">=3.12"` refuses older Python versions.

Tools read their own tables: ruff reads `[tool.ruff]` and below, mypy reads `[tool.mypy]`, pytest reads `[tool.pytest.ini_options]`, coverage reads `[tool.coverage.*]`, import-linter reads `[tool.importlinter]`.

## 5. Walkthrough of this repository's use

### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "kubernetes-harden-a-namespace"
version = "0.1.0"
description = "Two team namespaces on a local k3s cluster, hardened with RBAC, Pod Security, NetworkPolicy, quotas and a CEL admission policy, each control proved by an attack that must fail."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
authors = [{ name = "Sumit Srivastava" }]
dependencies = [
    "flask>=3.1,<4",
    "gunicorn>=23,<26",
    "psycopg[binary]>=3.2,<4",
    "psycopg-pool>=3.2,<4",
]
```

`[build-system]` says how to build the package: `requires = ["setuptools>=75"]` lists what must be installed first, `build-backend = "setuptools.build_meta"` names the entry point of the build tool. `[project]` holds the metadata: `name`, `version = "0.1.0"`, a one-line `description`, `readme = "README.md"` (shown as the long description), `requires-python = ">=3.12"`, `license = { text = "MIT" }` (an inline table), and `authors`, a list with one table. `dependencies = [ ... ]` 3.1,<4`, `gunicorn>=23,<26` and `redis>=5.2,<8`.=lists the four libraries the running app imports: `flask>=3.1,<4` (the web framework), `gunicorn>=23,<26` (the server), `psycopg[binary]>=3.2,<4` (the Postgres driver; the `binary` extra brings precompiled speedups so no compiler is needed) and `psycopg-pool>=3.2,<4` (the connection pool).=3.1,<4`, `gunicorn>=23,<26` and `redis>=5.2,<8`.

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8,<10",
    "pytest-cov>=5",
    "ruff>=0.6",
    "mypy>=1.11",
    "import-linter>=2.0",
    "pip-audit>=2.7",
    "pyyaml>=6",
    "types-PyYAML",
    "yamllint>=1.35",
    "shellcheck-py>=0.10",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 120
target-version = "py312"
src = ["src", "tests"]
```

`[project.optional-dependencies]` with `dev = [ ... ]` defines the extra used by developers and CI: `pytest` (tests), `pytest-cov` (coverage), `ruff` (linter and formatter), `mypy` (type checker), `import-linter` (layer rules), `pip-audit` (vulnerability scan), `pyyaml` and `types-PyYAML` (a YAML reader for the policy tests, and its type information), `yamllint` and `shellcheck-py` (a pip-installable copy of shellcheck). `[tool.setuptools.packages.find]` with `where = ["src"]` tells setuptools to look for packages in the `src` folder (the "src layout", which stops tests importing the code by accident from the current folder). `[tool.ruff]` sets `line-length = 120`, `target-version = "py312"` and `src = ["src", "tests"]`, the places ruff treats as the project's own code when sorting imports.

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "N", "C4", "RUF", "PT", "D100", "D101", "D103", "D104"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "tests"]

# Test functions are named for the behavior they check; annotating every one adds noise, not safety.
[[tool.mypy.overrides]]
module = ["tests.*"]
disallow_untyped_defs = false
disallow_incomplete_defs = false
disallow_untyped_calls = false
```

`[tool.ruff.lint]` `select = [...]` turns on rule families by letter: `E` and `F` (pycodestyle errors, pyflakes: unused names), `I` (import order), `B` (likely bugs), `UP` (outdated syntax), `SIM` (simplifications), `N` (naming), `C4` (comprehensions), `RUF` (ruff's own rules), `PT` (pytest style) and four docstring rules, `D100`, `D101`, `D103` and `D104`, which require a docstring on every module, public class, public function and package. `per-file-ignores` turns the `D` rules off for `tests/**`.

`[tool.mypy]` sets `python_version`, `strict = true` (the strictest bundle of checks) and `files = ["src", "tests"]`. The comment explains the override: `[[tool.mypy.overrides]]` for `module = ["tests.*"]` switches off three checks (`disallow_untyped_defs`, `disallow_incomplete_defs`, `disallow_untyped_calls`) because annotating every test function adds noise, not safety.


## 6. Try it yourself

```bash
.venv/bin/python -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); print(d['project']['name'], d['project']['dependencies'])"
```

Prints the project name and the four runtime dependencies. (`tomllib` is in Python's standard library from 3.11.)

```bash
.venv/bin/pip show kubernetes-harden-a-namespace
```

Shows the installed package metadata that came from the `[project]` table.

```bash
.venv/bin/ruff check --show-settings src | head -20
```

Prints the settings ruff read from `[tool.ruff]`.

## 7. Mistakes people make

- **Forgetting the `[tool.x]` heading name**: a typo means the tool silently uses defaults.
- **Using single `[ ]` for repeated tables.** Several `[[tool.importlinter.contracts]]` entries need the double brackets.
- **Wide dependency ranges without a lock.** Two installs a month apart then differ; the lock file prevents that.
- **Strings without quotes.** TOML requires them.

## 8. Check yourself

1. What does `[[tool.importlinter.contracts]]` mean? *One more entry in the list named `contracts`.*
2. Where does the exact list of installed versions live? *In `requirements.lock`, not here.*
3. What does `requires-python = ">=3.12"` do? *pip refuses to install on older Pythons.*
4. What is an extra? *A named optional group of dependencies (`dev`).*
5. Which table configures pytest? *`[tool.pytest.ini_options]`.*

## 9. Further reading

- TOML 1.0 specification: https://toml.io/en/v1.0.0
- Python packaging guide for `pyproject.toml`: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
- setuptools configuration: https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html
