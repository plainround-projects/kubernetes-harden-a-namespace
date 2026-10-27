import pytest

from tenant_web.infrastructure.settings import ConfigurationError, Settings

MINIMAL = {"TEAM_NAME": "team-a", "DB_PASSWORD": "pw"}


def test_defaults_when_only_the_required_values_are_set():
    settings = Settings.from_env(MINIMAL)
    assert settings.team.value == "team-a"
    assert (settings.db_host, settings.db_port, settings.db_name, settings.db_user) == ("db", 5432, "app", "app")
    assert (settings.pool_size, settings.log_level) == (4, "INFO")


def test_values_come_from_the_environment():
    settings = Settings.from_env(
        {**MINIMAL, "DB_HOST": "pg", "DB_PORT": "6543", "DB_POOL_SIZE": "8", "LOG_LEVEL": "debug"}
    )
    assert (settings.db_host, settings.db_port, settings.pool_size, settings.log_level) == ("pg", 6543, 8, "DEBUG")


def test_the_password_never_appears_in_the_repr():
    assert "hunter2" not in repr(Settings.from_env({**MINIMAL, "DB_PASSWORD": "hunter2"}))


@pytest.mark.parametrize(
    ("env", "variable"),
    [
        ({"DB_PASSWORD": "pw"}, "TEAM_NAME"),
        ({"TEAM_NAME": "Not A Label", "DB_PASSWORD": "pw"}, "TEAM_NAME"),
        ({"TEAM_NAME": "team-a"}, "DB_PASSWORD"),
        ({**MINIMAL, "DB_PORT": "x"}, "DB_PORT"),
        ({**MINIMAL, "DB_PORT": "0"}, "DB_PORT"),
        ({**MINIMAL, "DB_HOST": " "}, "DB_HOST"),
        ({**MINIMAL, "DB_TIMEOUT_SECONDS": "0"}, "DB_TIMEOUT_SECONDS"),
        ({**MINIMAL, "LOG_LEVEL": "LOUD"}, "LOG_LEVEL"),
    ],
)
def test_a_bad_or_missing_value_names_the_variable(env, variable):
    with pytest.raises(ConfigurationError, match=variable):
        Settings.from_env(env)
