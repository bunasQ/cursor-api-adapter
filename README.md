# cursor-api-adapter

Pythonic client for Cursor's `cursor-agent` CLI.

## What it is

`cursor-api-adapter` wraps the official `cursor-agent` binary as a Python library. It gives you a small, synchronous `CursorAgentClient` that mints and resumes server-side sessions, parses Cursor's `stream-json` output into typed dataclasses, and exposes a drop-in `mini-swe-agent` model adapter.

## Why it exists

Cursor doesn't ship a public HTTP API. The `cursor-agent` CLI is the only programmatic surface for talking to Cursor's hosted models (`composer-2.5`, `gpt-5.5-high`, `claude-opus-4-7-medium`, `gemini-3.1-pro`, `kimi-k2.5`, ...). This library wraps the subprocess + stream-json plumbing so you don't have to.

## Status

Alpha (`0.x`). API may change.

## Install

```bash
pip install cursor-api-adapter

# With the mini-swe-agent adapter:
pip install "cursor-api-adapter[minisweagent]"

# Development:
pip install "cursor-api-adapter[dev]"
```

## Prerequisites

- `cursor-agent` on `$PATH` (or pass `cli_path=`). See [Cursor's CLI install docs](https://docs.cursor.com/cli).
- `CURSOR_API_KEY` exported in your environment.

Verify with `CursorAgentClient.healthcheck()` — it checks the binary, the env var, and runs `cursor-agent --version`.

## Quickstart

```python
from cursor_api_adapter import CursorAgentClient

client = CursorAgentClient(model="composer-2.5", workspace=".")
client.healthcheck()

print(client.chat("Write a haiku about subprocess.run.").text)
print(client.chat("Now translate it to French.").text)  # auto-resumes
```

The first `chat()` mints a server-side session. Every subsequent `chat()` resumes it, so Cursor keeps the conversation context (and caches prompts) on its side.

## Authentication

Cursor reads `CURSOR_API_KEY` from the environment. The adapter never reads it — it just verifies presence at `healthcheck()` time and lets `cursor-agent` handle the rest.

```bash
export CURSOR_API_KEY="sk-..."
```

## Available models

Use any model name `cursor-agent` accepts. Run `cursor-agent --print --model help` to see the full list. Pass it as the `model=` constructor argument or per-call via `chat(prompt, model=...)`.

## Streaming

`client.stream(prompt)` yields parsed `StreamEvent`s as the CLI writes them:

```python
for event in client.stream("Explain how cursor-agent mints sessions."):
    if event.type == "assistant":
        for part in event.data["message"]["content"]:
            if part.get("type") == "text":
                print(part["text"], end="", flush=True)
print()
print("session_id:", client.session_id)
```

`session_id` is set the moment the `system/init` event arrives, so breaking out of the iterator early still preserves the session for the next `chat()` call.

## Multimodal / image input

Materialize images into the workspace and reference them by relative path in your prompt. Both `data:` URLs and local file paths work:

```python
from cursor_api_adapter import CursorAgentClient

client = CursorAgentClient(workspace="./agent_cwd")
client.healthcheck()

img_rel = client.attach_image("./design.png")   # copies into workspace, returns Path
prompt = (
    "Look at the file at "
    f"./{img_rel} and tell me what's in it."
)
print(client.chat(prompt).text)
```

Data URLs are decoded and written as `_cursor_image_<N>.<ext>` (png/jpg/webp). File paths are copied in with the same naming scheme.

## mini-swe-agent integration

Drop the `CursorCLIModel` into a mini-swe-agent YAML config:

```yaml
model:
  model_class: cursor_api_adapter.adapters.minisweagent.CursorCLIModel
  model_name: composer-2.5
  workspace: /path/to/agent/cwd
  multimodal_regex: "(?s)<MSWEA_MULTIMODAL_CONTENT type=\"([^\"]+)\">(.*?)</MSWEA_MULTIMODAL_CONTENT>"
```

The adapter bundles the first turn into a `[SYSTEM] / [USER] / [HARNESS NOTE]` block, rewrites embedded image tags into file-path references, and reshapes Cursor's response into the dict shape mini-swe-agent expects.

Install with the extra: `pip install "cursor-api-adapter[minisweagent]"`.

## Limitations

- No dollar cost. Cursor's CLI doesn't return monetary cost; the adapter tracks input/output/cache-read tokens via the `Usage` dataclass instead.
- No parallel requests on one client. A `CursorAgentClient` instance owns one session; if you need parallelism, create multiple clients.
- `stream()` timeout bounds the post-stream wait only. A process that produces stdout slowly can exceed the configured `timeout` without raising.

## License

MIT. See [LICENSE](./LICENSE).

## Contributing

Issues and PRs welcome at [github.com/bunasQ/cursor-api-adapter](https://github.com/bunasQ/cursor-api-adapter). Run the test suite with:

```bash
pip install -e ".[dev,minisweagent]"
pytest
ruff check .
ruff format --check .
```
