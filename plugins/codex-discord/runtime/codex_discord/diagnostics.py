"""Local configuration checks and explicit opt-in delivery diagnostics."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping, MutableMapping, Optional, Tuple
from urllib import parse

from .publisher import (
    DEFAULT_DESTINATION_TYPE,
    DESTINATION_TYPES,
    DeliveryPolicy,
    publish_notification,
)
from .state import RoutingState


WEBHOOK_ENVIRONMENT = "CODEX_DISCORD_WEBHOOK_URL"
MENTION_ENVIRONMENT = "CODEX_DISCORD_MENTION_USER_ID"
STATE_ENVIRONMENT = "CODEX_DISCORD_STATE_FILE"
DESTINATION_ENVIRONMENT = "CODEX_DISCORD_DESTINATION_TYPE"
DISCORD_USER_ID = re.compile(r"[0-9]{17,20}\Z")
DISCORD_HOSTS = frozenset(
    (
        "discord.com",
        "canary.discord.com",
        "ptb.discord.com",
        "discordapp.com",
        "canary.discordapp.com",
        "ptb.discordapp.com",
    )
)
LOOPBACK_HOSTS = frozenset(("127.0.0.1", "::1", "localhost"))
HEALTH_SESSION_ID = "codex-discord-health-check"


def default_state_file() -> Path:
    return Path.home() / ".codex" / "codex-discord" / "routing.json"


def _configured_state_file(environment: Mapping[str, str]) -> Path:
    configured = environment.get(STATE_ENVIRONMENT, "")
    path = Path(configured).expanduser() if configured.strip() else default_state_file()
    return path.resolve(strict=False)


def _webhook_is_usable(value: str) -> bool:
    try:
        parts = parse.urlsplit(value)
        port = parts.port
    except ValueError:
        return False
    if parts.username or parts.password or not parts.hostname:
        return False
    host = parts.hostname.lower()
    if host in DISCORD_HOSTS:
        if parts.scheme != "https" or port not in (None, 443):
            return False
    elif host in LOOPBACK_HOSTS:
        if parts.scheme not in ("http", "https"):
            return False
    else:
        return False
    segments = parts.path.split("/")
    return (
        len(segments) == 5
        and segments[:3] == ["", "api", "webhooks"]
        and DISCORD_USER_ID.fullmatch(segments[3]) is not None
        and bool(segments[4])
    )


def _issue(code: str, message: str, action: str) -> Mapping[str, str]:
    return {"code": code, "message": message, "action": action}


def _inspect_configuration(
    environment: Mapping[str, str],
) -> Tuple[
    MutableMapping[str, str],
    list,
    Mapping[str, object],
    Optional[str],
    str,
]:
    checks: MutableMapping[str, str] = {}
    issues = []
    endpoint = environment.get(WEBHOOK_ENVIRONMENT, "")
    if not endpoint.strip():
        checks["webhook"] = "missing"
        issues.append(
            _issue(
                "webhook-missing",
                "The Discord webhook is not configured.",
                f"Set {WEBHOOK_ENVIRONMENT} to the incoming webhook URL.",
            )
        )
        usable_endpoint = None
    elif not _webhook_is_usable(endpoint.strip()):
        checks["webhook"] = "malformed"
        issues.append(
            _issue(
                "webhook-malformed",
                "The configured webhook is not a supported Discord webhook URL.",
                f"Replace {WEBHOOK_ENVIRONMENT} with an HTTPS Discord webhook.",
            )
        )
        usable_endpoint = None
    else:
        checks["webhook"] = "usable"
        usable_endpoint = endpoint.strip()

    destination_type = environment.get(
        DESTINATION_ENVIRONMENT,
        DEFAULT_DESTINATION_TYPE,
    ).strip()
    if destination_type not in DESTINATION_TYPES:
        checks["destination_type"] = "invalid"
        issues.append(
            _issue(
                "destination-type-invalid",
                "The Discord destination type is invalid.",
                (
                    f"Set {DESTINATION_ENVIRONMENT} to text-channel or "
                    "forum-channel."
                ),
            )
        )
    else:
        checks["destination_type"] = destination_type

    mention_user_id = environment.get(MENTION_ENVIRONMENT, "")
    if not mention_user_id.strip():
        checks["mention_user_id"] = "not-configured"
    elif DISCORD_USER_ID.fullmatch(mention_user_id.strip()) is None:
        checks["mention_user_id"] = "malformed"
        issues.append(
            _issue(
                "mention-user-id-malformed",
                "The attention target is not a numeric Discord user ID.",
                f"Replace {MENTION_ENVIRONMENT} with the 17–20 digit user ID.",
            )
        )
    else:
        checks["mention_user_id"] = "usable"

    state_path = _configured_state_file(environment)
    state_summary: MutableMapping[str, object] = {"path": str(state_path)}
    try:
        state_summary["exists"] = state_path.exists()
        summary = RoutingState(state_path).inspect()
        state_summary.update(summary)
        checks["state"] = "ready"
    except (OSError, TypeError, ValueError):
        checks["state"] = "invalid"
        issues.append(
            _issue(
                "state-invalid",
                "The routing state cannot be read or has an invalid format.",
                (
                    f"Disable hooks, then retain or remove {state_path}; "
                    "rerun the local check before enabling hooks."
                ),
            )
        )

    return checks, issues, state_summary, usable_endpoint, destination_type


def _delivery_diagnostic(outcome: Mapping[str, object]) -> Mapping[str, object]:
    if outcome.get("status") == "published":
        diagnostic: MutableMapping[str, object] = {
            "attempted": True,
            "status": "published",
            "attempts": outcome.get("attempts", 1),
            "message": "The opt-in test notification was delivered.",
        }
        if outcome.get("route_recovered") is True:
            diagnostic.update(
                {
                    "code": "route-recovered",
                    "action": (
                        "The stored thread route was stale and was replaced. "
                        "No action is required."
                    ),
                }
            )
        return diagnostic

    detail = outcome.get("diagnostic")
    safe_detail = detail if isinstance(detail, str) else "Discord delivery failed."
    lowered = safe_detail.lower()
    if "http 400" in lowered:
        code = "forum-configuration"
        action = (
            "Verify that the webhook belongs to a forum channel and can create "
            "forum posts."
        )
    elif "http 401" in lowered:
        code = "authentication-failed"
        action = "Recreate the webhook and update the locally stored webhook value."
    elif "http 403" in lowered:
        code = "permission-denied"
        action = (
            "Verify the webhook's forum-channel permission and access to the "
            "configured server."
        )
    elif "http 404" in lowered:
        code = "webhook-not-found"
        action = "Verify or recreate the webhook; the configured webhook was not found."
    elif "http 429" in lowered:
        code = "rate-limited"
        action = "Wait for Discord's retry window, then retry the opt-in test."
    elif "route" in lowered or "thread" in lowered:
        code = "routing-failed"
        action = (
            "Inspect the routing-state location; remove only the affected state "
            "after disabling hooks if a fresh forum post is desired."
        )
    elif "timed out" in lowered:
        code = "timeout"
        action = (
            "Check local network and Discord availability, then retry with the "
            "same bounded timeout."
        )
    elif "connection failed" in lowered:
        code = "network-unavailable"
        action = "Check local network and Discord availability before retrying."
    else:
        code = "delivery-failed"
        action = "Review local configuration and retry the explicit delivery test."
    return {
        "attempted": True,
        "status": "delivery-failed",
        "code": code,
        "attempts": outcome.get("attempts", 0),
        "retryable": outcome.get("retryable", False),
        "message": safe_detail,
        "action": action,
    }


def run_doctor(
    *,
    environment: Optional[Mapping[str, str]] = None,
    send_test: bool = False,
    delivery_policy: Optional[DeliveryPolicy] = None,
) -> Tuple[Mapping[str, object], int]:
    """Return a credential-free health result and its documented exit code."""

    configured_environment = environment if environment is not None else os.environ
    checks, issues, state_summary, endpoint, destination_type = _inspect_configuration(
        configured_environment
    )
    if issues:
        return (
            {
                "status": "configuration-error",
                "checks": dict(sorted(checks.items())),
                "state": state_summary,
                "delivery": {"attempted": False, "status": "not-run"},
                "issues": issues,
            },
            1,
        )

    if not send_test:
        return (
            {
                "status": "ready",
                "checks": dict(sorted(checks.items())),
                "state": state_summary,
                "delivery": {"attempted": False, "status": "not-run"},
                "next_action": (
                    "Run doctor with --send-test only when a Discord test message "
                    "is intended."
                ),
            },
            0,
        )

    assert endpoint is not None
    assert destination_type in DESTINATION_TYPES
    policy = delivery_policy or DeliveryPolicy()
    policy.validate()
    try:
        outcome = publish_notification(
            {
                "session_id": HEALTH_SESSION_ID,
                "status": "completed",
                "task_title": "Codex Discord health check",
                "project": "codex-discord",
                "result": "The explicit test delivery reached Discord.",
                "validation": "Local configuration checks passed.",
            },
            endpoint,
            state_summary["path"],
            destination_type=destination_type,
            delivery_policy=policy,
        )
        delivery = _delivery_diagnostic(outcome)
        if delivery["status"] == "published":
            state_path = Path(str(state_summary["path"]))
            state_summary = {
                "path": str(state_path),
                "exists": state_path.exists(),
                **RoutingState(state_path).inspect(),
            }
    except (OSError, TypeError, ValueError):
        delivery = {
            "attempted": True,
            "status": "delivery-failed",
            "code": "local-state-error",
            "attempts": 0,
            "retryable": False,
            "message": "The test could not use the local routing state.",
            "action": (
                "Check the routing-state path and permissions, then rerun the "
                "local-only health check."
            ),
        }
    if delivery["status"] == "published":
        return (
            {
                "status": "ready",
                "checks": dict(sorted(checks.items())),
                "state": state_summary,
                "delivery": delivery,
            },
            0,
        )
    return (
        {
            "status": "delivery-failed",
            "checks": dict(sorted(checks.items())),
            "state": state_summary,
            "delivery": delivery,
        },
        2,
    )
