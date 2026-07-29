# Codex attention notifications

Slice 8 adds one notification-only lifecycle hook and an explicit milestone
operation. Neither interface can approve, deny, steer, or otherwise control a
Codex task.

## PermissionRequest hook

`python3 -m codex_discord.attention_hook` reads one JSON object from standard
input. The active Codex hook contract accepts the observed structured
`PermissionRequest` fields:

- `session_id` selects the same Discord forum post used by `Stop`.
- `turn_id`, the event name, `tool_name`, and a one-way digest of the canonical
  `tool_input` establish stable event identity.
- `cwd` supplies only its basename as the project name.
- `tool_name` identifies the kind of request. `tool_input` values are never
  included in the notification.

The message has `needs-input` status, deliberately mentions only the numeric
Discord user ID from `CODEX_DISCORD_MENTION_USER_ID`, and directs the user back
to Codex. The hook emits no decision payload and always exits zero. Missing or
invalid configuration, malformed input, and delivery failure therefore leave
the permission request unchanged.

The same entry point accepts adapter-owned `CodexDiscordAttention` objects for
normalized `blocked` and `failed` outcomes. These objects require
`session_id`, `turn_id`, `cwd`, `status`, `summary`, and `validation`; an
optional `next_action` is supported. This is an explicit local adapter
contract, not a claim that Codex currently exposes blocked or failed lifecycle
events. Only `PermissionRequest` is registered in the example hook file.
`PreToolUse`, `PostToolUse`, and other routine activity are neither registered
nor supported.

## Durable duplicate rule

Lifecycle identity is a SHA-256 digest of stable structured fields:

- permission request: session, turn, `PermissionRequest`, tool name, and a
  SHA-256 digest of canonical tool input;
- normalized outcome: session, turn, `CodexDiscordAttention`, and status.

After Discord acknowledges a delivery, the identity is atomically stored with
the session route. A repeated successful identity returns `duplicate` and
performs no HTTP request, including in a later process. Failed deliveries are
not recorded and may be retried. The store retains the 256 most recently
acknowledged identities, bounding local state.

Tool-input values are never retained in routing state or sent to Discord. The
digest prevents two different requests for the same tool in one turn from
being mistaken for duplicates.

This is an at-least-once transport with durable replay suppression, not a
distributed exactly-once protocol. A process crash after Discord accepts a
request but before local state is replaced can still duplicate that message.

## Explicit messages

Explicit progress updates and other user-authored Discord content use the
single generic outgoing-message surface described in
[Discord outgoing-message MVP](outgoing-message-mvp.md). They are not modeled
as lifecycle events and never mention a user automatically.

## Configuration

The attention hook reads:

- `CODEX_DISCORD_WEBHOOK_URL` for the forum webhook;
- `CODEX_DISCORD_MENTION_USER_ID` for the required 17–20 digit Discord user ID;
- optional `CODEX_DISCORD_STATE_FILE`, defaulting to
  `~/.codex/codex-discord/routing.json`.

Do not put webhook credentials or personal user IDs in tracked hook
definitions. `.codex/hooks.example.json` contains commands only and remains
opt-in.
