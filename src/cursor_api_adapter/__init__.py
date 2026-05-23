"""Pythonic client for the cursor-agent CLI."""

from __future__ import annotations

from .client import CursorAgentClient
from .errors import (
    CursorAgentAuthError,
    CursorAgentError,
    CursorAgentInvocationError,
    CursorAgentNotFoundError,
    CursorAgentStreamError,
    CursorAgentTimeout,
)
from .responses import CursorAgentResponse, StreamEvent, Usage

__version__ = "0.1.0"

__all__ = [
    "CursorAgentAuthError",
    "CursorAgentClient",
    "CursorAgentError",
    "CursorAgentInvocationError",
    "CursorAgentNotFoundError",
    "CursorAgentResponse",
    "CursorAgentStreamError",
    "CursorAgentTimeout",
    "StreamEvent",
    "Usage",
    "__version__",
]
