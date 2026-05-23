"""Pure parser for cursor-agent --output-format stream-json output."""

from __future__ import annotations

import json
from collections.abc import Iterator

from .responses import StreamEvent, Usage


def usage_from_event(evt: dict) -> Usage:
    raw = evt.get("usage") or {}
    return Usage(
        input_tokens=int(raw.get("inputTokens", 0) or 0),
        output_tokens=int(raw.get("outputTokens", 0) or 0),
        cache_read_tokens=int(raw.get("cacheReadTokens", 0) or 0),
    )


def iter_events(stdout: str) -> Iterator[dict]:
    """Yield decoded JSON events from a stream-json blob, skipping malformed lines."""
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def parse_stream(stdout: str) -> tuple[str, Usage, str | None, list[dict]]:
    """Parse a complete stream-json stdout blob.

    Returns ``(assistant_text, usage, session_id, raw_events)``.

    - ``assistant_text``: concatenation of every ``type=assistant`` text part.
      Falls back to the final ``result`` block's ``result`` field if no
      assistant chunks were emitted.
    - ``usage``: pulled from the LAST ``type=result`` block (canonical for the call).
    - ``session_id``: captured from the first ``type=system, subtype=init`` event.
    - ``raw_events``: every parsed event in order.
    """
    assistant_text = ""
    usage = Usage()
    session_id: str | None = None
    events: list[dict] = []
    result_fallback = ""

    for evt in iter_events(stdout):
        events.append(evt)
        etype = evt.get("type")
        if etype == "system" and evt.get("subtype") == "init":
            sid = evt.get("session_id")
            if sid and session_id is None:
                session_id = sid
        elif etype == "assistant":
            msg = evt.get("message") or {}
            for part in msg.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "text":
                    assistant_text += part.get("text", "")
        elif etype == "result":
            usage = usage_from_event(evt)
            if evt.get("result"):
                result_fallback = str(evt["result"])

    if not assistant_text and result_fallback:
        assistant_text = result_fallback

    return assistant_text, usage, session_id, events


def parse_event(evt: dict) -> StreamEvent:
    """Wrap a decoded JSON event in a typed StreamEvent."""
    return StreamEvent(type=str(evt.get("type", "")), data=evt)


__all__ = ["iter_events", "parse_event", "parse_stream", "usage_from_event"]
