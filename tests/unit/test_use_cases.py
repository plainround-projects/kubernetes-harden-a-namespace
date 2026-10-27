import pytest

from tenant_web.application.use_cases import CheckReadiness, RecordVisit
from tenant_web.domain.errors import StoreUnavailableError
from tenant_web.domain.values import TeamName
from tests.unit.conftest import FakeStore


def test_a_visit_returns_the_team_and_the_next_total(store):
    record = RecordVisit(TeamName("team-a"), store)
    receipts = [record() for _ in range(3)]
    assert [receipt.count.value for receipt in receipts] == [1, 2, 3]
    assert receipts[0].team == TeamName("team-a")


def test_each_page_has_its_own_total(store):
    record = RecordVisit(TeamName("team-a"), store)
    record("/")
    record("/")
    assert record("/other").count.value == 1


def test_a_store_failure_passes_through(store):
    store.down = True
    with pytest.raises(StoreUnavailableError):
        RecordVisit(TeamName("team-a"), store)()


def test_ready_when_the_database_answers(store):
    assert CheckReadiness(store)().ready is True


def test_not_ready_when_the_database_is_down_and_the_reason_is_kept():
    report = CheckReadiness(FakeStore(down=True))()
    assert report.ready is False
    assert "down" in report.reason
