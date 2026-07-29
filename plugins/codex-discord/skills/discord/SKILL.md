---
name: discord
description: Connect the Codex Discord plugin, check its configured Discord forum destination, and route supported Discord requests to the correct workflow. Use when the user asks to connect or configure Discord, verify readiness, troubleshoot the connection, understand supported Discord actions, or generally work with Discord without naming a more specific skill.
---

# Discord

Use this skill as the router for Discord work.

## Intent routing

- For an explicit send, post, share, progress update, or automation delivery,
  switch to `../discord-outgoing-message/SKILL.md`.
- For a draft or review request, return the Discord-ready text in chat without
  sending it.
- For connection, reconfiguration, or readiness checks, use the workflows
  below.
- For unsupported reads, DMs, arbitrary channel selection, scheduling, edits,
  or deletion, state the limitation before collecting details.

## Connect

The MVP connects one Discord **forum channel** as its default destination.

1. Resolve this `SKILL.md` path and treat its great-grandparent directory as
   the plugin root.
2. Run the plugin root's `scripts/codex-discord` launcher with the `onboard`
   operation yourself. Yield while it remains active.
3. The launcher announces a private localhost URL and normally opens it in the
   user's browser. If it does not open automatically, open that URL with an
   available browser tool or give the user the clickable localhost link.
4. Tell the user only that the Discord connection window is ready. The window
   itself guides them through selecting a private forum channel, creating its
   webhook, optionally supplying an attention user ID, and testing the
   connection.
5. Wait for the launcher to finish. Treat `status: connected` with
   `verification.status: sent` as ready, then report the credential-free
   `message_id` and `thread_id`.

Never ask the user to paste the webhook into chat, a Codex prompt, a command
argument, or a repository file. Never read, repeat, log, or transmit the stored
webhook outside the configured Discord request.

Never ask the user to run a terminal command, reveal the plugin cache path, or
describe the internal launcher as onboarding. The launcher is implementation
detail; the browser window is the user-facing connection surface.

If the user cancels or the window times out, report that no configuration was
changed and offer to open Connect Discord again. A failed connection test stays
in the window, does not save the webhook, and allows the user to correct or
retry it without exposing the credential.

After a successful connection, the next useful action is an explicit message
through `$discord-outgoing-message`. PersonalAssistant and other send-only
workflows do not need to enable or trust lifecycle hooks.

## Check

Resolve the same internal launcher and run its `doctor` operation yourself.

It must not contact Discord. Add `--send-test` only when the user explicitly
asks to create another Discord test message.

## Optional lifecycle notifications

The installed plugin also contains automatic `Stop` and `PermissionRequest`
hooks. Treat these as an optional feature after messaging is connected. A user
who wants them should inspect and trust both hooks in a new Codex task. An
attention user ID is required only for permission, blocked, or failed messages
that deliberately mention the user.

## Managed deployment

Administrators may supply `CODEX_DISCORD_WEBHOOK_URL` to the Codex process.
`CODEX_DISCORD_MENTION_USER_ID` is optional and enables deliberate attention
mentions. `CODEX_DISCORD_STATE_FILE` optionally overrides routing-state
storage. Environment values override private local configuration.
