"""Attach a local PNG into the workspace and reference it by path in the prompt.

Pass the path to a PNG/JPG/WebP as ``sys.argv[1]``. The file is copied into the
workspace as ``_cursor_image_<N>.<ext>``; cursor-agent reads it from there.
"""

import sys
from pathlib import Path

from cursor_api_adapter import CursorAgentClient


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python multimodal.py <path-to-image>", file=sys.stderr)
        sys.exit(2)

    src = Path(sys.argv[1])
    workspace = Path("./agent_cwd").resolve()

    client = CursorAgentClient(model="composer-2.5", workspace=workspace)
    client.healthcheck()

    rel_path = client.attach_image(src)
    prompt = (
        f"Look at the image at ./{rel_path}. Describe what you see in one "
        "sentence, then list the dominant colors."
    )
    print(client.chat(prompt).text)


if __name__ == "__main__":
    main()
