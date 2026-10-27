"""Named errors the layers above translate into responses, log lines and exit codes."""


class TenantError(Exception):
    """Base class of every error this service raises on purpose."""


class InvalidTeamNameError(TenantError):
    """A team name that is not a valid Kubernetes namespace label."""


class InvalidCountError(TenantError):
    """A visit count that is not a positive integer."""


class StoreUnavailableError(TenantError):
    """The database cannot be reached or refused the command."""
