# Discord outgoing-message MVP

## Decision

The existing plugin transport is sufficient for workflows such as a daily
PersonalAssistant calendar brief. The earlier concern was an interface
mismatch, not a delivery limitation: the only explicit write surface was named
and shaped as a Codex milestone even though the webhook publisher could already
send the underlying Discord message.

Version 0.3 adds a thin generic outgoing-message facade. It does not replace
the lifecycle hooks or attempt Slack feature parity. Because the repository
has no compatibility obligation, it removes the narrower `discord-milestone`
skill and `milestone` command instead of retaining two explicit-send surfaces.

## Slack analogy

The OpenAI Slack plugin provides the interaction pattern, not the feature list:

| Slack interaction pattern | Discord MVP |
| --- | --- |
| Explicit send intent performs a direct write | Explicit Discord send intent invokes `discord-outgoing-message` |
| Message content is free-form | `message` accepts one Discord-ready body |
| Destination resolution is separate from composition | Connection selects one forum webhook destination |
| Optional transport parameters stay absent by default | Routing and idempotency fields are optional |
| The caller receives a concrete write result | `sent`, `duplicate`, or `delivery-failed` |

Discord-specific routing remains visible only where it is useful. A
`route_key` identifies the forum post that receives related messages, and a
`thread_name` names that post when first created.

The onboarding analogy is likewise experiential rather than architectural.
Slack uses a registered connector and native authentication. This MVP keeps
its local webhook transport, but Codex opens a focused private connection
window, the user completes and verifies the connection there, and Codex
returns the result. Terminal commands and installed cache paths are explicitly
excluded from the user-facing onboarding flow.

## Public contract

The installed command reads one JSON object from standard input:

```sh
/usr/bin/python3 scripts/codex-discord send
```

Example:

```json
{
  "message": "# Daily calendar brief\n\nYour first event is at 9:00 AM.",
  "thread_name": "Daily Brief",
  "route_key": "personal-assistant:daily-brief",
  "idempotency_key": "personal-assistant:daily-brief:2026-07-29"
}
```

`message` is required. The other fields are optional:

- `thread_name` defaults to `Codex messages`.
- `route_key` defaults to `discord-outgoing-message`. Reusing a route key
  appends to the same forum post.
- `idempotency_key` maps to the existing delivered-event ledger. Repeating a
  recorded key is a successful no-op.

The connection-selected forum webhook remains the only MVP destination. The command
does not accept a webhook, credential, Discord DM, channel ID, or guild ID.

## Outcomes and exit codes

A successful write exits 0:

```json
{
  "route_key": "personal-assistant:daily-brief",
  "status": "sent",
  "thread_id": "456",
  "message_id": "123"
}
```

A suppressed duplicate also exits 0 and makes no Discord request:

```json
{
  "route_key": "personal-assistant:daily-brief",
  "status": "duplicate",
  "thread_id": "456"
}
```

A bounded transport failure exits 2:

```json
{
  "route_key": "personal-assistant:daily-brief",
  "status": "delivery-failed",
  "attempts": 3,
  "retryable": true,
  "diagnostic": "Discord connection failed after 3 attempts."
}
```

Invalid input or missing local configuration exits 1 and does not make a
Discord request. Lifecycle hooks retain their best-effort behavior so a
Discord outage cannot change the originating Codex task result.

## Reused implementation

Generic messages and automatic lifecycle notifications share:

- private webhook configuration;
- forum-post creation, persistent routing, and stale-route recovery;
- bounded retries, rate-limit handling, and delivery deadline;
- restrictive `allowed_mentions`;
- process-safe atomic state;
- the 256-entry delivered-event ledger;
- credential-free failure diagnostics.

The generic surface preserves message newlines and Markdown while neutralizing
mention-shaped content. It rejects content over Discord's 2,000 UTF-16 code
unit limit rather than splitting one requested message into several posts.

## Automation guidance

A recurring workflow should:

1. Produce the complete brief before invoking Discord.
2. Invoke the outgoing-message skill exactly once.
3. Use a stable route key for the intended forum post.
4. Derive the idempotency key from the workflow and the brief's local date or
   another durable source event identity.
5. Treat `sent` and `duplicate` as success.
6. Retry exit code 2 only when `retryable` is true.
7. Treat exit code 1 as a configuration or payload problem requiring a change.

Replay suppression is local and bounded, not distributed exactly-once
delivery. A process crash after Discord accepts the request but before state is
persisted can still produce a duplicate on retry.

## MVP exclusions

This release does not add:

- Discord reads;
- DMs or arbitrary channel selection;
- destination discovery or multiple configured webhooks;
- drafts, scheduling, editing, or deletion;
- a hosted MCP service;
- a bot or OAuth flow;
- two-way Discord control of Codex.

Those capabilities should be evaluated from concrete Discord workflows rather
than copied wholesale from Slack.
