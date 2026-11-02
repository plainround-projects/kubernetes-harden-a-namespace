# hadolint

## 1. What it is

hadolint is a linter for Dockerfiles (`docker.md`). It reads the recipe and warns about practices that make images bigger, less safe or less repeatable: unpinned base images, `apt-get install` without cleanup, running as root, shell-form `CMD`. Each warning has a code such as `DL3008`. It also runs the shellcheck rules on the shell commands inside `RUN` lines.

## 2. Why this repository uses it

The Dockerfile carries safety decisions (digest-pinned base, non-root user, exec-form `CMD`); an automatic reader keeps them from regressing. It runs as a throwaway container, so nothing must be installed: `docker run --rm -i hadolint/hadolint:v2.12.0 < Dockerfile`.

## 3. Where it appears

| File | Role |
| --- | --- |
| `Makefile` | Target `lint` runs the command above. |
| `.github/workflows/ci.yml` | The `check` job runs `make lint`. |
| `Dockerfile` | The checked file. |

## 4. How it works underneath

`docker run --rm -i image` starts a temporary container (`--rm` deletes it afterwards) and keeps its standard input open (`-i`). The shell operator `< Dockerfile` feeds the file to hadolint through that input. hadolint parses the instructions, applies its rules and prints findings with line numbers; a non-zero exit status fails `make lint`. The image tag `v2.12.0` pins the tool version.

## 5. Walkthrough of this repository's use



## 6. Try it yourself

```bash
docker run --rm -i hadolint/hadolint:v2.12.0 < Dockerfile && echo clean
```

Prints `clean` only (no findings).

```bash
printf 'FROM python:latest\nRUN pip install flask\n' | docker run --rm -i hadolint/hadolint:v2.12.0
```

Reports unpinned tags (`DL3007` or similar) and the unpinned pip package (`DL3013`).

## 7. Mistakes people make

- **Ignoring a rule with `# hadolint ignore=` without a reason.** None are used here.
- **Reading a clean result as "the image is secure".** It checks the recipe, not the packages inside.

## 8. Check yourself

1. Why does the command use `< Dockerfile`? *hadolint reads the recipe from standard input.*
2. What does `--rm` do? *Removes the container after it exits.*
3. Is anything installed on the machine for this? *No, only the container image is pulled.*
4. What does a finding look like? *A line number, a code like `DL3008` and a message.*
5. Which target runs it? *`make lint`.*

## 9. Further reading

- hadolint repository and rule list: https://github.com/hadolint/hadolint
- Dockerfile best practices: https://docs.docker.com/build/building/best-practices/
