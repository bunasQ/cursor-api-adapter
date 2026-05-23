"""Shared pytest fixtures for cursor-api-adapter tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def stream_init() -> str:
    return (FIXTURES / "stream_init.jsonl").read_text()


@pytest.fixture
def stream_assistant() -> str:
    return (FIXTURES / "stream_assistant.jsonl").read_text()


@pytest.fixture
def stream_result() -> str:
    return (FIXTURES / "stream_result.jsonl").read_text()


@pytest.fixture
def stream_full(stream_init: str, stream_assistant: str, stream_result: str) -> str:
    """Realistic stdout: init, then interleaved assistant/result events."""
    return stream_init + stream_assistant + stream_result


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def patched_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Set CURSOR_API_KEY by default so healthcheck doesn't trip on auth."""
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    return monkeypatch


def make_completed(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["cursor-agent"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def make_proc():
    return make_completed
