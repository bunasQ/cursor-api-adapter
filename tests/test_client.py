"""Subprocess-mocked tests for CursorAgentClient."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from cursor_api_adapter import (
    CursorAgentClient,
    CursorAgentInvocationError,
    CursorAgentStreamError,
    CursorAgentTimeout,
    _process,
)


def _stream_blob(session_id: str, text: str, *, in_tok: int = 1, out_tok: int = 2) -> str:
    init = {"type": "system", "subtype": "init", "session_id": session_id}
    assistant = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    }
    result = {
        "type": "result",
        "usage": {
            "inputTokens": in_tok,
            "outputTokens": out_tok,
            "cacheReadTokens": 0,
        },
    }
    return "\n".join(json.dumps(e) for e in (init, assistant, result)) + "\n"


class _ProcStub:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Collect every cmd passed to _process.run; return a canned stream blob."""
    captured: list[list[str]] = []
    blobs = iter(
        [
            _stream_blob("sess-first", "First reply."),
            _stream_blob("sess-first", "Second reply.", in_tok=4, out_tok=5),
            _stream_blob("sess-first", "Third reply."),
        ]
    )

    def fake_run(cmd, *, cwd, timeout, env):  # noqa: ANN001
        captured.append(list(cmd))
        try:
            return _ProcStub(stdout=next(blobs))
        except StopIteration:
            return _ProcStub(stdout=_stream_blob("sess-first", "extra"))

    monkeypatch.setattr(_process, "run", fake_run)
    return captured


def test_cmd_construction_has_expected_flags(calls: list[list[str]]) -> None:
    c = CursorAgentClient(model="composer-2.5", workspace="/tmp/wsx")
    c.chat("hello")
    cmd = calls[0]
    assert cmd[0] == "cursor-agent"
    assert "--print" in cmd
    assert "-f" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert cmd[cmd.index("--model") + 1] == "composer-2.5"
    assert cmd[cmd.index("--workspace") + 1] == "/tmp/wsx"
    # Prompt is the last arg.
    assert cmd[-1] == "hello"


def test_extra_cli_args_passed_through(calls: list[list[str]]) -> None:
    c = CursorAgentClient(extra_cli_args=("--verbose", "--foo=bar"))
    c.chat("hi")
    cmd = calls[0]
    assert "--verbose" in cmd
    assert "--foo=bar" in cmd


def test_resume_added_on_second_call(calls: list[list[str]]) -> None:
    c = CursorAgentClient()
    c.chat("first")
    c.chat("second")
    # First call: no --resume
    assert "--resume" not in calls[0]
    # Second call: --resume sess-first
    assert "--resume" in calls[1]
    assert calls[1][calls[1].index("--resume") + 1] == "sess-first"


def test_session_id_stored_after_first_call(calls: list[list[str]]) -> None:
    c = CursorAgentClient()
    assert c.session_id is None
    c.chat("hi")
    assert c.session_id == "sess-first"


def test_usage_accumulates_across_calls(calls: list[list[str]]) -> None:
    c = CursorAgentClient()
    c.chat("hi")
    assert c.total_usage.input_tokens == 1
    assert c.total_usage.output_tokens == 2
    c.chat("again")
    assert c.total_usage.input_tokens == 1 + 4
    assert c.total_usage.output_tokens == 2 + 5


def test_response_shape(calls: list[list[str]]) -> None:
    c = CursorAgentClient()
    r = c.chat("hi")
    assert r.text == "First reply."
    assert r.session_id == "sess-first"
    assert r.usage.input_tokens == 1
    assert r.usage.output_tokens == 2
    assert r.model == "composer-2.5"
    assert isinstance(r.raw_events, tuple)
    assert len(r.raw_events) == 3
    assert r.duration_s >= 0


def test_reset_clears_session_then_mints_new(
    monkeypatch: pytest.MonkeyPatch, calls: list[list[str]]
) -> None:
    c = CursorAgentClient()
    c.chat("hi")
    assert c.session_id == "sess-first"
    c.reset()
    assert c.session_id is None
    c.chat("hi again")
    # After reset the next call still has no --resume.
    assert "--resume" not in calls[1]


def test_resume_method_forces_session_id(
    monkeypatch: pytest.MonkeyPatch, calls: list[list[str]]
) -> None:
    c = CursorAgentClient()
    c.resume("sess-from-server", "hi there")
    cmd = calls[0]
    assert "--resume" in cmd
    assert cmd[cmd.index("--resume") + 1] == "sess-from-server"
    assert c.session_id == "sess-from-server"


def test_timeout_raises_cursor_agent_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, *, cwd, timeout, env):  # noqa: ANN001
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(_process, "run", fake_run)
    c = CursorAgentClient(timeout=1.0)
    with pytest.raises(CursorAgentTimeout):
        c.chat("hello")


def test_non_zero_exit_raises_invocation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, *, cwd, timeout, env):  # noqa: ANN001
        return _ProcStub(stdout="oops", stderr="bad", returncode=7)

    monkeypatch.setattr(_process, "run", fake_run)
    c = CursorAgentClient()
    with pytest.raises(CursorAgentInvocationError) as ei:
        c.chat("hello")
    assert ei.value.returncode == 7
    assert ei.value.stdout == "oops"
    assert ei.value.stderr == "bad"


def test_empty_stdout_raises_stream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, *, cwd, timeout, env):  # noqa: ANN001
        return _ProcStub(stdout="", returncode=0)

    monkeypatch.setattr(_process, "run", fake_run)
    c = CursorAgentClient()
    with pytest.raises(CursorAgentStreamError):
        c.chat("hello")


def test_chat_model_override_overrides_default_for_this_call(
    calls: list[list[str]],
) -> None:
    c = CursorAgentClient(model="composer-2.5")
    r = c.chat("hi", model="gpt-5.5-high")
    assert calls[0][calls[0].index("--model") + 1] == "gpt-5.5-high"
    assert r.model == "gpt-5.5-high"
    # Default isn't changed.
    assert c.model == "composer-2.5"


def test_workspace_cwd_is_passed_to_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_cwd: dict[str, Any] = {}

    def fake_run(cmd, *, cwd, timeout, env):  # noqa: ANN001
        captured_cwd["cwd"] = cwd
        return _ProcStub(stdout=_stream_blob("s1", "ok"))

    monkeypatch.setattr(_process, "run", fake_run)
    c = CursorAgentClient(workspace="/tmp/wsx")
    c.chat("hi")
    assert captured_cwd["cwd"] == "/tmp/wsx"


def test_no_workspace_cwd_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_cwd: dict[str, Any] = {}

    def fake_run(cmd, *, cwd, timeout, env):  # noqa: ANN001
        captured_cwd["cwd"] = cwd
        return _ProcStub(stdout=_stream_blob("s1", "ok"))

    monkeypatch.setattr(_process, "run", fake_run)
    c = CursorAgentClient()
    c.chat("hi")
    assert captured_cwd["cwd"] is None
