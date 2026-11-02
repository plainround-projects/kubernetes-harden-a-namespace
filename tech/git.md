# Git, .gitignore and .editorconfig

## 1. What it is

**Git** is a version-control tool: it records every change to the project as a **commit** (a labelled snapshot with an author and a message), so history can be read and undone. A **repository** is the project folder plus that history. **`.gitignore`** lists paths git must never record (generated files, caches, local credentials). **`.editorconfig`** is a small settings file that most code editors read, so everyone's editor uses the same indentation and line endings.

## 2. Why this repository uses it

The project is delivered as a repository with a clean history and a clean working tree. `.gitignore` keeps the generated cluster credentials (`.kube/`), downloaded tools (`.bin/`), the virtual environment and caches out of it. `.editorconfig` stops invisible differences (tabs, line endings, trailing spaces) from creating noise.

## 3. Where it appears

| File | Role |
| --- | --- |
| `.gitignore` | Paths not to record. |
| `.editorconfig` | Editor settings. |
| `LICENSE` | The MIT license text. |
| `CHANGELOG.md` | The human-readable history of releases. |

## 4. How it works underneath

git compares the working folder with the last commit and lists differences; a path matching a `.gitignore` pattern is skipped. A pattern ending in `/` matches a folder; `*.pyc` matches by name anywhere; `.coverage` matches a file name. `.editorconfig` has sections named by file patterns (`[*]`, `[*.{yml,yaml,json,toml}]`, `[Makefile]`, `[*.md]`); an editor applies every matching section from top to bottom. `root = true` tells it to stop looking in parent folders.

## 5. Walkthrough of this repository's use



### The two files, line by line

`.gitignore`: `.venv/` the virtual environment; `.bin/` downloaded tools; `.kube/` the generated kubeconfig (credentials); `.kubeconform-cache/` schema cache; `__pycache__/` and `*.pyc` Python's compiled caches; `*.egg-info/` packaging metadata; `build/` and `dist/` build output; `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` tool caches; `.coverage` the coverage data file; `.env` a local environment file (it could hold secrets); `.DS_Store` macOS folder metadata; `logs/` log folders; `.omc/` a tool's working folder.

`.editorconfig`: `root = true` stop searching upward. Under `[*]` (every file): `charset = utf-8` text encoding; `end_of_line = lf` Unix line endings; `insert_final_newline = true` end every file with a newline; `trim_trailing_whitespace = true` remove spaces at line ends; `indent_style = space` and `indent_size = 4` indent with four spaces. `[*.{yml,yaml,json,toml}]` overrides the indent size to 2. `[Makefile]` uses tabs (Make requires them). `[*.md]` keeps trailing spaces, because two spaces at the end of a Markdown line mean a line break.

## 6. Try it yourself

```bash
git status --short
```

Prints nothing when the tree is clean.

```bash
git check-ignore -v .kube/config .bin/k3d
```

Shows which `.gitignore` line ignores each path.

```bash
git log --oneline | head
```

Lists the commits with short messages.

## 7. Mistakes people make

- **Committing credentials.** `.kube/` and `.env` are ignored for exactly this reason.
- **Committing generated files.** They cause conflicts and hide real changes.
- **Using tabs in YAML or Python.** `.editorconfig` prevents it; Makefiles are the one exception.

## 8. Check yourself

1. Why is `.kube/` ignored? *It holds cluster credentials generated on each machine.*
2. Why does the Makefile section use tabs? *Make requires tabs before recipe lines.*
3. What does `git status --short` print on a clean tree? *Nothing.*
4. What does `root = true` mean? *The editor stops searching parent folders for settings.*
5. Why are Markdown trailing spaces kept? *Two trailing spaces force a line break.*

## 9. Further reading

- Pro Git book: https://git-scm.com/book/en/v2
- gitignore patterns: https://git-scm.com/docs/gitignore
- EditorConfig: https://editorconfig.org/
- Choose a license: https://choosealicense.com/licenses/mit/
