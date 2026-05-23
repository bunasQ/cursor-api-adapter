"""Exception hierarchy for cursor-api-adapter."""

from __future__ import annotations


class CursorAgentError(Exception):
    """Base class for all cursor-api-adapter errors."""


class CursorAgentNotFoundError(CursorAgentError):
    """The cursor-agent binary could not be located on PATH or at cli_path."""


class CursorAgentAuthError(CursorAgentError):
    """CURSOR_API_KEY is missing from the environment or rejected by the CLI."""


class CursorAgentTimeout(CursorAgentError):
    """A cursor-agent invocation exceeded its timeout budget."""


class CursorAgentInvocationError(CursorAgentError):
    """cursor-agent exited with a non-zero return code."""

    def __init__(
        self,
        message: str,
        *,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CursorAgentStreamError(CursorAgentError):
    """The stream-json output could not be parsed into a coherent response."""
