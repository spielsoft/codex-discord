import http.client
import json
import math
import re
import socket
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Union
from urllib import error, parse, request

from .state import MAX_DELIVERED_EVENTS, RoutingState, RoutingStateTimeout


@dataclass(frozen=True)
class DeliveryPolicy:
    """Hard bounds for one best-effort delivery operation."""

    max_attempts: int = 3
    request_timeout_seconds: float = 2.0
    delivery_timeout_seconds: float = 6.0
    max_retry_delay_seconds: float = 2.0

    def validate(self) -> None:
        if not isinstance(self.max_attempts, int) or self.max_attempts < 1:
            raise ValueError("max attempts must be a positive integer")
        for name, value in (
            ("request timeout", self.request_timeout_seconds),
            ("delivery timeout", self.delivery_timeout_seconds),
            ("maximum retry delay", self.max_retry_delay_seconds),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")


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
DISCORD_USER_AGENT = "DiscordBot (https://github.com/openai/codex, 0.1)"
DISCORD_USER_ID = re.compile(r"[0-9]{17,20}\Z")
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WHITESPACE = re.compile(r"\s+")
ZERO_WIDTH_SPACE = "\u200b"
STALE_THREAD_STATUSES = frozenset((403, 404))
TRANSIENT_HTTP_STATUSES = frozenset((408, 425, 429))


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


def _event_id(notification: Mapping[str, object]) -> Optional[str]:
    value = notification.get("event_id")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("event_id must be a non-empty string when provided")
    normalized = value.strip()
    if len(normalized) > 512:
        raise ValueError("event_id must not exceed 512 characters")
    return normalized


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


def _request_payload(
    endpoint: str,
    thread_id: Optional[str],
    payload: Mapping[str, object],
) -> request.Request:
    return request.Request(
        _discord_endpoint(endpoint, thread_id),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": DISCORD_USER_AGENT,
        },
        method="POST",
    )


def _retry_delay(
    http_error: error.HTTPError,
    attempt: int,
    maximum_delay: float,
) -> float:
    retry_after = http_error.headers.get("Retry-After")
    if retry_after is None:
        retry_after = http_error.headers.get("X-RateLimit-Reset-After")

    if retry_after is None and http_error.code == 429:
        try:
            response_body = json.load(http_error)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            response_body = {}
        if isinstance(response_body, Mapping):
            retry_after = response_body.get("retry_after")

    try:
        delay = float(retry_after) if retry_after is not None else 0.25 * 2 ** (
            attempt - 1
        )
    except (TypeError, ValueError, OverflowError):
        delay = 0.25 * 2 ** (attempt - 1)
    if not math.isfinite(delay) or delay < 0:
        delay = 0.25 * 2 ** (attempt - 1)
    return min(delay, maximum_delay)


def _failure_result(
    session_id: str,
    attempts: int,
    diagnostic: str,
    retryable: bool,
) -> Mapping[str, object]:
    return {
        "session_id": session_id,
        "status": "delivery-failed",
        "attempts": attempts,
        "retryable": retryable,
        "diagnostic": diagnostic,
    }


def _success_result(
    session_id: str,
    thread_id: str,
    attempts: int,
    route_recovered: bool,
) -> Mapping[str, object]:
    result = {
        "session_id": session_id,
        "status": "published",
        "thread_id": thread_id,
    }
    if attempts > 1:
        result["attempts"] = attempts
    if route_recovered:
        result["route_recovered"] = True
    return result


def _sleep_for_retry(
    delay: float,
    deadline: float,
) -> bool:
    remaining = deadline - time.monotonic()
    if remaining <= 0 or delay >= remaining:
        return False
    if delay:
        time.sleep(delay)
    return True


def _read_response(http_response: object) -> Mapping[str, object]:
    response_body = json.load(http_response)
    if not isinstance(response_body, Mapping):
        raise ValueError("Discord returned an invalid success response")
    return response_body


def publish_notification(
    notification: Mapping[str, object],
    endpoint: str,
    state_file: Union[str, Path],
    mention_user_id: Optional[str] = None,
    milestones_enabled: bool = False,
    delivery_policy: Optional[DeliveryPolicy] = None,
) -> Mapping[str, object]:
    if not isinstance(notification, Mapping):
        raise TypeError("notification must be a JSON object")

    policy = delivery_policy or DeliveryPolicy()
    policy.validate()
    status = _status(notification)
    event_id = _event_id(notification)
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

    session_id = values["session_id"]
    deadline = time.monotonic() + policy.delivery_timeout_seconds
    attempts = 0
    route_recovered = False
    try:
        with RoutingState(state_file).locked_state(
            timeout_seconds=policy.delivery_timeout_seconds
        ) as state:
            routes = state["routes"]
            delivered_events = state["delivered_events"]
            if not isinstance(routes, dict) or not isinstance(
                delivered_events, list
            ):
                raise ValueError("routing state is invalid")
            if event_id is not None and event_id in delivered_events:
                duplicate = {
                    "session_id": session_id,
                    "status": "duplicate",
                }
                existing_thread = routes.get(session_id)
                if isinstance(existing_thread, str):
                    duplicate["thread_id"] = existing_thread
                return duplicate
            thread_id = routes.get(session_id)
            while attempts < policy.max_attempts:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return _failure_result(
                        session_id,
                        attempts,
                        "Discord delivery timed out before another attempt.",
                        True,
                    )

                payload = dict(common_payload)
                if thread_id is None:
                    payload["thread_name"] = _thread_name(
                        values["task_title"],
                        values["project"],
                    )
                replacement_attempt = route_recovered and thread_id is None
                http_request = _request_payload(endpoint, thread_id, payload)
                attempts += 1

                try:
                    with request.urlopen(
                        http_request,
                        timeout=min(policy.request_timeout_seconds, remaining),
                    ) as response:
                        response_body = _read_response(response)
                except error.HTTPError as exc:
                    if (
                        thread_id is not None
                        and not route_recovered
                        and exc.code in STALE_THREAD_STATUSES
                    ):
                        routes.pop(session_id, None)
                        thread_id = None
                        route_recovered = True
                        if attempts < policy.max_attempts:
                            continue
                        return _failure_result(
                            session_id,
                            attempts,
                            "Discord thread route was stale and the attempt limit "
                            "prevented replacement.",
                            True,
                        )

                    transient = (
                        exc.code in TRANSIENT_HTTP_STATUSES
                        or 500 <= exc.code <= 599
                    )
                    if replacement_attempt:
                        failure_kind = "transient " if transient else ""
                        return _failure_result(
                            session_id,
                            attempts,
                            "Discord replacement thread creation returned "
                            f"{failure_kind}HTTP {exc.code}; the route remains "
                            "cleared.",
                            transient,
                        )
                    if not transient:
                        return _failure_result(
                            session_id,
                            attempts,
                            f"Discord returned HTTP {exc.code}; notification was "
                            "not delivered.",
                            False,
                        )
                    if attempts >= policy.max_attempts:
                        return _failure_result(
                            session_id,
                            attempts,
                            f"Discord returned transient HTTP {exc.code} after "
                            f"{attempts} attempts.",
                            True,
                        )
                    delay = _retry_delay(
                        exc,
                        attempts,
                        policy.max_retry_delay_seconds,
                    )
                    if not _sleep_for_retry(delay, deadline):
                        return _failure_result(
                            session_id,
                            attempts,
                            "Discord delivery timed out while waiting to retry.",
                            True,
                        )
                    continue
                except (socket.timeout, TimeoutError):
                    if replacement_attempt:
                        return _failure_result(
                            session_id,
                            attempts,
                            "Discord replacement thread creation timed out; the "
                            "route remains cleared.",
                            True,
                        )
                    if attempts >= policy.max_attempts:
                        return _failure_result(
                            session_id,
                            attempts,
                            f"Discord delivery timed out after {attempts} attempts.",
                            True,
                        )
                    if not _sleep_for_retry(
                        min(
                            0.25 * 2 ** (attempts - 1),
                            policy.max_retry_delay_seconds,
                        ),
                        deadline,
                    ):
                        return _failure_result(
                            session_id,
                            attempts,
                            "Discord delivery timed out before another attempt.",
                            True,
                        )
                    continue
                except (error.URLError, OSError, http.client.HTTPException):
                    if replacement_attempt:
                        return _failure_result(
                            session_id,
                            attempts,
                            "Discord replacement thread connection failed; the "
                            "route remains cleared.",
                            True,
                        )
                    if attempts >= policy.max_attempts:
                        return _failure_result(
                            session_id,
                            attempts,
                            f"Discord connection failed after {attempts} attempts.",
                            True,
                        )
                    if not _sleep_for_retry(
                        min(
                            0.25 * 2 ** (attempts - 1),
                            policy.max_retry_delay_seconds,
                        ),
                        deadline,
                    ):
                        return _failure_result(
                            session_id,
                            attempts,
                            "Discord delivery timed out before another attempt.",
                            True,
                        )
                    continue
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                    if replacement_attempt:
                        return _failure_result(
                            session_id,
                            attempts,
                            "Discord replacement thread returned an invalid "
                            "success response; the route remains cleared.",
                            False,
                        )
                    return _failure_result(
                        session_id,
                        attempts,
                        "Discord returned an invalid success response.",
                        False,
                    )

                if thread_id is None:
                    returned_thread_id = response_body.get("channel_id")
                    if (
                        not isinstance(returned_thread_id, str)
                        or not returned_thread_id
                    ):
                        return _failure_result(
                            session_id,
                            attempts,
                            (
                                "Discord replacement thread response did not "
                                "include an identity; the route remains cleared."
                                if replacement_attempt
                                else "Discord success response did not include a "
                                "thread identity."
                            ),
                            False,
                        )
                    thread_id = returned_thread_id
                    routes[session_id] = thread_id

                if event_id is not None:
                    delivered_events.append(event_id)
                    del delivered_events[:-MAX_DELIVERED_EVENTS]

                return _success_result(
                    session_id,
                    thread_id,
                    attempts,
                    route_recovered,
                )
    except RoutingStateTimeout:
        return _failure_result(
            session_id,
            attempts,
            "Routing state remained busy until the delivery timeout.",
            True,
        )

    return _failure_result(
        session_id,
        attempts,
        "Discord delivery stopped at the configured attempt limit.",
        True,
    )


def publish_completion(
    notification: Mapping[str, object],
    endpoint: str,
    state_file: Union[str, Path],
) -> Mapping[str, object]:
    """Backward-compatible name for the original completion-only interface."""
    return publish_notification(notification, endpoint, state_file)
