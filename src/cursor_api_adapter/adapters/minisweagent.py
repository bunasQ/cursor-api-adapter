"""mini-swe-agent model adapter for cursor-agent.

The ONLY module in this package that imports ``minisweagent``. All such
imports are deferred to function/class body so the base ``cursor-api-adapter``
install never touches mini-swe-agent.

YAML usage:

    model:
      model_class: cursor_api_adapter.adapters.minisweagent.CursorCLIModel
      model_name: composer-2.5
      workspace: /path/to/agent/cwd
      multimodal_regex: "(?s)<MSWEA_MULTIMODAL_CONTENT>..."
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from ..client import CursorAgentClient
from ..images import save_data_url

logger = logging.getLogger("cursor_cli_model")


@dataclass(slots=True)
class CursorCLIModelConfig:
    model_name: str = ""
    """Cursor-side model name. See `cursor-agent --print --model help` for the full list."""
    workspace: str = ""
    """Working directory passed to cursor-agent via --workspace."""
    cli_path: str = "cursor-agent"
    """Path to the cursor-agent binary."""
    extra_cli_args: list[str] = field(default_factory=list)
    """Extra args appended to every cursor-agent invocation."""
    timeout: int = 300
    """Hard timeout per cursor-agent call, seconds."""
    model_kwargs: dict[str, Any] = field(default_factory=dict)
    """Reserved for future use; currently ignored."""
    set_cache_control: str | None = None
    """Reserved; Cursor handles caching internally. Valid: "default_end" or None."""
    cost_tracking: str = "ignore_errors"
    """Reserved; Cursor doesn't return dollar costs. Valid: "default" or "ignore_errors"."""
    multimodal_regex: str = ""
    """If non-empty, extract embedded images from the first user message."""
    action_regex: str = r"```mswea_bash_command\s*\n(.*?)\n```"
    """Same default as LitellmTextbasedModel: how to extract the bash action."""
    format_error_template: str = (
        "Please always provide EXACTLY ONE action in triple backticks, "
        "found {{actions|length}} actions."
    )
    observation_template: str = (
        "{% if output.exception_info %}<exception>{{output.exception_info}}</exception>\n"
        "{% endif %}<returncode>{{output.returncode}}</returncode>\n"
        "<output>\n{{output.output}}</output>"
    )


class CursorCLIModel:
    """mini-swe-agent model wrapping CursorAgentClient."""

    abort_exceptions: list[type[Exception]] = [KeyboardInterrupt]

    def __init__(self, **kwargs: Any) -> None:
        known = {f.name for f in fields(CursorCLIModelConfig)}
        unknown = set(kwargs) - known
        if unknown:
            raise TypeError(f"Unknown CursorCLIModel kwargs: {sorted(unknown)}")
        self.config = CursorCLIModelConfig(**kwargs)
        if not self.config.model_name:
            raise ValueError("model_name is required for CursorCLIModel")
        self._image_counter: int = 0
        self._client = CursorAgentClient(
            model=self.config.model_name,
            workspace=self.config.workspace or None,
            cli_path=self.config.cli_path,
            timeout=float(self.config.timeout),
            extra_cli_args=tuple(self.config.extra_cli_args),
        )
        if not self.config.workspace:
            logger.warning(
                "CursorCLIModel: no workspace configured. cursor-agent will run in "
                "%s and may fail the trust check.",
                os.getcwd(),
            )

    # ------------------------------------------------------------------
    # Public interface (matches LitellmModel / LitellmTextbasedModel)
    # ------------------------------------------------------------------

    def query(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict:
        try:
            from minisweagent.models import GLOBAL_MODEL_STATS
            from minisweagent.models.utils.actions_text import parse_regex_actions
        except ImportError as e:
            raise ImportError(
                "mini-swe-agent is required for CursorCLIModel. "
                "Install with: pip install 'cursor-api-adapter[minisweagent]'"
            ) from e

        prompt = self._prompt_for_turn(messages)
        response = self._client.chat(prompt)

        actions = parse_regex_actions(
            response.text,
            action_regex=self.config.action_regex,
            format_error_template=self.config.format_error_template,
        )

        # Cursor CLI doesn't return dollar cost; report 0 so the agent's cost
        # tracker keeps working. Token counters are exposed via serialize().
        GLOBAL_MODEL_STATS.add(0.0)
        return {
            "role": "assistant",
            "content": response.text,
            "extra": {
                "actions": actions,
                "cost": 0.0,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_read_tokens": response.usage.cache_read_tokens,
                "cursor_session_id": self._client.session_id,
                "timestamp": time.time(),
            },
        }

    def format_message(self, **kwargs: Any) -> dict:
        """No multimodal expansion at this stage — images are rewritten to file
        paths when building the first prompt instead."""
        return dict(kwargs)

    def format_observation_messages(
        self,
        message: dict,
        outputs: list[dict],
        template_vars: dict | None = None,
    ) -> list[dict]:
        try:
            from minisweagent.models.utils.actions_text import format_observation_messages
        except ImportError as e:
            raise ImportError(
                "mini-swe-agent is required for CursorCLIModel. "
                "Install with: pip install 'cursor-api-adapter[minisweagent]'"
            ) from e

        return format_observation_messages(
            outputs,
            observation_template=self.config.observation_template,
            template_vars=template_vars,
            multimodal_regex="",
        )

    def get_template_vars(self, **kwargs: Any) -> dict[str, Any]:
        return _config_to_dict(self.config)

    def serialize(self) -> dict:
        usage = self._client.total_usage
        return {
            "info": {
                "config": {
                    "model": _config_to_dict(self.config),
                    "model_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                },
                "cursor": {
                    "session_id": self._client.session_id,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cache_read_tokens": usage.cache_read_tokens,
                },
            }
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _prompt_for_turn(self, messages: list[dict[str, Any]]) -> str:
        if self._client.session_id is None:
            return self._build_first_prompt(messages)
        return self._message_to_text(messages[-1])

    def _build_first_prompt(self, messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for m in messages:
            role = m.get("role", "user")
            text = self._message_to_text(m, save_images=True)
            if not text:
                continue
            label = {"system": "SYSTEM", "user": "USER"}.get(role, role.upper())
            parts.append(f"[{label}]\n{text}")
        parts.append(
            "[HARNESS NOTE]\n"
            "You are a planner inside another harness. The harness will execute\n"
            "your bash command and feed back the output. Respond with reasoning\n"
            "followed by ONE ```mswea_bash_command block. Do NOT use your own\n"
            "shell/edit tools."
        )
        return "\n\n".join(parts)

    def _message_to_text(
        self,
        message: dict[str, Any],
        *,
        save_images: bool = False,
    ) -> str:
        content = message.get("content")
        if content is None:
            return ""
        if isinstance(content, str):
            return self._rewrite_image_tags(content, save_images=save_images)
        if isinstance(content, list):
            chunks: list[str] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    chunks.append(
                        self._rewrite_image_tags(part.get("text", ""), save_images=save_images)
                    )
                elif part.get("type") == "image_url" and save_images:
                    url = (part.get("image_url") or {}).get("url", "")
                    saved = self._save_data_url(url)
                    if saved:
                        chunks.append(f"[image attached at ./{saved}]")
            return "\n".join(c for c in chunks if c)
        return str(content)

    def _rewrite_image_tags(self, text: str, *, save_images: bool) -> str:
        """Convert <MSWEA_MULTIMODAL_CONTENT> tags into file-path references."""
        if not self.config.multimodal_regex or not text:
            return text
        pattern = re.compile(self.config.multimodal_regex)

        def replace(match: re.Match) -> str:
            content_type = (match.group(1) or "").strip()
            payload = (match.group(2) or "").strip()
            if content_type != "image_url" or not save_images:
                return ""
            saved = self._save_data_url(payload)
            if not saved:
                return ""
            return f"[image attached at ./{saved} — read this file to see the design]"

        return pattern.sub(replace, text)

    def _save_data_url(self, url: str) -> str | None:
        if not url.startswith("data:"):
            return None
        if not self.config.workspace:
            return None
        self._image_counter += 1
        saved = save_data_url(
            url,
            Path(self.config.workspace),
            self._image_counter,
            prefix="_mswea_image",
        )
        return saved.name if saved else None


def _config_to_dict(cfg: CursorCLIModelConfig) -> dict[str, Any]:
    return {f.name: getattr(cfg, f.name) for f in fields(cfg)}
