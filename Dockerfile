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
