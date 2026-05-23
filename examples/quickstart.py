"""Mint a session, send two prompts, and let the second one auto-resume.

Prereqs:
    - cursor-agent on $PATH
    - CURSOR_API_KEY exported
"""

from cursor_api_adapter import CursorAgentClient


def main() -> None:
    client = CursorAgentClient(model="composer-2.5", workspace=".")
    client.healthcheck()

    print(client.chat("Write a haiku about subprocess.run.").text)
    print(client.chat("Now translate it to French.").text)  # auto-resumes

    print()
    print("session_id:", client.session_id)
    print("total_usage:", client.total_usage)


if __name__ == "__main__":
    main()
