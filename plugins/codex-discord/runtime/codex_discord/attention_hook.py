"""Best-effort attention delivery for supported Codex lifecycle inputs.

This adapter is notification-only. It emits no hook decision and always exits
successfully, so it cannot approve, deny, or otherwise control Codex.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

from .publisher import publish_notification


WEBHOOK_ENVIRONMENT = "CODEX_DISCORD_WEBHOOK_URL"
STATE_ENVIRONMENT = "CODEX_DISCORD_STATE_FILE"
MENTION_ENVIRONMENT = "CODEX_DISCORD_MENTION_USER_ID"
GENERIC_TASK_TITLE = "Codex task"
PERMISSION_VALIDATION = "Codex is awaiting a permission decision."
PERMISSION_NEXT_ACTION = "Review the request in Codex."
NORMALIZED_EVENT = "CodexDiscordAttention"
SUPPORTED_NORMALIZED_STATUSES = frozenset(("blocked", "failed"))
DISCORD_WEBHOOK_PATTERN = re.compile(
    r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\S+",
    re.IGNORECASE,
)
CREDENTIAL_PATTERN = re.compile(
    r"\b(?:token|secret|password)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def _safe_diagnostic(message: str) -> None:
    print(f"codex-discord attention hook: {message}", file=sys.stderr)


def _required_string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid {field}")
    return value.strip()


def _optional_string(payload: Mapping[str, Any], field: str) -> Optional[str]:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"invalid {field}")
    return value.strip() or None


def _redact(value: str) -> str:
    value = DISCORD_WEBHOOK_PATTERN.sub("<redacted-webhook>", value)
    return CREDENTIAL_PATTERN.sub("<redacted-credential>", value)


def _event_identity(*parts: str) -> str:
    encoded = json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode()
    return f"lifecycle:{hashlib.sha256(encoded).hexdigest()}"


def _tool_input_identity(payload: Mapping[str, Any]) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        raise ValueError("invalid tool_input")
    encoded = json.dumps(
        tool_input,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _project(payload: Mapping[str, Any]) -> str:
    cwd = _required_string(payload, "cwd")
    project = Path(cwd).name
    if not project:
        raise ValueError("invalid cwd")
    return project


def _permission_notification(
    payload: Mapping[str, Any],
) -> Mapping[str, str]:
    session_id = _required_string(payload, "session_id")
    turn_id = _required_string(payload, "turn_id")
    tool_name = _required_string(payload, "tool_name")
    return {
        "session_id": session_id,
        "event_id": _event_identity(
            session_id,
            turn_id,
            "PermissionRequest",
            tool_name,
            _tool_input_identity(payload),
        ),
        "status": "needs-input",
        "task_title": GENERIC_TASK_TITLE,
        "project": _project(payload),
        "result": f"Codex requested permission for {_redact(tool_name)}.",
        "validation": PERMISSION_VALIDATION,
        "next_action": PERMISSION_NEXT_ACTION,
    }


def _normalized_attention_notification(
    payload: Mapping[str, Any],
) -> Mapping[str, str]:
    session_id = _required_string(payload, "session_id")
    turn_id = _required_string(payload, "turn_id")
    status = _required_string(payload, "status")
    if status not in SUPPORTED_NORMALIZED_STATUSES:
        raise ValueError("unsupported attention status")

    notification = {
        "session_id": session_id,
        "event_id": _event_identity(
            session_id,
            turn_id,
            NORMALIZED_EVENT,
            status,
        ),
        "status": status,
        "task_title": GENERIC_TASK_TITLE,
        "project": _project(payload),
        "result": _redact(_required_string(payload, "summary")),
        "validation": _redact(_required_string(payload, "validation")),
    }
    next_action = _optional_string(payload, "next_action")
    if next_action:
        notification["next_action"] = _redact(next_action)
    return notification


def notification_from_lifecycle(
    payload: Mapping[str, Any],
) -> Mapping[str, str]:
    event_name = payload.get("hook_event_name")
    if event_name == "PermissionRequest":
        return _permission_notification(payload)
    if event_name == NORMALIZED_EVENT:
        return _normalized_attention_notification(payload)
    raise ValueError("unsupported lifecycle event")


def _default_state_file() -> Path:
    return Path.home() / ".codex" / "codex-discord" / "routing.json"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, Mapping):
            raise ValueError("hook input must be a JSON object")
        notification = notification_from_lifecycle(payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        _safe_diagnostic("ignored invalid or unsupported lifecycle input.")
        return 0

    endpoint = os.environ.get(WEBHOOK_ENVIRONMENT)
    if not endpoint or not endpoint.strip():
        _safe_diagnostic("skipped because the webhook is not configured.")
        return 0
    mention_user_id = os.environ.get(MENTION_ENVIRONMENT)
    if not mention_user_id or not mention_user_id.strip():
        _safe_diagnostic("skipped because the mention user ID is not configured.")
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
            mention_user_id=mention_user_id,
        )
        if outcome.get("status") not in ("published", "duplicate"):
            _safe_diagnostic(
                "Discord delivery failed; the Codex request is unchanged."
            )
    except Exception:
        _safe_diagnostic(
            "notification was not delivered; the Codex request is unchanged."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
