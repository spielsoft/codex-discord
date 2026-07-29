---
name: discord-outgoing-message
description: Send one immediate, free-form message to the Discord forum destination configured for Codex Discord. Use when the user explicitly asks to send, post, or share text to Discord, including progress updates, milestones, and recurring automation output. Do not use for drafts, automatic lifecycle delivery, connection management, Discord reads, DMs, or arbitrary channel selection.
---

# Discord outgoing message

Follow explicit write intent directly. If the user asks for a draft, review, or
later/manual send, return text in chat without invoking this skill's command.

The MVP has one destination: the Discord forum webhook selected during
the `$discord` connection workflow. It does not discover channels, select DMs, read Discord, or
accept a webhook in the prompt.

Before delivery:

1. Compose one Discord-ready message no longer than 2,000 characters. Preserve
   useful Markdown and links. Do not add broad mentions.
2. Use a short `thread_name` when the message should create a new forum post.
   If omitted, the plugin uses `Codex messages`.
3. Use a stable `route_key` when later messages should append to the same forum
   post. If omitted, the plugin uses its shared outgoing-message route.
4. Add an `idempotency_key` only when the workflow has a deterministic event
   identity. For a daily automation, include the workflow name and local date.
   Never use a random value to claim duplicate protection.
5. Resolve this `SKILL.md` path and treat its great-grandparent directory as
   the plugin root (`SKILL.md` → `discord-outgoing-message` → `skills` →
   plugin root).
6. Pipe exactly one JSON object to:

   ```sh
   /usr/bin/python3 "<plugin-root>/scripts/codex-discord" send
   ```

The object requires `message`. `thread_name`, `route_key`, and
`idempotency_key` are optional. Do not request or expose the webhook; the
command reads the private configured destination.

Invoke the command once per requested message. Report its credential-free JSON
outcome:

- `sent`: delivery succeeded and includes Discord `message_id` and `thread_id`.
- `duplicate`: the idempotency key was already recorded; no second Discord
  request was made.
- `delivery-failed`: delivery exhausted its bounded policy. Exit code 2 means
  an automation may retry according to `retryable`; exit code 1 means invalid
  input or configuration and should not be retried unchanged.
