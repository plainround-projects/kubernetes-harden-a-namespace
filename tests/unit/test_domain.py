import pytest

from tenant_web.domain.errors import InvalidCountError, InvalidTeamNameError
from tenant_web.domain.values import TeamName, VisitCount


@pytest.mark.parametrize("name", ["team-a", "a", "team-42", "x" * 63])
def test_a_dns_label_is_a_valid_team_name(name):
    assert TeamName(name).value == name


@pytest.mark.parametrize("name", ["", "Team-A", "team_a", "-team", "team-", "x" * 64, "team a", "team.a"])
def test_anything_else_is_rejected(name):
    with pytest.raises(InvalidTeamNameError):
        TeamName(name)


def test_a_visit_count_keeps_its_value():
    assert VisitCount(3).value == 3


@pytest.mark.parametrize("bad", [0, -1, 1.5, "2", None, True])
def test_a_visit_count_must_be_a_positive_integer(bad):
    with pytest.raises(InvalidCountError):
        VisitCount(bad)


def test_values_are_immutable():
    with pytest.raises(AttributeError):
        TeamName("team-a").value = "other"  # type: ignore[misc]
