"""Subprocess helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

from .errors import CursorAgentInvocationError, CursorAgentTimeout


def which(cli_path: str) -> str | None:
    """Return an absolute path for `cli_path` or None if not found.

    If `cli_path` already looks like a path (contains a separator), check it
    exists and is executable directly (matches ``shutil.which`` semantics).
    Otherwise resolve it via PATH using ``shutil.which``.
    """
    if os.sep in cli_path or (os.altsep and os.altsep in cli_path):
        p = Path(cli_path)
        if p.is_file() and os.access(p, os.X_OK):
            return cli_path
        return None
    return shutil.which(cli_path)


def merged_env(extra: Mapping[str, str] | None) -> dict[str, str] | None:
    """Merge `extra` onto a copy of ``os.environ``. Returns None if `extra` is None."""
    if extra is None:
        return None
    env = dict(os.environ)
    env.update(extra)
    return env


def run(
    cmd: list[str],
    *,
    cwd: str | os.PathLike | None,
    timeout: float,
    env: Mapping[str, str] | None,
) -> subprocess.CompletedProcess[str]:
    """Run `cmd`, capturing text output. Raises ``subprocess.TimeoutExpired`` on timeout."""
    return subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
        env=merged_env(env),
        check=False,
    )


def run_cli(
    cmd: list[str],
    *,
    cwd: str | os.PathLike | None,
    timeout: float,
    env: Mapping[str, str] | None,
) -> subprocess.CompletedProcess[str]:
    """Run a cursor-agent CLI command, translating failures to library exceptions.

    Raises:
        CursorAgentTimeout: if the call exceeds ``timeout`` seconds.
        CursorAgentInvocationError: if the process exits with a non-zero status.
    """
    try:
        proc = run(cmd, cwd=cwd, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        raise CursorAgentTimeout(f"cursor-agent timed out after {e.timeout}s") from e
    if proc.returncode != 0:
        raise CursorAgentInvocationError(
            f"cursor-agent exited {proc.returncode}",
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    return proc
