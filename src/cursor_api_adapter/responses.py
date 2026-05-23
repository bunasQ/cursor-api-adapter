"""Public response dataclasses returned by CursorAgentClient."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        if not isinstance(other, Usage):
            return NotImplemented
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
        )


@dataclass(frozen=True, slots=True)
class CursorAgentResponse:
    text: str
    session_id: str | None
    usage: Usage
    raw_events: tuple[dict, ...]
    model: str
    duration_s: float


@dataclass(frozen=True, slots=True)
class StreamEvent:
    type: str
    data: dict = field(default_factory=dict)
