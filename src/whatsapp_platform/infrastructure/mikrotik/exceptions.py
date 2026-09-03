"""MikroTik custom domain exceptions."""


class MikroTikError(Exception):
    """Base exception for all MikroTik integration errors."""


class MikroTikDisabledError(MikroTikError):
    """Raised when MikroTik integration is disabled in settings."""


class MikroTikConnectionError(MikroTikError):
    """Raised when network connection to MikroTik router fails."""


class MikroTikAuthError(MikroTikError):
    """Raised when authentication to MikroTik router fails (401/403)."""


class MikroTikTimeoutError(MikroTikError):
    """Raised when MikroTik API request times out."""


class MikroTikPermissionError(MikroTikError):
    """Raised when user is not authorized to execute network tools."""
