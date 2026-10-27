"""Shared fakes for the unit tests: an in-memory visit store that can be told to fail."""

from __future__ import annotations

import pytest

from tenant_web.domain.errors import StoreUnavailableError


class FakeStore:
    """Implements the VisitStore port in memory."""

    def __init__(self, *, down: bool = False) -> None:
        self.down = down
        self.pages: dict[str, int] = {}

    def record_visit(self, page: str) -> int:
        if self.down:
            raise StoreUnavailableError("fake store is down")
        self.pages[page] = self.pages.get(page, 0) + 1
        return self.pages[page]

    def ping(self) -> None:
        if self.down:
            raise StoreUnavailableError("fake store is down")


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()
