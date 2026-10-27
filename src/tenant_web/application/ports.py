"""What the use cases need from the outside world."""

from __future__ import annotations

from typing import Protocol


class VisitStore(Protocol):
    """Where visit counts live."""

    def record_visit(self, page: str) -> int:
        """Add one visit to a page and return its new total. Raises StoreUnavailableError when the store is down."""
        ...

    def ping(self) -> None:
        """Return when the store answers. Raises StoreUnavailableError when it does not."""
        ...
