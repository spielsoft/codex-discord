"""Best-effort Codex Stop hook for completed-turn notifications.

The hook intentionally produces no stdout and always exits successfully. A
Discord or local-configuration failure must never replace the Codex turn's
result.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from .publisher import publish_notification


WEBHOOK_ENVIRONMENT = "CODEX_DISCORD_WEBHOOK_URL"
STATE_ENVIRONMENT = "CODEX_DISCORD_STATE_FILE"
GENERIC_TASK_TITLE = "Codex task"
GENERIC_COMPLETION_RESULT = "Codex turn completed"
STOP_VALIDATION = "Codex reported a completed turn."
DISCORD_WEBHOOK_PATTERN = re.compile(
    r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\S+",
    re.IGNORECASE,
)
CREDENTIAL_PATTERN = re.compile(
    r"\b(?:token|secret|password)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def _safe_diagnostic(message: str) -> None:
    print(f"codex-discord Stop hook: {message}", file=sys.stderr)


def _required_string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid {field}")
    return value.strip()


def _completion_result(value: Any) -> str:
    if not isinstance(value, str):
        return GENERIC_COMPLETION_RESULT
    sanitized = DISCORD_WEBHOOK_PATTERN.sub("<redacted-webhook>", value)
    sanitized = CREDENTIAL_PATTERN.sub("<redacted-credential>", sanitized)
    normalized = unicodedata.normalize("NFC", sanitized)
    if not any(
        not character.isspace()
        and not unicodedata.category(character).startswith("C")
        for character in normalized
    ):
        return GENERIC_COMPLETION_RESULT
    return sanitized


def _notification_from_stop(payload: Mapping[str, Any]) -> Mapping[str, str]:
    if payload.get("hook_event_name") != "Stop":
        raise ValueError("unsupported lifecycle event")

    session_id = _required_string(payload, "session_id")
    cwd = _required_string(payload, "cwd")
    project = Path(cwd).name
    if not project:
        raise ValueError("invalid cwd")

    return {
        "session_id": session_id,
        "status": "completed",
        "task_title": GENERIC_TASK_TITLE,
        "project": project,
        "result": _completion_result(payload.get("last_assistant_message")),
        "validation": STOP_VALIDATION,
    }


def _default_state_file() -> Path:
    return Path.home() / ".codex" / "codex-discord" / "routing.json"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, Mapping):
            raise ValueError("hook input must be a JSON object")
        notification = _notification_from_stop(payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        _safe_diagnostic("ignored invalid lifecycle input.")
        return 0

    endpoint = os.environ.get(WEBHOOK_ENVIRONMENT)
    if not endpoint or not endpoint.strip():
        _safe_diagnostic("skipped because the webhook is not configured.")
        return 0

    configured_state_file = os.environ.get(STATE_ENVIRONMENT)
    state_file = (
        Path(configured_state_file).expanduser()
        if configured_state_file and configured_state_file.strip()
        else _default_state_file()
    )

    try:
        outcome = publish_notification(
            notification,
            endpoint,
            state_file,
        )
        if outcome.get("status") != "published":
            _safe_diagnostic("Discord delivery failed; the Codex turn is unchanged.")
    except Exception:
        _safe_diagnostic("notification was not delivered; the Codex turn is unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
