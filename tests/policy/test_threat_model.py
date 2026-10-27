"""The threat model and the attacks folder agree: every attack has exactly one primary control, and the gap is named."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.policy

ROOT = Path(__file__).resolve().parents[2]
MODEL = (ROOT / "docs" / "threat-model.md").read_text()
ATTACK_FILES = sorted(path.name for path in (ROOT / "attacks").iterdir() if re.match(r"0\d", path.name))
CONTROLS = ("Pod Security", "RBAC", "NetworkPolicy", "ResourceQuota", "ValidatingAdmissionPolicy")


def _table_rows() -> list[tuple[str, str]]:
    rows = []
    for line in MODEL.splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if line.startswith("| `") and len(cells) >= 3:
            rows.append((cells[0], cells[2]))
    return rows


def test_every_attack_file_appears_in_exactly_one_row():
    rows = _table_rows()
    for name in ATTACK_FILES:
        assert sum(name in attacks for attacks, _ in rows) == 1, name


def test_every_row_names_exactly_one_primary_control():
    for attacks, control in _table_rows():
        assert sum(known in control for known in CONTROLS) == 1, (attacks, control)


def test_every_attack_in_the_table_exists_as_a_file():
    for attacks, _ in _table_rows():
        for name in re.findall(r"`([^`]+)`", attacks):
            assert (ROOT / "attacks" / name).exists(), name


def test_the_model_lists_what_teams_must_do_and_must_never_do_and_names_the_gap():
    for heading in (
        "## What each team must be able to do",
        "## What each team must never do",
        "## Not stopped by any of these",
    ):
        assert heading in MODEL
    assert "remote-code-execution" in MODEL
