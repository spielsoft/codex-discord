import json
import re
import unicodedata
from pathlib import Path
from typing import Mapping, Optional, Union
from urllib import error, parse, request

from .state import RoutingState


class PublishError(RuntimeError):
    """A notification could not be published."""


REQUIRED_FIELDS = (
    "session_id",
    "task_title",
    "project",
    "result",
    "validation",
)

STATUS_PRESENTATION = {
    "completed": ("🟢", "Completed", False),
    "needs-input": ("🟠", "Needs input", True),
    "blocked": ("🔴", "Blocked", True),
    "failed": ("❌", "Failed", True),
    "milestone": ("🔵", "Milestone", False),
}

FIELD_LIMITS = {
    "task_title": 256,
    "project": 128,
    "result": 768,
    "validation": 512,
    "next_action": 192,
}

DISCORD_CONTENT_LIMIT = 2000
DISCORD_THREAD_NAME_LIMIT = 100
DISCORD_USER_ID = re.compile(r"[0-9]{17,20}\Z")
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WHITESPACE = re.compile(r"\s+")
ZERO_WIDTH_SPACE = "\u200b"


def _utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _truncate(value: str, limit: int) -> str:
    if _utf16_length(value) <= limit:
        return value

    ellipsis = "…"
    available = limit - _utf16_length(ellipsis)
    result = []
    used = 0
    for character in value:
        character_length = _utf16_length(character)
        if used + character_length > available:
            break
        result.append(character)
        used += character_length
    return "".join(result).rstrip() + ellipsis


def _sanitize_mentions(value: str) -> str:
    return value.replace("@", f"@{ZERO_WIDTH_SPACE}").replace(
        "<#", f"<{ZERO_WIDTH_SPACE}#"
    )


def _normalize_text(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a non-empty string")
    scalar_text = "".join(
        "\ufffd" if 0xD800 <= ord(character) <= 0xDFFF else character
        for character in value
    )
    normalized = unicodedata.normalize("NFC", scalar_text)
    normalized = CONTROL_CHARACTERS.sub(" ", normalized)
    normalized = WHITESPACE.sub(" ", normalized).strip()
    if not normalized:
        raise ValueError(f"{field} must be a non-empty string")
    return _truncate(_sanitize_mentions(normalized), limit)


def _required_text(notification: Mapping[str, object], field: str) -> str:
    if field == "session_id":
        value = notification.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
        return value.strip()
    limit = FIELD_LIMITS.get(field, 256)
    return _normalize_text(notification.get(field), field, limit)


def _status(notification: Mapping[str, object]) -> str:
    value = notification.get("status", "completed")
    if not isinstance(value, str) or value not in STATUS_PRESENTATION:
        choices = ", ".join(STATUS_PRESENTATION)
        raise ValueError(f"status must be one of: {choices}")
    return value


def _mention_user_id(value: Optional[str], attention: bool) -> Optional[str]:
    if value is None:
        if attention:
            raise ValueError("mention user ID is required for attention statuses")
        return None
    if not isinstance(value, str) or not DISCORD_USER_ID.fullmatch(value):
        raise ValueError("mention user ID must be a Discord user ID")
    return value


def _discord_endpoint(endpoint: str, thread_id: Optional[str] = None) -> str:
    parts = parse.urlsplit(endpoint)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("endpoint must be an HTTP or HTTPS URL")
    query = parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [
        (key, value) for key, value in query if key not in ("thread_id", "wait")
    ]
    if thread_id is not None:
        query.append(("thread_id", thread_id))
    query.append(("wait", "true"))
    return parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, parse.urlencode(query), parts.fragment)
    )


def _message(
    status: str,
    task_title: str,
    project: str,
    result: str,
    validation: str,
    next_action: Optional[str],
    mention_user_id: Optional[str],
) -> str:
    icon, label, attention = STATUS_PRESENTATION[status]
    lines = [
        f"{icon} {label} — {task_title}",
        "",
        f"Project: {project}",
        f"Result: {result}",
        f"Checks: {validation}",
    ]
    if next_action:
        lines.append(f"Next: {next_action}")
    content = "\n".join(lines)
    if attention:
        content = f"<@{mention_user_id}>\n{content}"
    if _utf16_length(content) > DISCORD_CONTENT_LIMIT:
        raise ValueError("formatted notification exceeds Discord's message limit")
    return content


def _thread_name(task_title: str, project: str) -> str:
    separator = " — "
    project_budget = min(32, _utf16_length(project))
    project_part = _truncate(project, project_budget)
    title_budget = (
        DISCORD_THREAD_NAME_LIMIT
        - _utf16_length(separator)
        - _utf16_length(project_part)
    )
    title_part = _truncate(task_title, title_budget)
    return f"{title_part}{separator}{project_part}"


def _allowed_mentions(
    mention_user_id: Optional[str], attention: bool
) -> Mapping[str, object]:
    return {
        "parse": [],
        "users": [mention_user_id] if attention else [],
        "roles": [],
        "replied_user": False,
    }


def publish_notification(
    notification: Mapping[str, object],
    endpoint: str,
    state_file: Union[str, Path],
    mention_user_id: Optional[str] = None,
    milestones_enabled: bool = False,
) -> Mapping[str, str]:
    if not isinstance(notification, Mapping):
        raise TypeError("notification must be a JSON object")

    status = _status(notification)
    values = {field: _required_text(notification, field) for field in REQUIRED_FIELDS}
    raw_next_action = notification.get("next_action")
    if raw_next_action is not None and not isinstance(raw_next_action, str):
        raise ValueError("next_action must be a string when provided")
    next_action = (
        _normalize_text(
            raw_next_action,
            "next_action",
            FIELD_LIMITS["next_action"],
        )
        if raw_next_action and raw_next_action.strip()
        else None
    )

    _, _, attention = STATUS_PRESENTATION[status]
    configured_user_id = _mention_user_id(mention_user_id, attention)

    if status == "milestone" and not milestones_enabled:
        return {
            "session_id": values["session_id"],
            "status": "suppressed",
        }

    common_payload = {
        "content": _message(
            status,
            values["task_title"],
            values["project"],
            values["result"],
            values["validation"],
            next_action,
            configured_user_id,
        ),
        "allowed_mentions": _allowed_mentions(
            configured_user_id,
            attention,
        ),
    }

    with RoutingState(state_file).locked_routes() as routes:
        thread_id = routes.get(values["session_id"])
        payload = dict(common_payload)
        if thread_id is None:
            payload["thread_name"] = _thread_name(
                values["task_title"],
                values["project"],
            )

        http_request = request.Request(
            _discord_endpoint(endpoint, thread_id),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=10) as response:
                response_body = json.load(response)
        except (
            error.HTTPError,
            error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as exc:
            raise PublishError(str(exc)) from exc

        if thread_id is None:
            thread_id = response_body.get("channel_id")
            if not isinstance(thread_id, str) or not thread_id:
                raise PublishError(
                    "Discord response did not include a thread identity"
                )
            routes[values["session_id"]] = thread_id

    return {
        "session_id": values["session_id"],
        "status": "published",
        "thread_id": thread_id,
    }


def publish_completion(
    notification: Mapping[str, object],
    endpoint: str,
    state_file: Union[str, Path],
) -> Mapping[str, str]:
    """Backward-compatible name for the original completion-only interface."""
    return publish_notification(notification, endpoint, state_file)
