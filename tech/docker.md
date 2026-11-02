# Docker (Dockerfile and .dockerignore)

## 1. What it is

A **container** is a way to run a program in a box: the program sees its own file system, its own process list and its own network, although it shares the computer's operating-system core (the **kernel**) with everything else. An **image** is the frozen, read-only content of that box's file system plus a note saying which command to run. **Docker** is the tool that builds images and runs containers. A **Dockerfile** is the text recipe for building an image: one instruction per line, run from the top. A **`.dockerignore`** file lists paths that must not be sent to the builder at all.

## 2. Why this repository uses it

Kubernetes runs containers, so the web service has to be an image first. The image is also where several of the lesson's safety decisions live: the process runs as a user who is not the administrator, the image contains only what the app needs, and the base image is pinned by a content hash. Its name carries the approved registry's prefix so the admission policy accepts it.

## 3. Where it appears

| File | Role |
| --- | --- |
| `Dockerfile` | The recipe. |
| `.dockerignore` | What the builder must not see. |
| `.env.example` | The settings the service and the scripts read. |
| `scripts/build-images.sh` | Runs `docker build`, retags and imports the images (see `bash.md`). |
| `.github/workflows/ci.yml` | Lints the Dockerfile with hadolint (see `github-actions.md`). |

## 4. How it works underneath

An image is made of **layers**. Each `RUN`, `COPY` and `ADD` instruction produces a layer: the set of file changes it made. Layers are cached; if an instruction and everything before it are unchanged, Docker reuses the stored layer instead of running it again. That is why the Dockerfile copies `requirements.lock` and installs from it *before* copying the source code: the slow install step is reused when only the source changed.

A **multi-stage build** has several `FROM` lines. Each starts a fresh stage. A later stage can copy files out of an earlier one with `COPY --from=<stage>`, and everything else in the earlier stage is thrown away. The first stage (named `builder`) needs tools to install packages; the final stage (`runtime`) receives only the finished virtual environment.

`FROM image@sha256:...` names a base image by the **digest**, the SHA-256 hash of its manifest. A tag such as `3.13-slim-bookworm` can be moved to a different image later; a digest cannot.

When a container starts, Docker applies the image's `ENV` values, switches to the `USER`, changes into the `WORKDIR` and runs the `CMD` (or `ENTRYPOINT`). The `CMD` written as a JSON list (the **exec form**) starts the program directly as process number 1, so the program receives signals such as `SIGTERM` itself. The text form (`CMD gunicorn ...`) would start a shell first, and the shell would swallow the signal.

Docker sends the build **context** (the folder you build from) to the builder before it reads the Dockerfile. `.dockerignore` shrinks that context and keeps files such as `.git` or a local `.venv` out of the image.

## 5. Walkthrough of this repository's use

### `.dockerignore`

```text
.venv
.bin
.kube
.git
.github
.pytest_cache
.mypy_cache
.ruff_cache
.coverage
.kubeconform-cache
tests
manifests
cluster
scripts
docs
**/__pycache__
*.egg-info
```

One pattern per line; each is a path the builder does not receive. `.venv` is the developer's virtual environment; `.bin` the downloaded tools; `.kube` the generated cluster configuration (it holds credentials); `.git` and `.github` the history and CI files; `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.coverage` and `.kubeconform-cache` are caches that tools leave behind. `tests`, `manifests`, `cluster`, `scripts` and `docs` are not needed at run time. `**/__pycache__` matches Python's cache folders at any depth and `*.egg-info` the packaging metadata folders. Besides keeping the image small, this means the `.kube` credentials can never be copied into an image by accident.

### `Dockerfile`

```dockerfile
# The tenant web service as an image: a multi-stage build, so the final image holds the virtual environment
# and nothing else (no pip, no compiler, no build cache), runs as a non-root user and ignores the source tree.
#
#   docker build -t registry.example.test/platform/tenant-web:0.1.0 .

FROM python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530 AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps .
```

The comments state the purpose (a multi-stage build whose final image holds the virtual environment and nothing else, runs as non-root and ignores the source tree) and the build command with the approved name. `FROM python:3.13-slim-bookworm@sha256:... AS builder` starts the first stage from the slim Debian 12 image of Python 3.13, pinned by digest and named `builder`. `ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1` (a backslash continues the line) tells pip not to keep downloads and not to check for a newer pip. `WORKDIR /build` sets the working folder. `RUN python -m venv /opt/venv` creates a virtual environment, and `ENV PATH="/opt/venv/bin:${PATH}"` puts it first on the command search path. `COPY requirements.lock ./` then `RUN pip install --require-hashes -r requirements.lock` installs exactly the pinned packages, refusing any whose hash is not listed. `COPY pyproject.toml README.md ./` and `COPY src ./src` bring in the project; `RUN pip install --no-deps .` installs it without looking for dependencies (the lock already installed them).

```dockerfile
FROM python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"
COPY --from=builder /opt/venv /opt/venv
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
# No --preload: the connection pool starts threads, and threads do not survive gunicorn's fork. /tmp is the
# only writable path (an emptyDir in the cluster); gunicorn keeps its worker heartbeat files there.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--worker-class", "gthread", \
     "--worker-tmp-dir", "/tmp", "--graceful-timeout", "10", "--access-logfile", "-", \
     "tenant_web.interfaces.wsgi:build_app()"]
```

The second stage, `runtime`, starts again from the same pinned base. `ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=...` stops Python writing `.pyc` files (the file system is read-only in the cluster), makes output immediate and puts the virtual environment on the path. `COPY --from=builder /opt/venv /opt/venv` copies the finished environment out of the first stage. `RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app` creates a user with the fixed number 10001 (Kubernetes checks `runAsNonRoot` by number); `USER 10001:10001` runs everything after as that user and group. `EXPOSE 8080` documents the port. `HEALTHCHECK` tells plain Docker to fetch `/healthz` every 30 seconds with a 2-second timeout and mark the container unhealthy after three failures (Kubernetes ignores it and uses its own probes). The comment explains the absence of `--preload`: the connection pool starts threads, and threads do not survive gunicorn's fork; `/tmp` is the only writable path (an `emptyDir` in the cluster) and gunicorn keeps its worker heartbeat files there. The `CMD` list starts gunicorn: bind `0.0.0.0:8080`, one worker, four threads, the `gthread` worker class, heartbeat folder `/tmp`, a 10-second graceful timeout, access log to standard output, and the factory `tenant_web.interfaces.wsgi:build_app()` (every option is explained in `gunicorn.md`).

### `.env.example`

```text
# Variables the service and the scripts read. Export one in your shell to override it; every value shown is
# the default except the secrets, which are never written down: the database password is generated into a
# Kubernetes Secret by scripts/create-secrets.sh.

# The web service (set in manifests/base/web.yaml; DB_PASSWORD comes from the Secret db-credentials).
TEAM_NAME=team-a
DB_HOST=db
DB_PORT=5432
DB_NAME=app
DB_USER=app
DB_TIMEOUT_SECONDS=3
DB_POOL_SIZE=4
# DEBUG, INFO, WARNING or ERROR.
LOG_LEVEL=INFO

# The scripts.
CLUSTER_NAME=harden
REGISTRY=registry.example.test/platform
ENGINEER=alice
```

A template of the settings the project reads (see `environment.md`). `TEAM_NAME=team-a` names the team (and the namespace); `DB_HOST=db` is the Service name of the database; `DB_PORT=5432`, `DB_NAME=app`, `DB_USER=app` are the Postgres connection details; `DB_TIMEOUT_SECONDS=3` bounds how long a connection may take; `DB_POOL_SIZE=4` is the number of pooled connections; `LOG_LEVEL=INFO` chooses how chatty the log is. There is no password line: the comment at the top says it is generated into a Secret by `scripts/create-secrets.sh`. The last block is for the scripts: `CLUSTER_NAME=harden`, `REGISTRY=registry.example.test/platform` (the approved registry's name) and `ENGINEER=alice` (the person the attacks impersonate).


## 6. Try it yourself

```bash
make docker-build
docker image ls registry.example.test/platform/tenant-web
docker run --rm registry.example.test/platform/tenant-web:0.1.0 python -c "import os; print(os.getuid())"
```

The build ends with `naming to registry.example.test/platform/tenant-web:0.1.0`; the second command lists the image (about 190 MB with the database driver); the third prints `10001`, proof that the process is not root.

```bash
docker run --rm registry.example.test/platform/tenant-web:0.1.0 sh -c "ls /build 2>&1; ls /opt/venv/bin | head -3"
```

`ls /build` reports `No such file or directory`: the build stage was left behind.

```bash
docker history registry.example.test/platform/tenant-web:0.1.0 | head -8
```

Lists each layer with the instruction that made it and its size.

```bash
docker run --rm -e TEAM_NAME=BAD -e DB_PASSWORD=x registry.example.test/platform/tenant-web:0.1.0; echo "exit $?"
```

Prints the JSON line `FATAL invalid configuration: TEAM_NAME: ...` and `exit 1`.

## 7. Mistakes people make

- **Using a moving tag.** `python:latest` changes under you. This file pins a digest.
- **Running as root.** A process with user id 0 can do far more damage if it is taken over. Here `USER 10001:10001`.
- **Copying everything first.** `COPY . .` before the install invalidates the cache on every source edit.
- **Leaving build tools in the final image.** A compiler and `pip` help an attacker; the multi-stage build drops them.
- **The shell form of `CMD`.** Signals do not reach the app, so shutdown becomes a hard kill after the timeout.
- **Forgetting `.dockerignore`.** The `.git` folder or secrets in the working directory end up inside the image.

## 8. Check yourself

1. Why are there two `FROM` lines? *Two stages: build with tools, then ship only the result.*
2. Why does `requirements.lock` get copied before `src`? *So the install layer stays cached when only code changes.*
3. What does `--require-hashes` guarantee? *pip refuses any package whose file hash is not listed in the lock file.*
4. What does `USER 10001:10001` change? *The process runs as an ordinary numeric user and group, not root.*
5. Why does this image's `CMD` have no `--preload`? *The connection pool starts threads, and threads do not survive gunicorn's fork.*

## 9. Further reading

- Dockerfile reference: https://docs.docker.com/reference/dockerfile/
- Multi-stage builds: https://docs.docker.com/build/building/multi-stage/
- Build cache: https://docs.docker.com/build/cache/
- `.dockerignore`: https://docs.docker.com/build/concepts/context/#dockerignore-files
- Best practices: https://docs.docker.com/build/building/best-practices/
