"""mini-swe-agent YAML config snippet.

Save the YAML below to a file (e.g. ``cursor.yaml``) and pass it to mini-swe-agent:

    mini-swe-agent --config cursor.yaml --task "..."

Install the adapter with the extra so mini-swe-agent itself is available:

    pip install "cursor-api-adapter[minisweagent]"
"""

_MULTIMODAL_REGEX = (
    r'"(?s)<MSWEA_MULTIMODAL_CONTENT type=\"([^\"]+)\">'
    r'(.*?)</MSWEA_MULTIMODAL_CONTENT>"'
)

CONFIG_YAML = f"""\
model:
  model_class: cursor_api_adapter.adapters.minisweagent.CursorCLIModel
  model_name: composer-2.5
  workspace: /path/to/agent/cwd
  cli_path: cursor-agent
  timeout: 300
  multimodal_regex: {_MULTIMODAL_REGEX}
"""


def main() -> None:
    print(CONFIG_YAML)


if __name__ == "__main__":
    main()
