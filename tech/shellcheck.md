# shellcheck

## 1. What it is

shellcheck is a **static analyser** for shell scripts: a program that reads a script without running it and warns about mistakes that Bash itself would accept silently, such as an unquoted variable, a command that cannot work as written, or a variable that is set and never used. Each warning has a code (`SC2086`) with an explanation online. This repository uses the pip package `shellcheck-py`, which carries a copy of the real shellcheck program.

## 2. Why this repository uses it

Shell scripts fail in surprising ways (the unquoted-variable `rm` is the classic). With twelve scripts that start and delete clusters, an automatic reader that never gets tired is cheap insurance, and `make lint` runs it on every change.

## 3. Where it appears

| File | Role |
| --- | --- |
| `Makefile` | Target `lint` runs `shellcheck -x scripts/*.sh`. |
| `.shellcheckrc` | Its settings. |
| `pyproject.toml` | Lists `shellcheck-py` among the dev dependencies. |
| `scripts/*.sh`, `attacks/*.sh` | Carry `# shellcheck source=lib.sh` and `# shellcheck shell=bash` hints. |

## 4. How it works underneath

shellcheck parses the script into a syntax tree, as Bash would, and then applies hundreds of checks to the tree. It never runs the script. Because `source` pulls in another file, it needs to know where that file is: the `-x` flag allows it to follow `source` lines, and `source-path=SCRIPTDIR` in the settings says "look in the folder of the script being checked". A comment `# shellcheck source=lib.sh` on the line above a `source` tells it the exact file.

## 5. Walkthrough of this repository's use

### `.shellcheckrc`

```text
external-sources=true
source-path=SCRIPTDIR
```

A two-line settings file in which each line is a `key=value`. `external-sources=true` has the same effect as passing `-x` on the command line: follow `source` statements. `source-path=SCRIPTDIR` adds the folder of the script under check to the places shellcheck looks for the files named in those statements.


## 6. Try it yourself

```bash
.venv/bin/shellcheck -x scripts/*.sh attacks/*.sh && echo clean
```

No output but `clean`.

```bash
printf '#!/usr/bin/env bash\nrm -rf $1/tmp\n' > /tmp/x.sh && .venv/bin/shellcheck /tmp/x.sh
```

Reports `SC2086: Double quote to prevent globbing and word splitting` on line 2.

```bash
.venv/bin/shellcheck --version | head -2
```

Shows the version and license of the bundled program.

## 7. Mistakes people make

- **Silencing a warning without reading it.** Each code explains a real failure.
- **Not telling it where sourced files are**, which hides every variable defined there.
- **Believing a clean result means the script is right.** It finds common mistakes, not logic errors.

## 8. Check yourself

1. Does shellcheck run the script? *No, it only reads it.*
2. What does `-x` allow? *Following `source` lines into other files.*
3. What does `source-path=SCRIPTDIR` mean? *Search for sourced files next to the script being checked.*
4. What does `# shellcheck shell=bash` do in `lib.sh`? *Declares the dialect, since the file has no run-time use of its shebang.*
5. Which command runs it for the whole project? *`make lint`.*

## 9. Further reading

- shellcheck home and wiki (every warning code): https://www.shellcheck.net/wiki/
- Project repository and manual: https://github.com/koalaman/shellcheck
- `shellcheck-py` on PyPI: https://pypi.org/project/shellcheck-py/
