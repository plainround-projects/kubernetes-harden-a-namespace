"""The service's three questions: count a visit, are you ready, are you alive."""

from __future__ import annotations

from dataclasses import dataclass

from tenant_web.application.ports import VisitStore
from tenant_web.domain.errors import StoreUnavailableError
from tenant_web.domain.values import TeamName, VisitCount


@dataclass(frozen=True, slots=True)
class VisitReceipt:
    """What a visit returns: whose service answered and the page's new total."""

    team: TeamName
    count: VisitCount


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """The answer to "should the Service send me traffic right now?"."""

    ready: bool
    reason: str


class RecordVisit:
    """Count one visit to a page for this team's service."""

    def __init__(self, team: TeamName, store: VisitStore) -> None:
        """Bind the team and its store."""
        self._team = team
        self._store = store

    def __call__(self, page: str = "/") -> VisitReceipt:
        """Count the visit and return the receipt."""
        return VisitReceipt(self._team, VisitCount(self._store.record_visit(page)))


class CheckReadiness:
    """Ready means the database answers right now."""

    def __init__(self, store: VisitStore) -> None:
        """Bind the store."""
        self._store = store

    def __call__(self) -> ReadinessReport:
        """Ask the store; never raise, because a failing database is a normal answer here."""
        try:
            self._store.ping()
        except StoreUnavailableError as error:
            return ReadinessReport(ready=False, reason=str(error))
        return ReadinessReport(ready=True, reason="database reachable")
