"""Immutable values: a team's name and a count of visits."""

from __future__ import annotations

import re
from dataclasses import dataclass

from tenant_web.domain.errors import InvalidCountError, InvalidTeamNameError

_DNS_LABEL = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?")


@dataclass(frozen=True, slots=True)
class TeamName:
    """A team's name, which is also its namespace: a lower-case DNS label."""

    value: str

    def __post_init__(self) -> None:
        """Reject anything Kubernetes would not accept as a namespace name."""
        if not _DNS_LABEL.fullmatch(self.value):
            raise InvalidTeamNameError(f"a team name must be a lower-case DNS label, got {self.value!r}")


@dataclass(frozen=True, slots=True)
class VisitCount:
    """How many times a page has been visited. The first visit is 1."""

    value: int

    def __post_init__(self) -> None:
        """Reject anything but a positive integer."""
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 1:
            raise InvalidCountError(f"a visit count must be a positive integer, got {self.value!r}")
