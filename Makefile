# make up | run | smoke | down      (make help lists everything)
PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3)
VENV := .venv
PY := $(VENV)/bin/python
STAMP := $(VENV)/.installed
K8S_VERSION := 1.35.0
OVERLAYS := baseline hardened
CONTROLS := pod-security rbac network-policy quota admission-policy

# The project's own kubeconfig and the pinned tools in .bin: nothing here touches ~/.kube or the system.
export KUBECONFIG := $(CURDIR)/.kube/config
export PATH := $(CURDIR)/.bin:$(PATH)

.PHONY: help install tools up images baseline harden run prove-controls db db-queries lint format conform test \
        test-integration smoke audit check docker-build down clean

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | sort

$(STAMP): requirements-dev.lock pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes -r requirements-dev.lock
	$(VENV)/bin/pip install -q --no-deps -e .
	touch $@

install: $(STAMP) ## create .venv from the lock file

tools: ## download the pinned k3d and kubeconform into .bin (checksum-verified)
	scripts/tools.sh

up: tools ## create the k3d cluster, build and import the images, deploy both teams hardened
	scripts/cluster-start.sh
	scripts/build-images.sh
	scripts/stage.sh hardened

images: ## rebuild the images and load them into the cluster
	scripts/build-images.sh

baseline: ## put both teams in the careless baseline: no control, so every attack succeeds
	scripts/stage.sh baseline

harden: ## put both teams in the hardened stage: every control on
	scripts/stage.sh hardened

run: ## run every attack as a developer of team A; each must print BLOCKED when hardened
	scripts/run-attacks.sh

prove-controls: ## switch each control off in turn and show that its attack, and only its attack, succeeds
	@for control in $(CONTROLS); do \
	  echo "######## without $$control"; \
	  scripts/stage.sh without $$control; \
	  scripts/run-attacks.sh || true; \
	done
	scripts/stage.sh hardened

db: ## run sql/001 and sql/002 against team A's database (both idempotent): make db TEAM=team-b for the other
	scripts/db.sh $(or $(TEAM),team-a)

db-queries: ## run the statements the service runs (sql/003_queries.sql) against team A's database
	scripts/db.sh $(or $(TEAM),team-a) queries

lint: $(STAMP) conform ## ruff, format check, mypy, import rules, yamllint, shellcheck, hadolint, kubeconform
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .
	$(VENV)/bin/mypy
	$(VENV)/bin/lint-imports
	$(VENV)/bin/yamllint -s .
	$(VENV)/bin/shellcheck -x scripts/*.sh attacks/*.sh
	docker run --rm -i hadolint/hadolint:v2.12.0 < Dockerfile

conform: tools ## validate both rendered overlays against the Kubernetes 1.35 schemas with kubeconform
	@mkdir -p .kubeconform-cache
	@for overlay in $(OVERLAYS); do \
	  echo "kubeconform manifests/overlays/$$overlay"; \
	  kubectl kustomize --load-restrictor=LoadRestrictionsNone manifests/overlays/$$overlay | .bin/kubeconform -strict -summary -kubernetes-version $(K8S_VERSION) -cache .kubeconform-cache || exit 1; \
	done

format: $(STAMP) ## apply ruff's formatting and safe fixes
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/ruff format .

# Unit tests and the manifest policy checks need no cluster and no Docker. The domain and application stay at 95% or more.
test: $(STAMP) ## unit tests with coverage and the manifest and threat-model policy checks (no cluster needed)
	$(PY) -m pytest tests/unit tests/policy --cov=tenant_web --cov-report=term
	$(PY) -m coverage report --include='src/tenant_web/domain/*,src/tenant_web/application/*' --fail-under=95

test-integration: $(STAMP) ## the Postgres adapter, the SQL scripts and the real gunicorn command against a Postgres container
	$(PY) -m pytest tests/integration -m integration

smoke: $(STAMP) ## every Done when line on the cluster, baseline to hardened to one-control-off (make up first)
	$(PY) -m pytest tests/e2e -m e2e -s -v

audit: $(STAMP) ## check the locked dependencies for known vulnerabilities
	$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock

check: lint test ## lint plus unit and policy tests

docker-build: ## build the web image without loading it anywhere
	docker build -t registry.example.test/platform/tenant-web:0.1.0 .

down: ## delete the k3d cluster and its kubeconfig
	scripts/cluster-down.sh

clean: down
	rm -rf $(VENV) .bin .pytest_cache .mypy_cache .ruff_cache .coverage .kubeconform-cache
