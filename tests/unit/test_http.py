import pytest

from tenant_web.application.use_cases import CheckReadiness, RecordVisit
from tenant_web.domain.values import TeamName
from tenant_web.interfaces.http import create_app


def _client(store, alive=True):
    app = create_app(RecordVisit(TeamName("team-a"), store), CheckReadiness(store), lambda: alive)
    return app.test_client()


@pytest.fixture
def client(store):
    return _client(store)


def test_each_visit_increments_and_names_the_team(client):
    answers = [client.get("/").get_json() for _ in range(3)]
    assert [answer["visits"] for answer in answers] == [1, 2, 3]
    assert {answer["team"] for answer in answers} == {"team-a"}
    assert answers[0]["pod"]


def test_a_visit_is_a_503_when_the_database_is_down(store, client):
    store.down = True
    response = client.get("/")
    assert response.status_code == 503
    assert response.get_json() == {"error": "database unavailable"}


def test_healthz_is_alive_even_when_the_database_is_down(store, client):
    store.down = True
    assert client.get("/healthz").status_code == 200


def test_healthz_is_500_when_liveness_fails(store):
    assert _client(store, alive=False).get("/healthz").status_code == 500


def test_readyz_follows_the_database(store, client):
    assert client.get("/readyz").get_json() == {"status": "ready"}
    store.down = True
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.get_json()["status"] == "not ready"
