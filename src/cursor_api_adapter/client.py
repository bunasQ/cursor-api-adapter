"""Synchronous client for the cursor-agent CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from . import _process
from .errors import (
    CursorAgentAuthError,
    CursorAgentError,
    CursorAgentInvocationError,
    CursorAgentNotFoundError,
    CursorAgentStreamError,
    CursorAgentTimeout,
)
from .images import save_data_url
from .responses import CursorAgentResponse, StreamEvent, Usage
from .stream import parse_event, parse_stream, usage_from_event


class CursorAgentClient:
    """Pythonic wrapper around the ``cursor-agent`` CLI."""

    def __init__(
        self,
        model: str = "composer-2.5",
        *,
        workspace: str | os.PathLike | None = None,
        cli_path: str = "cursor-agent",
        timeout: float = 300.0,
        extra_cli_args: Sequence[str] = (),
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._model = model
        self._workspace: Path | None = Path(workspace) if workspace is not None else None
        self._cli_path = cli_path
        self._timeout = timeout
        self._extra_cli_args: tuple[str, ...] = tuple(extra_cli_args)
        self._env: Mapping[str, str] | None = env
        self._session_id: str | None = None
        self._total_usage = Usage()
        self._image_counter = 0

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def total_usage(self) -> Usage:
        return self._total_usage

    @property
    def model(self) -> str:
        return self._model

    @property
    def workspace(self) -> Path | None:
        return self._workspace

    def healthcheck(self) -> None:
        """Verify cursor-agent is available and the environment is configured.

        Raises:
            CursorAgentNotFoundError: binary not found on PATH or at ``cli_path``.
            CursorAgentAuthError: ``CURSOR_API_KEY`` not set.
            CursorAgentInvocationError: ``cursor-agent --version`` exits non-zero.
        """
        resolved = _process.which(self._cli_path)
        if resolved is None:
            raise CursorAgentNotFoundError(
                f"cursor-agent binary not found (cli_path={self._cli_path!r}). "
                "Install from https://docs.cursor.com/cli or pass cli_path=."
            )
        if not os.environ.get("CURSOR_API_KEY"):
            raise CursorAgentAuthError(
                "CURSOR_API_KEY is not set. Export it before calling cursor-agent."
            )
        _process.run_cli(
            [resolved, "--version"],
            cwd=None,
            timeout=5.0,
            env=self._env,
        )

    def chat(self, prompt: str, *, model: str | None = None) -> CursorAgentResponse:
        """Send a prompt. If no session has been minted yet, this call mints one;
        otherwise it resumes the existing session."""
        return self._invoke(prompt, model=model, resume_with=self._session_id)

    def resume(self, session_id: str, prompt: str) -> CursorAgentResponse:
        """Resume a known server-side session and send `prompt`."""
        self._session_id = session_id
        return self._invoke(prompt, model=None, resume_with=session_id)

    def reset(self) -> None:
        """Forget the current session_id. The next ``chat()`` will mint a new one."""
        self._session_id = None

    def stream(self, prompt: str) -> Iterator[StreamEvent]:
        """Run cursor-agent and yield parsed StreamEvents as it writes them.

        ``session_id`` is updated the moment the ``system/init`` event arrives,
        so callers can break out of the iterator early without losing the
        session. ``total_usage`` is updated as each ``result`` event arrives.

        Note: the timeout bounds the post-stream wait only; a slow-streaming
        process can exceed it.
        """
        cmd = self._build_cmd(model=None, resume_with=self._session_id)
        cmd.append(prompt)
        env = _process.merged_env(self._env)
        cwd = str(self._workspace) if self._workspace is not None else None

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
            bufsize=1,
        )

        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if evt.get("type") == "system" and evt.get("subtype") == "init":
                    sid = evt.get("session_id")
                    if sid and self._session_id is None:
                        self._session_id = sid
                elif evt.get("type") == "result":
                    self._total_usage = self._total_usage + usage_from_event(evt)
                yield parse_event(evt)

            try:
                returncode = proc.wait(timeout=self._timeout)
            except subprocess.TimeoutExpired as e:
                raise CursorAgentTimeout(
                    f"cursor-agent stream timed out after {self._timeout}s"
                ) from e
            if returncode != 0:
                stderr = proc.stderr.read() if proc.stderr else ""
                raise CursorAgentInvocationError(
                    f"cursor-agent exited {returncode}",
                    returncode=returncode,
                    stdout="",
                    stderr=stderr,
                )
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def attach_image(self, source: str | os.PathLike) -> Path:
        """Materialize an image into the workspace and return its path.

        `source` may be either a ``data:`` URL or a path to an existing file. The
        returned path is relative to the workspace when one is set, otherwise
        absolute.
        """
        if self._workspace is None:
            raise CursorAgentError(
                "attach_image() requires a workspace. Pass workspace= to CursorAgentClient()."
            )
        ws = self._workspace
        ws.mkdir(parents=True, exist_ok=True)

        src_str = os.fspath(source)
        if src_str.startswith("data:"):
            self._image_counter += 1
            saved = save_data_url(src_str, ws, self._image_counter)
            if saved is None:
                raise CursorAgentError("Could not decode data URL.")
            return saved

        src_path = Path(src_str)
        if not src_path.exists():
            raise FileNotFoundError(src_str)
        self._image_counter += 1
        ext = src_path.suffix.lstrip(".").lower() or "png"
        filename = f"_cursor_image_{self._image_counter}.{ext}"
        shutil.copyfile(src_path, ws / filename)
        return Path(filename)

    def _build_cmd(self, *, model: str | None, resume_with: str | None) -> list[str]:
        chosen_model = model or self._model
        cmd: list[str] = [
            self._cli_path,
            "--print",
            "-f",
            "--output-format",
            "stream-json",
            "--model",
            chosen_model,
        ]
        if self._workspace is not None:
            cmd.extend(["--workspace", str(self._workspace)])
        cmd.extend(self._extra_cli_args)
        if resume_with is not None:
            cmd.extend(["--resume", resume_with])
        return cmd

    def _invoke(
        self,
        prompt: str,
        *,
        model: str | None,
        resume_with: str | None,
    ) -> CursorAgentResponse:
        cmd = self._build_cmd(model=model, resume_with=resume_with)
        cmd.append(prompt)
        cwd = str(self._workspace) if self._workspace is not None else None

        started = time.monotonic()
        proc = _process.run_cli(cmd, cwd=cwd, timeout=self._timeout, env=self._env)
        duration_s = time.monotonic() - started

        text, usage, session_id, events = parse_stream(proc.stdout)
        if not text and not events:
            raise CursorAgentStreamError(
                f"cursor-agent produced no parseable output. stdout={proc.stdout!r}"
            )
        if session_id and self._session_id is None:
            self._session_id = session_id
        self._total_usage = self._total_usage + usage

        return CursorAgentResponse(
            text=text,
            session_id=self._session_id,
            usage=usage,
            raw_events=tuple(events),
            model=model or self._model,
            duration_s=duration_s,
        )


__all__ = ["CursorAgentClient"]
