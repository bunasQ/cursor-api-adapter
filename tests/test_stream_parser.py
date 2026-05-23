"""Unit tests for cursor_api_adapter.stream.parse_stream."""

from __future__ import annotations

from cursor_api_adapter.stream import parse_stream


def test_empty_stdout_returns_defaults() -> None:
    text, usage, sid, events = parse_stream("")
    assert text == ""
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cache_read_tokens == 0
    assert sid is None
    assert events == []


def test_whitespace_only_stdout_returns_defaults() -> None:
    text, usage, sid, events = parse_stream("\n\n   \n")
    assert text == ""
    assert sid is None
    assert events == []


def test_init_event_captures_session_id(stream_init: str) -> None:
    _, _, sid, events = parse_stream(stream_init)
    assert sid == "sess-test-abc123"
    assert len(events) == 1
    assert events[0]["type"] == "system"


def test_multi_chunk_assistant_text_concatenation(stream_assistant: str) -> None:
    text, _, _, events = parse_stream(stream_assistant)
    assert text == "Hello world. Goodbye."
    assert len(events) == 3


def test_last_result_wins_for_usage(stream_result: str) -> None:
    _, usage, _, events = parse_stream(stream_result)
    # Final block: inputTokens=100, outputTokens=42, cacheReadTokens=7
    assert usage.input_tokens == 100
    assert usage.output_tokens == 42
    assert usage.cache_read_tokens == 7
    assert len(events) == 2


def test_full_stream_combines_everything(stream_full: str) -> None:
    text, usage, sid, events = parse_stream(stream_full)
    assert sid == "sess-test-abc123"
    assert text == "Hello world. Goodbye."
    assert usage.input_tokens == 100
    assert usage.output_tokens == 42
    assert usage.cache_read_tokens == 7
    # init + 3 assistant + 2 result = 6
    assert len(events) == 6


def test_malformed_lines_are_tolerated() -> None:
    raw = "\n".join(
        [
            '{"type":"system","subtype":"init","session_id":"sess-x"}',
            "not-json-at-all",
            "",
            '{"type":"assistant","message":{"content":[{"type":"text","text":"ok"}]}}',
            "{bad json:",
            '{"type":"result","usage":{"inputTokens":5,"outputTokens":6,"cacheReadTokens":1}}',
        ]
    )
    text, usage, sid, events = parse_stream(raw)
    assert sid == "sess-x"
    assert text == "ok"
    assert usage.input_tokens == 5
    assert usage.output_tokens == 6
    assert usage.cache_read_tokens == 1
    # Three well-formed events; two malformed lines skipped.
    assert len(events) == 3


def test_result_fallback_text_when_no_assistant_events() -> None:
    raw = (
        '{"type":"system","subtype":"init","session_id":"s1"}\n'
        '{"type":"result","usage":{"inputTokens":1,"outputTokens":1,"cacheReadTokens":0},'
        '"result":"fallback text"}\n'
    )
    text, _, sid, _ = parse_stream(raw)
    assert text == "fallback text"
    assert sid == "s1"


def test_session_id_only_set_on_first_init() -> None:
    raw = (
        '{"type":"system","subtype":"init","session_id":"first"}\n'
        '{"type":"system","subtype":"init","session_id":"second"}\n'
    )
    _, _, sid, _ = parse_stream(raw)
    assert sid == "first"


def test_assistant_event_with_no_text_part_is_ignored() -> None:
    raw = (
        '{"type":"assistant","message":{"content":[{"type":"image","data":"x"}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":"only this"}]}}\n'
    )
    text, _, _, _ = parse_stream(raw)
    assert text == "only this"


def test_missing_usage_keys_default_to_zero() -> None:
    raw = '{"type":"result","usage":{"inputTokens":10}}\n'
    _, usage, _, _ = parse_stream(raw)
    assert usage.input_tokens == 10
    assert usage.output_tokens == 0
    assert usage.cache_read_tokens == 0
