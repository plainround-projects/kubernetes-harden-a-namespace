import pytest

from tenant_web.interfaces import wsgi


class FakePool:
    opened = False

    def open(self, wait=True):
        FakePool.opened = True

    def connection(self):
        raise AssertionError("no query in this test")


def test_the_factory_opens_the_pool_without_waiting_and_builds_the_app(monkeypatch):
    monkeypatch.setattr(wsgi, "build_pool", lambda settings: FakePool())
    app = wsgi.build_app({"TEAM_NAME": "team-a", "DB_PASSWORD": "pw"})
    assert FakePool.opened
    assert app.test_client().get("/healthz").status_code == 200


@pytest.mark.parametrize("env", [{}, {"TEAM_NAME": "team-a"}, {"TEAM_NAME": "BAD", "DB_PASSWORD": "pw"}])
def test_a_bad_configuration_exits_with_one_fatal_line(env, capfd):
    with pytest.raises(SystemExit) as exit_info:
        wsgi.build_app(env)
    assert exit_info.value.code == 1
    assert "FATAL invalid configuration" in capfd.readouterr().err
