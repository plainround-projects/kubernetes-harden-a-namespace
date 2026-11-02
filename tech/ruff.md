# ruff

## 1. What it is

ruff is a very fast tool that does two jobs for Python code: **linting** (reading code and reporting likely mistakes and style problems, each with a rule code such as `F401` "imported but unused") and **formatting** (rewriting the layout of code, such as line breaks and quote style, into one consistent style, like the older tool Black). Both are in one program, written in Rust, installed from pip.

## 2. Why this repository uses it

One tool and one configuration replace half a dozen older ones. `make lint` runs `ruff check` and `ruff format --check`, so style never needs discussing in a review, and `make format` fixes everything that can be fixed automatically.

## 3. Where it appears

| File | Role |
| --- | --- |
| `pyproject.toml` | `[tool.ruff]` and `[tool.ruff.lint]` settings (walkthrough in `toml.md`). |
| `Makefile` | Targets `lint` and `format`. |
| `src/`, `tests/` | The checked code. |

## 4. How it works underneath

ruff parses each Python file into a syntax tree and runs its enabled rules over the tree. Rules are grouped by prefix letters; this project enables `E`/`F` (the basics), `I` (sorted imports), `B` (bugbear: patterns that are usually bugs), `UP` (use modern syntax for the target Python version), `SIM` (simplify), `N` (naming), `C4` (comprehensions), `RUF` (ruff's own), `PT` (pytest style) and four docstring rules. `ruff check --fix` rewrites code for fixes that are known safe. `ruff format` re-prints the whole file from its tree using a fixed style, so two people always get identical output. `line-length = 120` sets the wrap width and `target-version = "py312"` tells it which language features it may assume.

## 5. Walkthrough of this repository's use

The configuration lines are quoted and explained in `toml.md`. The commands:



## 6. Try it yourself

```bash
.venv/bin/ruff check .
```

Prints `All checks passed!`.

```bash
.venv/bin/ruff format --check .
```

Prints `N files already formatted`.

```bash
printf 'import os\nx=1\n' > /tmp/t.py && .venv/bin/ruff check /tmp/t.py
```

Reports `F401 os imported but unused` and the format difference with `ruff format --diff /tmp/t.py`.

```bash
.venv/bin/ruff rule F401
```

Prints the full explanation of one rule.

## 7. Mistakes people make

- **Disabling a rule instead of reading it.** Most warnings point at real problems.
- **Running the formatter and linter fixes in the wrong order.** `make format` runs `check --fix` first and then `format`.
- **Mixing two formatters.** Only ruff formats here.

## 8. Check yourself

1. What is the difference between `check` and `format`? *`check` finds problems, `format` rewrites layout.*
2. What does `--fix` do? *Applies the safe automatic corrections.*
3. What does the `I` family enforce? *Import order.*
4. Why are docstring rules off for tests? *Test names already say what they check.*
5. What command applies formatting? *`make format`.*

## 9. Further reading

- ruff documentation: https://docs.astral.sh/ruff/
- Rules list: https://docs.astral.sh/ruff/rules/
- Configuration: https://docs.astral.sh/ruff/configuration/
