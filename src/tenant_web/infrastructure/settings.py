"""Configuration from the environment (twelve-factor), validated once at startup."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from tenant_web.domain.errors import InvalidTeamNameError
from tenant_web.domain.values import TeamName

LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


class ConfigurationError(Exception):
    """An environment variable is missing or malformed. The message names the variable."""


@dataclass(frozen=True, slots=True)
class Settings:
    """What the service reads from its environment. The password never appears in a repr."""

    team: TeamName
    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "app"
    db_user: str = "app"
    db_password: str = field(default="", repr=False)
    db_timeout_seconds: float = 3.0
    pool_size: int = 4
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        """Build settings from a mapping such as os.environ; TEAM_NAME and DB_PASSWORD are required."""
        try:
            team = TeamName(env.get("TEAM_NAME", ""))
        except InvalidTeamNameError as error:
            raise ConfigurationError(f"TEAM_NAME: {error}") from error
        password = env.get("DB_PASSWORD", "")
        if not password:
            raise ConfigurationError("DB_PASSWORD must be set (the cluster supplies it from a Secret)")
        log_level = env.get("LOG_LEVEL", "INFO").upper()
        if log_level not in LOG_LEVELS:
            raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(LOG_LEVELS)}, got {log_level!r}")
        return cls(
            team=team,
            db_host=_text(env, "DB_HOST", "db"),
            db_port=int(_number(env, "DB_PORT", 5432, 1, 65535)),
            db_name=_text(env, "DB_NAME", "app"),
            db_user=_text(env, "DB_USER", "app"),
            db_password=password,
            db_timeout_seconds=_number(env, "DB_TIMEOUT_SECONDS", 3.0, 0.1, 60),
            pool_size=int(_number(env, "DB_POOL_SIZE", 4, 1, 64)),
            log_level=log_level,
        )


def _text(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, default).strip()
    if not value:
        raise ConfigurationError(f"{name} must not be empty")
    return value


def _number(env: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from None
    if not low <= value <= high:
        raise ConfigurationError(f"{name} must be between {low} and {high}, got {value}")
    return value
