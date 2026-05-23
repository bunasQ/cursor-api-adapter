"""Tests for cursor_api_adapter.images.save_data_url."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from cursor_api_adapter.images import save_data_url


def _data_url(mime: str, payload: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode()}"


def test_save_png(workspace: Path) -> None:
    url = _data_url("image/png", b"png-bytes")
    out = save_data_url(url, workspace, 1)
    assert out == Path("_cursor_image_1.png")
    assert (workspace / out).read_bytes() == b"png-bytes"


def test_save_jpeg(workspace: Path) -> None:
    url = _data_url("image/jpeg", b"jpeg-bytes")
    out = save_data_url(url, workspace, 2)
    assert out == Path("_cursor_image_2.jpg")
    assert (workspace / out).read_bytes() == b"jpeg-bytes"


def test_save_webp(workspace: Path) -> None:
    url = _data_url("image/webp", b"webp-bytes")
    out = save_data_url(url, workspace, 3)
    assert out == Path("_cursor_image_3.webp")
    assert (workspace / out).read_bytes() == b"webp-bytes"


def test_unknown_mime_defaults_to_png(workspace: Path) -> None:
    url = _data_url("image/heic", b"heic-bytes")
    out = save_data_url(url, workspace, 1)
    assert out == Path("_cursor_image_1.png")


def test_prefix_override(workspace: Path) -> None:
    url = _data_url("image/png", b"x")
    out = save_data_url(url, workspace, 9, prefix="_mswea_image")
    assert out == Path("_mswea_image_9.png")
    assert (workspace / out).read_bytes() == b"x"


def test_non_data_url_returns_none(workspace: Path) -> None:
    assert save_data_url("https://example.com/foo.png", workspace, 1) is None
    assert save_data_url("/tmp/foo.png", workspace, 1) is None


def test_malformed_data_url_no_comma_returns_none(workspace: Path) -> None:
    assert save_data_url("data:image/png;base64", workspace, 1) is None


def test_returned_path_is_relative(workspace: Path) -> None:
    out = save_data_url(_data_url("image/png", b"x"), workspace, 1)
    assert out is not None
    assert not out.is_absolute()


def test_workspace_is_created_if_missing(tmp_path: Path) -> None:
    ws = tmp_path / "doesnt-exist-yet"
    out = save_data_url(_data_url("image/png", b"x"), ws, 1)
    assert out is not None
    assert (ws / out).exists()


@pytest.mark.parametrize(
    "mime, ext",
    [("image/png", "png"), ("image/jpeg", "jpg"), ("image/webp", "webp")],
)
def test_mime_to_ext_map(workspace: Path, mime: str, ext: str) -> None:
    out = save_data_url(_data_url(mime, b"x"), workspace, 1)
    assert out == Path(f"_cursor_image_1.{ext}")
