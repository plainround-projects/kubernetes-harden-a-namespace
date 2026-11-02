# YAML and yamllint

## 1. What it is

YAML is a text format for writing structured data: names with values, lists, and groups nested inside groups. It is meant to be easy for people to read. Almost every Kubernetes object, the cluster configuration and the CI workflow in this repository are YAML files (extension `.yaml` or `.yml`). **yamllint** is a small program that reads YAML files and reports style mistakes (wrong indentation, lines too long, duplicate keys) so the files stay consistent.

The building blocks:

- A **mapping** is a set of `key: value` pairs. The key and value are separated by a colon and a space.
- Nesting is written with **indentation using spaces** (never tabs). Everything indented under a key belongs to it.
- A **list** item starts with `- ` (dash and space). A list of mappings starts each mapping with a dash.
- A **scalar** is a single value: text, a number, `true`/`false`, `null`. Quotes are optional for text but needed when YAML would otherwise guess wrong (`"100"` stays text; `100` is a number).
- `#` starts a comment that runs to the end of the line.
- `---` on a line by itself separates several documents in one file (Kubernetes uses this to put a Deployment and a Service in one file).
- `|` after a key starts a **block of literal text** on the following indented lines, kept line by line (the patches in the overlays use `|-`, which also drops the final newline).
- Short forms: `["a", "b"]` is a list written on one line, `{ key: value }` a mapping on one line.

## 2. Why this repository uses it

Kubernetes and k3d read their configuration from YAML; there is no other way to give them objects. yamllint keeps 20-odd files consistent and catches mistakes such as a stray tab that would otherwise show up only when the cluster refuses the file.

## 3. Where it appears

| File | Role |
| --- | --- |
| `manifests/**/*.yaml` | Kubernetes objects (see `kubernetes.md`, `kustomize.md`). |
| `cluster/k3d-config.yaml` | The cluster description (see `k3d.md`). |
| `.github/workflows/ci.yml` | The CI pipeline (see `github-actions.md`). |
| `.yamllint.yaml` | yamllint's own settings. |
| `Makefile` target `lint` | Runs `yamllint -s .`. |

## 4. How it works underneath

A YAML parser reads the text line by line and builds a tree of mappings, lists and scalars from the indentation. The same tree could be written as JSON; YAML is a superset that is nicer to write by hand. Because meaning depends on indentation, one wrong space changes the structure silently: an item that moves one level out is no longer inside its parent.

Type guessing is the classic trap. Unquoted `yes`, `no`, `on` and `off` were once read as booleans, which is why yamllint has a `truthy` rule. A value such as `1.35` is a number, not text; quote it when text is required.

yamllint applies a list of **rules** to each file, each rule can be `enable`d with options, set to warning or error, or disabled. The `-s` (strict) flag makes warnings fail the run. `extends: default` starts from yamllint's default rule set.

## 5. Walkthrough of this repository's use

### `.yamllint.yaml`

```yaml
extends: default
ignore: |
  .venv/
  .bin/
  .kube/
rules:
  line-length:
    max: 140
  document-start: disable
  truthy:
    check-keys: false
  comments:
    min-spaces-from-content: 1
  braces:
    max-spaces-inside: 1
```

`extends: default` starts from the default rules. `ignore: |` begins a literal block of path patterns yamllint must skip: `.venv/` (installed packages), `.bin/` (downloaded tools) and `.kube/` (generated credentials and the throwaway stage files). `rules:` then changes five rules. `line-length` with `max: 140` allows lines up to 140 characters (the default is 80, too short for the long comments and probe commands). `document-start: disable` turns off the rule that demands `---` at the top of every file. `truthy` with `check-keys: false` still warns about values like `yes` but ignores keys (the CI file has a key named `on`, which older YAML reads as a boolean). `comments` with `min-spaces-from-content: 1` requires at least one space between code and a trailing `#` comment. `braces` with `max-spaces-inside: 1` allows one space inside `{ }`, which the attack manifests use for the short form `{ cpu: 10m, memory: 16Mi }`.


## 6. Try it yourself

```bash
.venv/bin/yamllint -s .
```

Prints nothing and exits with status 0 when every file passes.

```bash
printf 'a:\n\t- b\n' > /tmp/bad.yaml && .venv/bin/yamllint /tmp/bad.yaml
```

Reports an error about the tab (`found character '\t' that cannot start any token` or a syntax error line).

```bash
.venv/bin/python -c "import yaml,sys; print(yaml.safe_load(open('manifests/base/serviceaccounts.yaml')))"
```

Prints the first object as a Python dictionary (`safe_load` reads one document; use `safe_load_all` for several).

## 7. Mistakes people make

- **Tabs for indentation.** Not allowed; use spaces.
- **Unquoted values that look like numbers or booleans.** Quote them when text is meant (`"100"`).
- **Inconsistent indentation inside a list.** Moves items to the wrong parent.
- **Putting a colon in an unquoted value** (`image: a:b` is fine, `title: a: b` is not).
- **Assuming `---` is needed on the first line.** Here the `document-start` rule is disabled.

## 8. Check yourself

1. What separates two objects in one file? *A line containing `---`.*
2. What does `|-` after a key do? *Starts literal multi-line text and removes the final newline.*
3. Why is `value: "100"` written with quotes in the unschedulable overlay? *So it is text, not a number.*
4. What does `extends: default` do? *Starts from yamllint's default rules before the file's own changes.*
5. What does `yamllint -s` change? *Warnings become errors.*

## 9. Further reading

- YAML 1.2 specification: https://yaml.org/spec/1.2.2/
- yamllint documentation: https://yamllint.readthedocs.io/en/stable/
- yamllint rules: https://yamllint.readthedocs.io/en/stable/rules.html
- PyYAML: https://pyyaml.org/wiki/PyYAMLDocumentation
