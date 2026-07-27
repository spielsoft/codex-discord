import json
from pathlib import Path
from typing import Mapping, Optional, Union
from urllib import error, parse, request

from .state import RoutingState


class PublishError(RuntimeError):
    """A completion could not be published."""


REQUIRED_FIELDS = (
    "session_id",
    "task_title",
    "project",
    "result",
    "validation",
)


def _required_text(notification: Mapping[str, object], field: str) -> str:
    value = notification.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


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
    task_title: str,
    project: str,
    result: str,
    validation: str,
    next_action: Optional[str],
) -> str:
    lines = [
        f"🟢 Completed — {task_title}",
        "",
        f"Project: {project}",
        f"Result: {result}",
        f"Checks: {validation}",
    ]
    if next_action:
        lines.append(f"Next: {next_action}")
    return "\n".join(lines)


def publish_completion(
    notification: Mapping[str, object],
    endpoint: str,
    state_file: Union[str, Path],
) -> Mapping[str, str]:
    if not isinstance(notification, Mapping):
        raise TypeError("notification must be a JSON object")

    values = {field: _required_text(notification, field) for field in REQUIRED_FIELDS}
    raw_next_action = notification.get("next_action")
    if raw_next_action is not None and not isinstance(raw_next_action, str):
        raise ValueError("next_action must be a string when provided")
    next_action = raw_next_action.strip() if raw_next_action else None

    common_payload = {
        "content": _message(
            values["task_title"],
            values["project"],
            values["result"],
            values["validation"],
            next_action,
        ),
        "allowed_mentions": {"parse": []},
    }

    with RoutingState(state_file).locked_routes() as routes:
        thread_id = routes.get(values["session_id"])
        payload = dict(common_payload)
        if thread_id is None:
            payload["thread_name"] = (
                f"{values['task_title']} — {values['project']}"
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
