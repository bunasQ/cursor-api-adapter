<div align="center">

<img src="./assets/logo.png" alt="cursor-api-adapter" width="120" />

# cursor-api-adapter

**Run Cursor's Composer models inside [`mini-swe-agent`](https://github.com/SWE-agent/mini-swe-agent).**
Drop-in model adapter for the official `cursor-agent` CLI. Also usable as a standalone Python client.

[![CI](https://img.shields.io/github/actions/workflow/status/bunasQ/cursor-api-adapter/ci.yml?branch=main&style=flat-square&label=ci)](https://github.com/bunasQ/cursor-api-adapter/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-3b82f6.svg?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-3b82f6.svg?style=flat-square)](./LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg?style=flat-square)](#status)

</div>

---

## Quick start

```python
from cursor_api_adapter import CursorAgentClient

client = CursorAgentClient(model="composer-2.5", workspace=".")
client.healthcheck()

print(client.chat("Write a haiku about subprocess.run.").text)
print(client.chat("Now translate it to French.").text)  # auto-resumes
```

The first `chat()` mints a server-side session. Every subsequent call resumes it, so Cursor keeps the conversation context (and caches prompts) on its side — second-call input cost drops by an order of magnitude.

## Motivation

I was building an eval harness for UI-layout replication and wanted to put Cursor's `composer-2.5` head-to-head with Claude Opus 4.7, GPT-5.5, and Gemini 3.1 on the same tasks. The harness uses [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) for the agent loop. Mini-swe-agent has a pluggable Model interface but only ships LiteLLM-backed adapters — and Cursor doesn't expose Composer over any API LiteLLM supports.

The only programmatic path to Cursor's models is `cursor-agent`, their official CLI. So I wrote this adapter: a Python wrapper that makes `cursor-agent` look like a regular language model client, plus a drop-in mini-swe-agent module so Composer fits anywhere LiteLLM would.

If you also want to test Cursor's models inside an existing agent harness — or just call them from a Python script without spinning up the IDE — this is for you.

## Install

Not on PyPI yet — install straight from GitHub:

```bash
pip install git+https://github.com/bunasQ/cursor-api-adapter.git

# with the mini-swe-agent adapter
pip install "cursor-api-adapter[minisweagent] @ git+https://github.com/bunasQ/cursor-api-adapter.git"
```

**Zero runtime dependencies** in the core library — pure standard library.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | uses `X \| None`, `match`, `dataclass(slots=True)` |
| `cursor-agent` binary on `$PATH` | [install docs](https://docs.cursor.com/cli) |
| `CURSOR_API_KEY` env var | the adapter never reads it — `cursor-agent` does |

Verify everything is wired up with one call:

```python
CursorAgentClient().healthcheck()  # raises a typed error if anything's off
```

## Models

Any model the CLI accepts. Run `cursor-agent --print --model help` while authed to see the full roster. Notable picks:

| Model | Provider | Notes |
|---|---|---|
| `composer-2.5` | Cursor | their flagship coding model (May 2026) |
| `composer-2.5-fast` | Cursor | faster, slightly cheaper |
| `claude-opus-4-7-high` | Anthropic | via Cursor's gateway |
| `gpt-5.5-high` | OpenAI | via Cursor's gateway |
| `gemini-3.1-pro` | Google | via Cursor's gateway |
| `kimi-k2.5` | Moonshot | via Cursor's gateway |
| `grok-4.3` | xAI | via Cursor's gateway |

Pass at the client level or per call:

```python
client = CursorAgentClient(model="composer-2.5")
client.chat("...")                              # uses composer-2.5
client.chat("...", model="claude-opus-4-7-high") # one-off override
```

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

## Multimodal — image input

Materialize images into the workspace and reference them by relative path in your prompt. Both `data:` URLs and local file paths work:

```python
client = CursorAgentClient(workspace="./agent_cwd")
client.healthcheck()

img = client.attach_image("./design.png")   # copies into workspace, returns Path
print(client.chat(f"Look at ./{img} and describe the layout.").text)
```

Data URLs are decoded and written as `_cursor_image_<N>.<ext>` (png/jpg/webp). File paths are copied in with the same naming scheme.

## mini-swe-agent integration

Drop the `CursorCLIModel` into a mini-swe-agent YAML config — it's a one-line swap:

```yaml
model:
  model_class: cursor_api_adapter.adapters.minisweagent.CursorCLIModel
  model_name: composer-2.5
  workspace: /path/to/agent/cwd
  multimodal_regex: "(?s)<MSWEA_MULTIMODAL_CONTENT><CONTENT_TYPE>(.+?)</CONTENT_TYPE>(.+?)</MSWEA_MULTIMODAL_CONTENT>"
```

The adapter bundles the first turn into a `[SYSTEM] / [USER] / [HARNESS NOTE]` block, rewrites embedded image tags into file-path references, and reshapes Cursor's response into the dict shape mini-swe-agent expects. Install with the extra: `pip install "cursor-api-adapter[minisweagent] @ git+https://github.com/bunasQ/cursor-api-adapter.git"`.

## API surface

```python
from cursor_api_adapter import (
    CursorAgentClient,          # the client
    CursorAgentResponse,        # what chat()/resume() return
    Usage,                      # token counts (no $)
    StreamEvent,                # what stream() yields
    CursorAgentError,           # base exception
    CursorAgentNotFoundError,   # binary missing
    CursorAgentAuthError,       # CURSOR_API_KEY missing
    CursorAgentTimeout,         # subprocess timeout
    CursorAgentInvocationError, # nonzero exit (.returncode/.stdout/.stderr)
    CursorAgentStreamError,     # malformed stream-json
)
```

## Limitations

- **No dollar cost.** Cursor's CLI doesn't return monetary cost. The adapter tracks `input_tokens`, `output_tokens`, and `cache_read_tokens` via the `Usage` dataclass — compute dollars yourself with Cursor's published rates if you need them.
- **One session per client.** A `CursorAgentClient` instance owns one session id; for parallel work, spin up multiple clients.
- **`stream()` timeout** bounds the post-stream wait only. A process that produces stdout slowly can exceed the configured `timeout` without raising. (Fixing in `0.2.x`.)

## Status

Alpha — `0.x`. API may change between minor versions. Pin to `==0.1.*` if that scares you.

## Development

```bash
git clone https://github.com/bunasQ/cursor-api-adapter
cd cursor-api-adapter
pip install -e ".[dev,minisweagent]"

pytest                         # unit tests (53 passing, 1 skipped)
CURSOR_ADAPTER_LIVE=1 pytest   # also hit the live cursor-agent
ruff check .
ruff format --check .
```

## License

MIT — see [LICENSE](./LICENSE).
Copyright © 2026 [Sergey Bunas](mailto:sergey@21st.dev).

## Contributing

Issues and PRs welcome at [github.com/bunasQ/cursor-api-adapter](https://github.com/bunasQ/cursor-api-adapter).
