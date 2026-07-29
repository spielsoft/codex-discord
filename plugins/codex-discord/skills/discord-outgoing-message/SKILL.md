---
name: discord-outgoing-message
description: Send one immediate, free-form message through the Codex Discord tool to the text or forum channel selected during connection. Use when the user explicitly asks to send, post, or share text to Discord, including progress updates, alerts, daily briefs, and recurring automation output. Do not use for drafts, automatic lifecycle delivery, connection management, Discord reads, DMs, or arbitrary channel selection.
---

# Discord outgoing message

Follow explicit write intent directly. If the user asks for a draft, review, or
later/manual send, return text in chat without invoking the send tool.

The MVP has one configured destination selected during `$discord` connection:
either a regular text channel or a forum channel. It does not discover
channels, select DMs, read Discord, or accept a webhook in the prompt.

Before delivery:

1. Compose one Discord-ready message no longer than 2,000 characters. Preserve
   useful Markdown and links. Do not add broad mentions.
2. Add a stable `route_key` when the calling workflow has a logical route.
   Forum delivery uses it to append later messages to the same post; text
   delivery returns it for correlation without creating a thread.
3. Add an `idempotency_key` only when the workflow has a deterministic event
   identity. For a daily automation, include the workflow name and local date.
   Never use a random value to claim duplicate protection.
4. Add a short `thread_name` only when the configured destination is a forum
   channel and the caller has a useful forum-post title. Text-channel delivery
   ignores it.
5. Call `discord_send_message` exactly once with `message` and any applicable
   optional fields. This is the agent-facing write surface, analogous to
   Slack's direct send-message tool. Do not invoke or expose an internal CLI,
   request the webhook, or ask the user to run a command.

Report the tool's credential-free structured outcome:

- `sent`: delivery succeeded and includes `message_id`, `route_key`, and
  `destination_type`; text delivery also includes `channel_id`, while forum
  delivery includes `thread_id`.
- `duplicate`: the idempotency key was already recorded; no second Discord
  request was made.
- `delivery-failed`: bounded delivery failed. A recurring automation may retry
  only when `retryable` is true.
- `configuration-error`: Discord is not connected or its destination setting
  is invalid. Do not retry unchanged; run `$discord` connection instead.

If `discord_send_message` is unavailable, explain that the plugin must be
reinstalled or Codex restarted and the send retried in a new task. Do not fall
back to the former terminal-pipe interface.
