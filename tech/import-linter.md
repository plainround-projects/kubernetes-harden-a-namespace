# import-linter

## 1. What it is

import-linter is a Python tool that checks **which modules are allowed to import which**. You write rules ("contracts") in the configuration; it reads the source, builds a graph of who imports whom, and fails if a rule is broken. The command is `lint-imports`. This repository uses it to enforce its layered design: the code is split into four layers, and an inner layer must never depend on an outer one.

## 2. Why this repository uses it

A layered design only stays layered if something stops a shortcut from creeping in at 5 p.m. on a Friday. Here the rules are: the web layer may use the Postgres layer, which may use the use-case layer, which may use the domain layer, but never the other way. And the domain and application layers must know nothing about Flask or Postgres. If someone writes `import psycopg` in the domain, `make lint` fails.

## 3. Where it appears

| File | Role |
| --- | --- |
| `pyproject.toml` | The `[tool.importlinter]` table and two contracts. |
| `Makefile` | Target `lint` runs `lint-imports`. |
| `src/tenant_web/` | The package it inspects. |

## 4. How it works underneath

import-linter uses a library called Grimp to read every `.py` file in the root package, find each `import` statement and make a directed graph (an arrow from the importing module to the imported one). A **layers** contract lists packages from highest to lowest; it fails if a lower package imports a higher one, directly or through a chain. A **forbidden** contract lists source modules and modules that they must not import, directly or indirectly. With `include_external_packages = true` the graph also contains third-party packages, which is what allows the second contract to name `psycopg`, `psycopg_pool` and `flask`.

## 5. Walkthrough of this repository's use

### `pyproject.toml`

```toml
[[tool.importlinter.contracts]]
name = "Layers: interfaces -> infrastructure -> application -> domain, never upward"
type = "layers"
layers = [
    "tenant_web.interfaces",
    "tenant_web.infrastructure",
    "tenant_web.application",
    "tenant_web.domain",
]

[[tool.importlinter.contracts]]
name = "Domain and application know nothing about Postgres or Flask"
type = "forbidden"
source_modules = ["tenant_web.domain", "tenant_web.application"]
forbidden_modules = ["psycopg", "psycopg_pool", "flask"]
```

The first `[[tool.importlinter.contracts]]` has a `name` (shown in the output), `type = "layers"` and the list `layers`, ordered from outermost (`tenant_web.interfaces`, the web and start-up code) through `infrastructure` (settings, logging, Redis) and `application` (the use cases) to `domain` (the pure rules). Imports may only point downward. The second contract has `type = "forbidden"`: `source_modules` are the domain and application packages; `forbidden_modules` are `psycopg`, `psycopg_pool` and `flask`. Neither of the inner layers may import them, directly or through another module.


## 6. Try it yourself

```bash
.venv/bin/lint-imports
```

Prints the two contracts with `KEPT` and `Contracts: 2 kept, 0 broken.`

```bash
echo "import psycopg" >> src/tenant_web/domain/values.py && .venv/bin/lint-imports; git checkout src/tenant_web/domain/values.py
```

The second contract reports `BROKEN` and shows the import chain; the `git checkout` undoes the experiment.

## 7. Mistakes people make

- **Forgetting indirect imports.** A forbidden import through a middle module still counts; the tool reports the whole chain.
- **Listing layers in the wrong order.** The list goes from outermost to innermost.
- **Leaving `include_external_packages` off** and wondering why a rule about `psycopg` never fires.

## 8. Check yourself

1. Which layer may import which? *Each layer may import only the ones below it in the list.*
2. Why can the domain not import `psycopg`? *The second contract forbids it for the domain and application packages.*
3. Is a chain `application -> infrastructure -> psycopg` caught? *Yes, forbidden contracts check indirect imports.*
4. What command runs the check? *`lint-imports`, via `make lint`.*
5. What does the root package setting do? *It tells the tool which package to analyse.*

## 9. Further reading

- import-linter documentation: https://import-linter.readthedocs.io/en/stable/
- Contract types: https://import-linter.readthedocs.io/en/stable/contract_types/
- Grimp: https://grimp.readthedocs.io/en/stable/
