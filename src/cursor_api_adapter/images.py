"""Helpers for materializing data: URLs into workspace files."""

from __future__ import annotations

import base64
from pathlib import Path

_MIME_TO_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


def save_data_url(
    url: str,
    workspace: Path,
    counter: int,
    prefix: str = "_cursor_image",
) -> Path | None:
    """Decode a data: URL and write it into `workspace` as `<prefix>_<counter>.<ext>`.

    Returns a Path containing just the filename (relative to `workspace`), or
    None if `url` is not a data URL or is malformed.
    """
    if not url.startswith("data:"):
        return None
    try:
        header, b64 = url.split(",", 1)
    except ValueError:
        return None
    mime = header.split(";")[0].removeprefix("data:") or "image/png"
    ext = _MIME_TO_EXT.get(mime, "png")
    workspace.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{counter}.{ext}"
    (workspace / filename).write_bytes(base64.b64decode(b64))
    return Path(filename)
