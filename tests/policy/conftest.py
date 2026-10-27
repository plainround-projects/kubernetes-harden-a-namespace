"""Render the Kustomize overlays once per session so the policy tests read plain dictionaries."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
Doc = dict[str, Any]


def render(overlay: str) -> list[Doc]:
    """kubectl kustomize manifests/overlays/<overlay>, parsed into one dictionary per resource."""
    output = subprocess.run(
        [
            "kubectl",
            "kustomize",
            "--load-restrictor=LoadRestrictionsNone",
            str(ROOT / "manifests" / "overlays" / overlay),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [doc for doc in yaml.safe_load_all(output) if doc]


def select(docs: list[Doc], kind: str, namespace: str | None = None, name: str | None = None) -> list[Doc]:
    """The resources of a kind, optionally in one namespace and with one name."""
    return [
        doc
        for doc in docs
        if doc["kind"] == kind
        and (namespace is None or doc["metadata"].get("namespace") == namespace)
        and (name is None or doc["metadata"]["name"] == name)
    ]


@pytest.fixture(scope="session")
def hardened() -> list[Doc]:
    return render("hardened")


@pytest.fixture(scope="session")
def baseline() -> list[Doc]:
    return render("baseline")
