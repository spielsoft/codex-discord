# Setup and operations

The integration is local and one-way. It sends explicit messages and,
optionally, selected Codex lifecycle events to Discord; it never reads Discord,
grants permissions, or controls Codex.

## Discord prerequisites

Create or select all of the following:

1. A private Discord server.
2. A **forum channel** in that server. A text channel is not interchangeable:
   the integration creates one forum post for each Codex session.
3. An incoming webhook created for that forum channel.
4. Optional: the numeric, 17–20 digit Discord user ID that should be mentioned
   for automatic attention events. Enable Discord Developer Mode and use
   **Copy User ID**; a display name or username is not a user ID.

The webhook URL is a credential. Keep it outside the repository, hook JSON,
shell scripts, screenshots, issue reports, and command output. Prefer a local
secret manager such as macOS Keychain and expose the value only to the process
that launches Codex. If a webhook URL is ever shared, delete and recreate the
webhook in Discord.

## Local configuration

The hooks and `doctor` command read:

| Environment variable | Purpose | Required |
| --- | --- | --- |
| `CODEX_DISCORD_WEBHOOK_URL` | HTTPS incoming webhook for the forum channel | Yes |
| `CODEX_DISCORD_MENTION_USER_ID` | Numeric user ID allowed for attention mentions | No |
| `CODEX_DISCORD_STATE_FILE` | Absolute routing-state path | No |

When `CODEX_DISCORD_STATE_FILE` is absent, the default is:

```text
~/.codex/codex-discord/routing.json
```

Environment variables must be present in the Codex desktop or CLI process,
not only in an unrelated terminal. Do not add the webhook to
`.codex/hooks.json`; the example hook definition intentionally contains no
credentials.

For an installed plugin, select **Connect Discord** or invoke `$discord`.
Codex opens a private localhost connection window. The window explains the
Discord prerequisites, accepts the webhook in a password-style field, accepts
an optional attention user ID, and sends one visible connection test.
Owner-only configuration is written only after Discord accepts the test.

The launcher and installed cache path remain implementation details. The
onboarding skill must never ask the user to run either from a terminal. A
send-only workflow is ready when the window reports that Discord is connected
and Codex reports the credential-free message and thread IDs.

## Local health check

Run this before enabling the hooks:

```sh
python3 -m codex_discord doctor
```

This default command sends nothing and does not contact Discord. It validates
the webhook shape, an attention user ID when configured, and local state
format, then prints credential-free JSON. It never prints the webhook, token,
mention user ID, session IDs, or Discord thread IDs.

Exit status is part of the public command contract:

- `0`: local configuration is ready;
- `1`: configuration or local state is missing, malformed, or unusable;
- `2`: an explicitly requested test delivery failed.

Only the following opt-in form sends a quiet completed notification:

```sh
python3 -m codex_discord doctor --send-test
```

The test uses the normal bounded publisher and a stable health-check route, so
later tests append to the same diagnostic forum post. It does not mention the
configured user. The command identifies authentication, permission,
forum-channel, missing-webhook, stale-routing, timeout, network, and rate-limit
outcomes with a safe action. Local loopback webhook-shaped URLs are accepted
for offline fake-service testing; non-loopback HTTP URLs and non-Discord
internet hosts are rejected.

Explicit messaging needs no lifecycle hooks. To add automatic lifecycle
notifications, copy `.codex/hooks.example.json` to the ignored
`.codex/hooks.json`, restart Codex with the applicable settings available,
inspect `/hooks`, and trust the two workspace hooks. See
[Stop hook](stop-hook.md) and [attention hook](attention-hook.md) for their
event contracts.

## Routing state

The state file contains the Codex-session-to-Discord-thread routes and at most
256 acknowledged lifecycle event digests. Routes have no automatic expiry in
this prototype. The health check reports only the state path and aggregate
counts.

- **Locate:** run `doctor` and read `state.path`.
- **Retain:** back up or leave the file in place to preserve same-task thread
  continuity.
- **Reset:** first disable the hooks, then remove the reported JSON file and
  its adjacent `.lock` file. A later notification creates empty state and a
  fresh forum post. Resetting state does not delete Discord posts.

Do not edit the JSON while hooks are active. Invalid state intentionally fails
the local health check instead of silently discarding routes.

## Disable versus uninstall

These are separate operations:

1. **Disable delivery:** remove the integration's `Stop` and
   `PermissionRequest` entries from the ignored `.codex/hooks.json`, then
   restart Codex. If the file was copied solely for this integration, it can
   instead be removed. Preserve any unrelated project hooks. Verify `/hooks`
   no longer lists these two commands.
2. **Remove configuration:** stop exporting the three environment variables
   from the Codex launch environment. This does not delete a credential from a
   secret manager.
3. **Retain or remove state:** keep the reported state and lock files for future
   thread continuity, or remove them after hooks are disabled.
4. **Revoke credentials:** delete the incoming webhook in Discord and remove
   its value from Keychain or the chosen secret manager. Removing code or an
   environment variable does not revoke the webhook.
5. **Uninstall workspace code:** only after disabling hooks, remove the
   integration package or workspace checkout. For an installed plugin, follow
   the package-specific trust, state-retention, and removal guidance in
   [`plugins/codex-discord/README.md`](../plugins/codex-discord/README.md).

The Discord forum posts remain in Discord until removed there.

## Diagnostic reference

| Code | Meaning | First action |
| --- | --- | --- |
| `authentication-failed` | Discord rejected the webhook credential | Recreate the webhook and update local secret storage |
| `permission-denied` | The webhook cannot access or create in the destination | Verify forum-channel access and webhook permissions |
| `forum-configuration` | Discord rejected the forum-post request | Confirm the webhook belongs to a forum channel |
| `webhook-not-found` | The configured webhook no longer exists | Verify or recreate the webhook |
| `route-recovered` | A stale stored thread was replaced successfully | No action is required |
| `routing-failed` | A thread route could not be used or replaced | Inspect state; reset only after disabling hooks |
| `timeout` / `network-unavailable` | Delivery could not finish within its bound | Check local network and Discord availability |
| `rate-limited` | Discord asked the publisher to wait | Retry after Discord's retry window |

Diagnostics are best effort. They deliberately do not echo Discord response
bodies because those can contain credential or user-controlled text.
