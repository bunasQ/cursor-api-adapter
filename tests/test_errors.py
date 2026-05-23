"""Tests for the healthcheck error paths."""

from __future__ import annotations

import subprocess

import pytest

from cursor_api_adapter import CursorAgentClient, _process
from cursor_api_adapter.errors import (
    CursorAgentAuthError,
    CursorAgentInvocationError,
    CursorAgentNotFoundError,
    CursorAgentTimeout,
)


def test_healthcheck_raises_not_found_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch, patched_env: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_process, "which", lambda _: None)
    c = CursorAgentClient(cli_path="cursor-agent")
    with pytest.raises(CursorAgentNotFoundError):
        c.healthcheck()


def test_healthcheck_raises_auth_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_process, "which", lambda _: "/usr/local/bin/cursor-agent")
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    c = CursorAgentClient()
    with pytest.raises(CursorAgentAuthError):
        c.healthcheck()


def test_healthcheck_raises_invocation_when_version_nonzero(
    monkeypatch: pytest.MonkeyPatch, patched_env: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_process, "which", lambda _: "/usr/local/bin/cursor-agent")

    def fake_run(cmd, *, cwd, timeout, env):  # noqa: ANN001
        return subprocess.CompletedProcess(args=cmd, returncode=2, stdout="", stderr="boom")

    monkeypatch.setattr(_process, "run", fake_run)
    c = CursorAgentClient()
    with pytest.raises(CursorAgentInvocationError) as ei:
        c.healthcheck()
    assert ei.value.returncode == 2
    assert ei.value.stderr == "boom"


def test_healthcheck_raises_timeout_when_version_hangs(
    monkeypatch: pytest.MonkeyPatch, patched_env: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_process, "which", lambda _: "/usr/local/bin/cursor-agent")

    def fake_run(cmd, *, cwd, timeout, env):  # noqa: ANN001
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(_process, "run", fake_run)
    c = CursorAgentClient()
    with pytest.raises(CursorAgentTimeout):
        c.healthcheck()


def test_healthcheck_passes_when_everything_ok(
    monkeypatch: pytest.MonkeyPatch, patched_env: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_process, "which", lambda _: "/usr/local/bin/cursor-agent")

    def fake_run(cmd, *, cwd, timeout, env):  # noqa: ANN001
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="cursor-agent 1.0.0\n", stderr=""
        )

    monkeypatch.setattr(_process, "run", fake_run)
    c = CursorAgentClient()
    c.healthcheck()  # should not raise


def test_attach_image_without_workspace_raises_cursor_agent_error() -> None:
    from cursor_api_adapter.errors import CursorAgentError

    c = CursorAgentClient(workspace=None)
    with pytest.raises(CursorAgentError):
        c.attach_image("data:image/png;base64,QUJD")
