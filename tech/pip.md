# pip, virtual environments and the lock files (uv)

## 1. What it is

**pip** is Python's package installer: `pip install flask` downloads the Flask library from the Python Package Index (PyPI, the public shop of Python libraries) and unpacks it. A **virtual environment** (made by `python -m venv`) is a private folder of installed libraries, so this project's versions never mix with other projects'. A **lock file** lists the exact version of every library, including the libraries those libraries need, together with a cryptographic **hash** (a fingerprint) of each downloadable file. `requirements.lock` (runtime) and `requirements-dev.lock` (runtime plus tools) are lock files made by **uv**, a very fast Python package tool, with the command written in the first lines of each file: `uv pip compile pyproject.toml --generate-hashes --python-version 3.13 --universal`.

## 2. Why this repository uses it

A range like `flask>=3.1,<4` means two installs a month apart can give different code. A lock file removes that: every install, on a laptop, in CI and in the Docker build, uses the same bytes. The hashes also mean a tampered or substituted package is rejected before it can run. `pip-audit` reads the same file to check each pinned version against a database of known vulnerabilities.

## 3. Where it appears

| File | Role |
| --- | --- |
| `requirements.lock` | Runtime packages; used by the `Dockerfile`. |
| `requirements-dev.lock` | Runtime plus test and lint tools; used by `make install`. |
| `pyproject.toml` | The human-written ranges the locks are compiled from (see `toml.md`). |
| `Makefile` | Target `install` builds `.venv`; target `audit` runs `pip-audit`. |
| `Dockerfile` | `pip install --require-hashes -r requirements.lock`. |

## 4. How it works underneath

`pip install --require-hashes -r file` reads each line of the lock file (`name==version` followed by one or more `--hash=sha256:...` lines). It downloads the package files, computes their SHA-256 hash, and installs only if it matches one of the listed hashes; in this mode pip also refuses any package that is not listed, so no hidden dependency can slip in. `# via flask` comments record why a package is present. `--no-deps` stops pip from looking for more dependencies (the lock already holds them all). `-e .` (editable) installs the project as a link to the source folder. `--universal` makes the lock valid for every operating system, which is why it contains conditional markers for packages that only some systems need.

## 5. Walkthrough of this repository's use

The lock files are machine-generated and not edited by hand; every command that uses them is explained in `docker.md` (build), `make.md` (install, audit) and `toml.md` (ranges).



## 6. Try it yourself

```bash
head -8 requirements.lock
```

Shows the generating command and the first pinned packages with their hashes.

```bash
.venv/bin/pip list | head
```

Lists installed packages and versions; they match the lock.

```bash
make audit
```

Prints `No known vulnerabilities found` (needs internet) for the locked set.

```bash
.venv/bin/pip install --require-hashes --dry-run flask==3.1.3
```

Refuses: with `--require-hashes` every requirement must have a hash, so installing by name alone fails.

## 7. Mistakes people make

- **Installing into the system Python.** Use the virtual environment.
- **Editing the lock file by hand.** Change `pyproject.toml` and recompile.
- **Compiling the lock on one Python version and installing on another.** The lock names the version it was compiled for.
- **Committing `.venv`.** It is in `.gitignore`.

## 8. Check yourself

1. What is the difference between `pyproject.toml` and the lock file? *The first has ranges written by a person; the second has exact versions and hashes made by a tool.*
2. What does `--require-hashes` guarantee? *Every installed file matches a fingerprint listed in the lock.*
3. Why is the Docker build's install command `--no-deps` for the project itself? *The lock already installed all dependencies.*
4. What does `# via flask` mean? *That package is present because Flask needs it.*
5. What does `make audit` check? *Known vulnerabilities in the pinned versions.*

## 9. Further reading

- pip documentation: https://pip.pypa.io/en/stable/
- Secure installs and hash-checking mode: https://pip.pypa.io/en/stable/topics/secure-installs/
- venv: https://docs.python.org/3.13/library/venv.html
- uv pip compile: https://docs.astral.sh/uv/pip/compile/
- pip-audit: https://pypi.org/project/pip-audit/
