#!/usr/bin/env python3
"""Capture a narrow, sanitized Codex lifecycle payload for Slice 6.

The hook mode deliberately writes no stdout because hook output can affect
Codex behavior. PermissionRequest values are reduced to their JSON shape, and
session/turn identifiers are replaced with deterministic pseudonyms.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_EVENTS = {"Stop", "PermissionRequest"}
SUPPORTED_SURFACES = {"cli", "desktop"}
MAX_MESSAGE_LENGTH = 500
DISCORD_WEBHOOK_PATTERN = re.compile(
    r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\S+",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"(?i)\b(?:token|secret|password)=\S+")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--arm", choices=sorted(SUPPORTED_SURFACES))
    return parser.parse_args()


def write_private_json(path: Path, value: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def arm_capture(path: Path, surface: str) -> None:
    write_private_json(path, {"surface": surface})


def read_surface(path: Path) -> str:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "unknown"
    surface = value.get("surface")
    return surface if surface in SUPPORTED_SURFACES else "unknown"


def pseudonym(prefix: str, value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def sanitize_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return "<non-string>"
    sanitized = DISCORD_WEBHOOK_PATTERN.sub("<redacted-webhook>", value)
    sanitized = TOKEN_PATTERN.sub("<redacted-credential>", sanitized)
    user_home = str(Path.home())
    if user_home and user_home != "/":
        sanitized = sanitized.replace(user_home, "<home>")
    sanitized = " ".join(sanitized.split())
    if len(sanitized) > MAX_MESSAGE_LENGTH:
        sanitized = sanitized[: MAX_MESSAGE_LENGTH - 1] + "…"
    return sanitized


def value_shape(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        return "<max-depth>"
    if isinstance(value, dict):
        return {
            str(key)[:80]: value_shape(item, depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))[:50]
        }
    if isinstance(value, list):
        item_shapes = []
        for item in value[:10]:
            shape = value_shape(item, depth + 1)
            if shape not in item_shapes:
                item_shapes.append(shape)
        return item_shapes
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def sanitize_payload(payload: dict[str, Any], surface: str) -> dict[str, Any]:
    event_name = payload.get("hook_event_name")
    if event_name not in SUPPORTED_EVENTS:
        raise ValueError("unsupported hook event")

    cwd = payload.get("cwd")
    record: dict[str, Any] = {
        "capture_schema": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "surface": surface,
        "hook_event_name": event_name,
        "available_fields": sorted(str(key) for key in payload),
        "session_id": pseudonym("session", payload.get("session_id")),
        "turn_id": pseudonym("turn", payload.get("turn_id")),
        "cwd_name": Path(cwd).name if isinstance(cwd, str) else None,
        "model": sanitize_text(payload.get("model")),
        "permission_mode": sanitize_text(payload.get("permission_mode")),
        "transcript_path_present": bool(payload.get("transcript_path")),
    }
    if event_name == "Stop":
        record.update(
            {
                "last_assistant_message": sanitize_text(
                    payload.get("last_assistant_message")
                ),
                "stop_hook_active": payload.get("stop_hook_active"),
            }
        )
    else:
        record.update(
            {
                "tool_name": sanitize_text(payload.get("tool_name")),
                "tool_input_shape": value_shape(payload.get("tool_input")),
            }
        )
    return record


def append_private_json_line(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        json.dump(record, stream, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def main() -> int:
    arguments = parse_arguments()
    if arguments.arm:
        arm_capture(arguments.context, arguments.arm)
        print(f"armed sanitized {arguments.arm} capture")
        return 0
    if arguments.output is None:
        print("capture failed: --output is required", file=sys.stderr)
        return 2

    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        record = sanitize_payload(payload, read_surface(arguments.context))
        append_private_json_line(arguments.output, record)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        print("capture failed: invalid or unwritable hook input", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
