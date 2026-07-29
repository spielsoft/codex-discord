# Discord outgoing-message MVP

## Decision

The existing webhook publisher was sufficient to send a PersonalAssistant
daily brief. The usability problem was the agent interface and the
forum-only destination assumption:

- agents had to discover a skill that piped JSON into an installed command;
- onboarding selected only a forum webhook;
- forum webhooks create forum posts, which are a poor fit for routine alerts;
- a successful send was not exposed as a native callable tool like Slack's
  send-message operation.

Version 0.4 makes a regular Discord text channel the recommended onboarding
choice and adds one native `discord_send_message` MCP tool. Forum delivery
remains a separate selectable destination because it provides useful routed
post behavior. The former installed `send` command is removed instead of
retaining two agent-facing write interfaces.

## Slack analogy

The OpenAI Slack plugin supplies the interaction pattern, not the Discord
feature list:

| Slack pattern | Discord MVP |
| --- | --- |
| A direct callable send-message tool | `discord_send_message` |
| Message composition is separate from connection | Connection stores one private webhook destination |
| Destination details are not pasted into each prompt | The tool accepts no webhook or credential |
| Optional transport context stays optional | `route_key`, `idempotency_key`, and forum-only `thread_name` |
| Writes return a structured result | `sent`, `duplicate`, `delivery-failed`, or `configuration-error` |

Discord differs from Slack in destination selection. This MVP connects one
destination during guided setup rather than accepting a channel identifier on
each tool call. That is deliberate: an incoming Discord webhook is already
bound to a channel, and the plugin does not yet discover or enumerate channels.

Onboarding follows the same user-facing principle. Codex opens a focused
private connection window, the user chooses text or forum delivery and
verifies it there, and Codex reports the credential-free result. Terminal
commands and installed cache paths are not part of the user-facing flow.

## Agent tool contract

`discord_send_message` accepts:

- `message` (required): one Discord-ready body, at most 2,000 UTF-16 code
  units;
- `route_key` (optional): a stable logical route, and the forum-post routing
  key when forum delivery is configured;
- `idempotency_key` (optional): a deterministic event identity for local
  duplicate suppression;
- `thread_name` (optional): a forum-post title, ignored for text-channel
  delivery.

The tool never accepts or returns the configured webhook.

For a configured text channel, the transport sends a normal webhook request
with neither `thread_name` in the body nor `thread_id` in the query. Discord
therefore creates one ordinary message in that channel and no forum post or
thread.

For a configured forum channel, the first message for a route includes
`thread_name`; later messages include the stored `thread_id` and append to the
same forum post. This matches Discord's
[Execute Webhook contract](https://docs.discord.com/developers/resources/webhook),
which requires a forum webhook call to provide either `thread_name` or
`thread_id`; a normal text-channel webhook requires neither.

## Structured outcomes

A text-channel success:

```json
{
  "route_key": "personal-assistant:daily-brief",
  "status": "sent",
  "destination_type": "text-channel",
  "channel_id": "456",
  "message_id": "123"
}
```

A forum-channel success substitutes `thread_id` for `channel_id`. A duplicate
returns `status: duplicate` and makes no Discord request. A bounded transport
failure returns `status: delivery-failed`, `retryable`, `attempts`, and a
credential-free diagnostic. Missing or invalid connection data returns
`status: configuration-error` with `retryable: false`.

## Automation guidance

A recurring workflow should:

1. Build the complete message before calling Discord.
2. Call `discord_send_message` exactly once.
3. Derive `idempotency_key` from the workflow and durable event identity, such
   as `personal-assistant:daily-brief:2026-07-29`.
4. Treat `sent` and `duplicate` as success.
5. Retry `delivery-failed` only when `retryable` is true.
6. Treat `configuration-error` as a reason to reconnect, not to retry
   unchanged.

Replay suppression is local and bounded, not distributed exactly-once
delivery. A process crash after Discord accepts the request but before state is
persisted can still produce a duplicate on retry.

## Reused implementation

Text messages, forum messages, and automatic lifecycle notifications share:

- private webhook configuration;
- bounded retries, rate-limit handling, and a delivery deadline;
- restrictive `allowed_mentions`;
- process-safe atomic state;
- the 256-entry delivered-event ledger;
- credential-free failure diagnostics.

Forum delivery additionally uses persistent route-to-thread mapping and stale
route recovery. Text delivery does not create or retain thread routes.

## MVP exclusions

This release does not add Discord reads, DMs, destination discovery, arbitrary
per-call channel selection, multiple configured webhooks, drafts, scheduling,
editing, deletion, a hosted service, a bot/OAuth flow, or two-way Discord
control of Codex.
