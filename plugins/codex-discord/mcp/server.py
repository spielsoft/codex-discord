#!/usr/bin/env python3
"""Local MCP surface for sending to the configured Discord destination."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Mapping, MutableMapping, Optional


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "runtime"))

from codex_discord.publisher import (  # noqa: E402
    DEFAULT_DESTINATION_TYPE,
    DESTINATION_TYPES,
    publish_message,
)


SERVER_NAME = "Codex Discord"
SERVER_VERSION = "0.4.0"
TOOL_NAME = "discord_send_message"
WEBHOOK_ENVIRONMENT = "CODEX_DISCORD_WEBHOOK_URL"
DESTINATION_ENVIRONMENT = "CODEX_DISCORD_DESTINATION_TYPE"
STATE_ENVIRONMENT = "CODEX_DISCORD_STATE_FILE"
CONFIG_FILENAME = "config.json"
JSON_RPC_METHOD_NOT_FOUND = -32601
JSON_RPC_INVALID_PARAMS = -32602


def _plugin_data() -> Path:
    configured = os.environ.get("PLUGIN_DATA", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codex" / "codex-discord"


def _stored_configuration() -> Mapping[str, str]:
    try:
        value = json.loads((_plugin_data() / CONFIG_FILENAME).read_text())
    except (OSError, TypeError, ValueError):
        return {}
    if not isinstance(value, Mapping):
        return {}
    return {
        name: configured.strip()
        for name, configured in value.items()
        if name in (WEBHOOK_ENVIRONMENT, DESTINATION_ENVIRONMENT)
        and isinstance(configured, str)
        and configured.strip()
    }


def _configuration_value(name: str, stored: Mapping[str, str]) -> str:
    return os.environ.get(name, "").strip() or stored.get(name, "")


def _state_file() -> Path:
    configured = os.environ.get(STATE_ENVIRONMENT, "").strip()
    return (
        Path(configured).expanduser()
        if configured
        else _plugin_data() / "routing.json"
    )


def _send(message: Mapping[str, object]) -> None:
    json.dump(message, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _result(
    request_id: object,
    text: str,
    structured: Mapping[str, object],
    *,
    is_error: bool = False,
) -> None:
    result: MutableMapping[str, object] = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
    }
    if is_error:
        result["isError"] = True
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: object, code: int, message: str) -> None:
    _send(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    )


def _optional_string(
    arguments: Mapping[str, object],
    name: str,
) -> Optional[str]:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string when provided.")
    return value


def _tool_definition() -> Mapping[str, object]:
    return {
        "name": TOOL_NAME,
        "title": "Send Discord Message",
        "description": (
            "Send one message to the Discord destination selected during "
            "Codex Discord connection. A configured text channel receives an "
            "ordinary message; a configured forum channel receives the "
            "plugin's forum-post behavior. Returns credential-free delivery "
            "status and Discord message identity."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": (
                        "Complete Discord-ready message, up to 2,000 characters."
                    ),
                },
                "route_key": {
                    "type": "string",
                    "description": (
                        "Stable logical route. Used for forum-post reuse and "
                        "returned for both destination types."
                    ),
                },
                "idempotency_key": {
                    "type": "string",
                    "description": (
                        "Stable event identity used to suppress a repeated "
                        "send to the configured destination."
                    ),
                },
                "thread_name": {
                    "type": "string",
                    "description": (
                        "Forum post name. Relevant only when the configured "
                        "destination is a forum channel."
                    ),
                },
            },
            "required": ["message"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    }


def _call_tool(request_id: object, params: object) -> None:
    if not isinstance(params, Mapping) or params.get("name") != TOOL_NAME:
        unknown = params.get("name", "") if isinstance(params, Mapping) else ""
        _error(
            request_id,
            JSON_RPC_INVALID_PARAMS,
            f"Unknown tool: {unknown}",
        )
        return
    arguments = params.get("arguments", {})
    if not isinstance(arguments, Mapping):
        raise ValueError("arguments must be an object.")

    message = arguments.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string.")
    unexpected = set(arguments) - {
        "message",
        "route_key",
        "idempotency_key",
        "thread_name",
    }
    if unexpected:
        raise ValueError(
            f"Unsupported argument: {sorted(unexpected)[0]}."
        )

    payload: MutableMapping[str, object] = {"message": message}
    for name in ("route_key", "idempotency_key", "thread_name"):
        value = _optional_string(arguments, name)
        if value is not None:
            payload[name] = value

    stored = _stored_configuration()
    endpoint = _configuration_value(WEBHOOK_ENVIRONMENT, stored)
    destination_type = (
        _configuration_value(DESTINATION_ENVIRONMENT, stored)
        or DEFAULT_DESTINATION_TYPE
    )
    if not endpoint:
        _result(
            request_id,
            "Discord is not connected. Open Connect Discord, then retry.",
            {
                "status": "configuration-error",
                "retryable": False,
                "diagnostic": "Discord is not connected.",
            },
            is_error=True,
        )
        return
    if destination_type not in DESTINATION_TYPES:
        _result(
            request_id,
            "The configured Discord destination type is invalid. Reconnect Discord.",
            {
                "status": "configuration-error",
                "retryable": False,
                "diagnostic": "Discord destination type is invalid.",
            },
            is_error=True,
        )
        return

    outcome = publish_message(
        payload,
        endpoint,
        _state_file(),
        destination_type=destination_type,
    )
    status = outcome.get("status")
    if status == "sent":
        identity = outcome.get("message_id", "unknown")
        _result(
            request_id,
            f"Sent Discord message {identity}.",
            outcome,
        )
        return
    if status == "duplicate":
        _result(
            request_id,
            "Skipped a duplicate Discord message; no new request was made.",
            outcome,
        )
        return
    diagnostic = outcome.get("diagnostic")
    safe_diagnostic = (
        diagnostic
        if isinstance(diagnostic, str) and diagnostic
        else "Discord delivery failed."
    )
    _result(
        request_id,
        safe_diagnostic,
        outcome,
        is_error=True,
    )


def _handle(message: Mapping[str, object]) -> None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params")
    if method == "initialize":
        protocol_version = (
            params.get("protocolVersion", "2025-11-25")
            if isinstance(params, Mapping)
            else "2025-11-25"
        )
        _send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                    "instructions": (
                        "Use discord_send_message for explicit Discord writes. "
                        "The tool uses the destination selected in Connect Discord."
                    ),
                },
            }
        )
        return
    if method == "ping":
        _send({"jsonrpc": "2.0", "id": request_id, "result": {}})
        return
    if method == "tools/list":
        _send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": [_tool_definition()]},
            }
        )
        return
    if method == "tools/call":
        try:
            _call_tool(request_id, params)
        except (OSError, TypeError, ValueError) as error:
            _error(
                request_id,
                JSON_RPC_INVALID_PARAMS,
                str(error),
            )
        return
    if request_id is not None:
        _error(
            request_id,
            JSON_RPC_METHOD_NOT_FOUND,
            f"Method not found: {method}",
        )


def main() -> None:
    for raw_line in sys.stdin:
        if not raw_line.strip():
            continue
        try:
            message = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, Mapping):
            _handle(message)


if __name__ == "__main__":
    main()
