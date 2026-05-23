"""Tests for the mini-swe-agent adapter. Skipped if minisweagent is not installed."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

pytest.importorskip("minisweagent")

from cursor_api_adapter import _process  # noqa: E402
from cursor_api_adapter.adapters import minisweagent as adapter_mod  # noqa: E402


def _stream_blob(session_id: str, text: str) -> str:
    init = {"type": "system", "subtype": "init", "session_id": session_id}
    assistant = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    }
    result = {
        "type": "result",
        "usage": {"inputTokens": 11, "outputTokens": 22, "cacheReadTokens": 3},
    }
    return "\n".join(json.dumps(e) for e in (init, assistant, result)) + "\n"


class _ProcStub:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_query_returns_expected_dict_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    text_with_action = "Sure, here's the plan.\n```mswea_bash_command\nls -la\n```\n"

    def fake_run(cmd, *, cwd, timeout, env):  # noqa: ANN001
        return _ProcStub(stdout=_stream_blob("sess-mswea-1", text_with_action))

    monkeypatch.setattr(_process, "run", fake_run)

    model = adapter_mod.CursorCLIModel(
        model_name="composer-2.5",
        workspace=str(tmp_path),
    )
    out = model.query(messages=[{"role": "user", "content": "Plan the work."}])

    assert out["role"] == "assistant"
    assert "plan" in out["content"].lower()
    assert "```mswea_bash_command" in out["content"]
    extra = out["extra"]
    assert extra["cost"] == 0.0
    assert extra["input_tokens"] == 11
    assert extra["output_tokens"] == 22
    assert extra["cache_read_tokens"] == 3
    assert extra["cursor_session_id"] == "sess-mswea-1"
    assert isinstance(extra["timestamp"], float)
    assert isinstance(extra["actions"], list)
    assert len(extra["actions"]) == 1


def test_serialize_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reply = "Doing it.\n```mswea_bash_command\necho hi\n```\n"
    monkeypatch.setattr(
        _process,
        "run",
        lambda cmd, *, cwd, timeout, env: _ProcStub(stdout=_stream_blob("sess-z", reply)),
    )
    model = adapter_mod.CursorCLIModel(
        model_name="composer-2.5",
        workspace=str(tmp_path),
    )
    # Run a query to mint a session and populate usage.
    model.query(messages=[{"role": "user", "content": "hi"}])
    s = model.serialize()
    assert s["info"]["config"]["model"]["model_name"] == "composer-2.5"
    assert s["info"]["config"]["model_type"].endswith("CursorCLIModel")
    assert s["info"]["cursor"]["session_id"] == "sess-z"
    assert s["info"]["cursor"]["input_tokens"] == 11
    assert s["info"]["cursor"]["output_tokens"] == 22
    assert s["info"]["cursor"]["cache_read_tokens"] == 3


def test_first_prompt_bundles_system_user_harness(tmp_path: Path) -> None:
    model = adapter_mod.CursorCLIModel(
        model_name="composer-2.5",
        workspace=str(tmp_path),
    )
    prompt = model._build_first_prompt(
        [
            {"role": "system", "content": "You are a planner."},
            {"role": "user", "content": "Implement X."},
        ]
    )
    assert "[SYSTEM]\nYou are a planner." in prompt
    assert "[USER]\nImplement X." in prompt
    assert "[HARNESS NOTE]" in prompt
    assert "mswea_bash_command" in prompt


def test_multimodal_regex_rewrite_writes_file(tmp_path: Path) -> None:
    b64 = base64.b64encode(b"pngbytes").decode()
    pattern = r"(?s)<MSWEA_MULTIMODAL_CONTENT type=\"([^\"]+)\">(.*?)</MSWEA_MULTIMODAL_CONTENT>"
    model = adapter_mod.CursorCLIModel(
        model_name="composer-2.5",
        workspace=str(tmp_path),
        multimodal_regex=pattern,
    )
    text = (
        f'<MSWEA_MULTIMODAL_CONTENT type="image_url">data:image/png;base64,{b64}'
        f"</MSWEA_MULTIMODAL_CONTENT>"
    )
    prompt = model._build_first_prompt([{"role": "user", "content": text}])
    assert "[image attached at ./_mswea_image_1.png — read this file to see the design]" in prompt
    assert (tmp_path / "_mswea_image_1.png").read_bytes() == b"pngbytes"


def test_image_url_content_part_writes_mswea_image(tmp_path: Path) -> None:
    b64 = base64.b64encode(b"webpbytes").decode()
    model = adapter_mod.CursorCLIModel(
        model_name="composer-2.5",
        workspace=str(tmp_path),
    )
    prompt = model._build_first_prompt(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Here is the image:"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/webp;base64,{b64}"},
                    },
                ],
            }
        ]
    )
    assert "[image attached at ./_mswea_image_1.webp]" in prompt
    assert (tmp_path / "_mswea_image_1.webp").read_bytes() == b"webpbytes"


def test_later_turn_sends_only_last_message(tmp_path: Path) -> None:
    model = adapter_mod.CursorCLIModel(
        model_name="composer-2.5",
        workspace=str(tmp_path),
    )
    # Simulate a session already minted.
    model._client._session_id = "sess-existing"
    out = model._prompt_for_turn(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "older"},
            {"role": "user", "content": "latest"},
        ]
    )
    assert out == "latest"


def test_abort_exceptions_includes_keyboard_interrupt() -> None:
    assert KeyboardInterrupt in adapter_mod.CursorCLIModel.abort_exceptions


def test_unknown_kwargs_raise(tmp_path: Path) -> None:
    # Source's Pydantic raised on unknown keys; the dataclass adapter matches.
    with pytest.raises(TypeError, match="Unknown CursorCLIModel kwargs"):
        adapter_mod.CursorCLIModel(
            model_name="composer-2.5",
            workspace=str(tmp_path),
            some_future_field="ignored",
        )


def test_missing_model_name_raises(tmp_path: Path) -> None:
    # Source's Pydantic required model_name; the dataclass adapter rejects empty.
    with pytest.raises(ValueError, match="model_name is required"):
        adapter_mod.CursorCLIModel(workspace=str(tmp_path))


def test_query_raises_friendly_importerror_without_minisweagent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sys

    model = adapter_mod.CursorCLIModel(model_name="composer-2.5", workspace=str(tmp_path))
    # Setting sys.modules entries to None makes deferred imports raise ImportError.
    monkeypatch.setitem(sys.modules, "minisweagent.models", None)
    monkeypatch.setitem(sys.modules, "minisweagent.models.utils.actions_text", None)

    with pytest.raises(ImportError, match="cursor-api-adapter\\[minisweagent\\]"):
        model.query(messages=[{"role": "user", "content": "hi"}])
