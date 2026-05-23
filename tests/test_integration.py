"""End-to-end test against a real cursor-agent CLI.

Skipped by default. Set CURSOR_ADAPTER_LIVE=1 and have cursor-agent on PATH
with CURSOR_API_KEY exported to run this.
"""

from __future__ import annotations

import os

import pytest

from cursor_api_adapter import CursorAgentClient

pytestmark = pytest.mark.skipif(
    not os.getenv("CURSOR_ADAPTER_LIVE"),
    reason="set CURSOR_ADAPTER_LIVE=1 to run the live cursor-agent integration test",
)


def test_live_chat_roundtrip(tmp_path) -> None:  # noqa: ANN001
    client = CursorAgentClient(model="composer-2.5", workspace=str(tmp_path))
    client.healthcheck()

    first = client.chat("Reply with exactly the single word: ok")
    assert first.text.strip(), "expected non-empty assistant text"
    assert client.session_id, "session_id should be minted on first call"

    # Second call should resume.
    second = client.chat("And again: ok")
    assert second.session_id == first.session_id
    assert client.total_usage.input_tokens >= first.usage.input_tokens
