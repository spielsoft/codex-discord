# Codex Discord plugin

This reusable, one-way Codex plugin sends selected lifecycle events to a
Discord forum webhook. It never reads Discord, approves requests, or controls
Codex.

## Package contents

- `hooks/hooks.json`: notification-only `Stop` and `PermissionRequest` hooks,
  discovered by Codex at the plugin default path.
- `runtime/codex_discord/`: independent Python standard-library runtime.
- `scripts/codex-discord`: setup, doctor, milestone, hook, and removal-guidance
  command boundary.
- `skills/discord-setup/`: guided first-run connection and verification.
- `skills/discord-milestone/`: focused workflow for user-requested milestones.

The manifest intentionally omits a `hooks` field. Codex discovers
`hooks/hooks.json` by convention. Hook commands resolve installed code through
`PLUGIN_ROOT` and default writable routing state to
`PLUGIN_DATA/routing.json`. Guided setup stores per-user configuration in
`PLUGIN_DATA/config.json`; no credential or user-specific configuration is
shipped in the package.

## What each user configures

The plugin needs:

- one incoming webhook created for the destination Discord **forum channel**;
- one numeric Discord user ID for deliberate attention mentions.

It does not need the name or ID of a pre-existing forum post. On the first
event for a Codex session, the webhook creates `Codex task — <project>`.
The plugin stores Discord's returned thread ID and appends later events from
that Codex session to the same post.

## Supported surfaces and runtime

Compatibility evidence from July 27, 2026 covers
`codex-cli 0.146.0-alpha.3.1` on macOS and its paired Codex desktop build:

- `Stop` was observed in CLI and desktop with a usable
  `last_assistant_message`.
- `PermissionRequest` was observed in CLI. Desktop attention delivery retains
  the explicit milestone/notification fallback because a desktop permission
  event was not observed.
- Plugin hooks require review and trust on both surfaces.

The bundled runtime requires macOS or another POSIX environment with
`fcntl`, Python 3.9 or newer at `/usr/bin/python3`, outbound HTTPS access, and
Codex plugin support. Windows is not supported by this package version.
Lifecycle schemas can change in later Codex versions, so rerun the offline
contract and an opt-in smoke when upgrading Codex.

## Install and trust

The plugin package contains no user-global configuration. Its repository
provides the standard repo marketplace at
`.agents/plugins/marketplace.json`, pointing to `plugins/codex-discord`.

From a local clone:

```sh
codex plugin marketplace add /absolute/path/to/repository
codex plugin add codex-discord@codex-discord
```

From GitHub, replace `owner/repository` with the repository shorthand:

```sh
codex plugin marketplace add owner/repository
codex plugin add codex-discord@codex-discord
```

These commands mutate the user's Codex plugin configuration and are therefore
explicit opt-in steps. Start a new Codex task after installation, run `/hooks`,
inspect the plugin source, and trust exactly the two packaged hooks. Changed
hook definitions require review again.

The installed `codex-cli 0.146.0-alpha.3.1` exposes no `--config-dir` or
`--config-file` option on `plugin`, `plugin marketplace add`, or `plugin add`.
Codex's documented configuration base is the process-wide `CODEX_HOME`;
repository checks intentionally do not repoint `CODEX_HOME` or `HOME`.
Package tests instead perform a clean copy into a temporary install root and
exercise the same manifest, hooks, commands, and bundled runtime without
invoking the user-config-mutating plugin CLI. A real marketplace add/install
remains the explicit opt-in procedure above.

## First-run setup

After installation, select the starter prompt **Set up Codex Discord
notifications**, or invoke `$discord-setup`. The guided workflow explains how
to create the forum webhook and copy a numeric Discord user ID.

Run the setup command from a local terminal so the webhook never enters a chat
or Codex transcript:

```sh
/usr/bin/python3 scripts/codex-discord setup
```

Webhook input is hidden. The command validates both values locally and writes
`PLUGIN_DATA/config.json` with owner-only permissions. Then verify the local
configuration and deliberately send one test:

```sh
/usr/bin/python3 scripts/codex-discord doctor
/usr/bin/python3 scripts/codex-discord doctor --send-test
```

The first command is local-only. The second creates a diagnostic forum post.
Start a new Codex task, inspect and trust the two packaged hooks, and complete
one turn to verify automatic delivery.

Each user has independent `PLUGIN_DATA`. A workspace can direct everyone to
one forum webhook while giving each person their own numeric mention ID.

## Managed configuration

Administrators can provide environment variables instead of interactive setup.
Environment values override the per-user private configuration:

| Variable | Purpose | Required |
| --- | --- | --- |
| `CODEX_DISCORD_WEBHOOK_URL` | Incoming webhook for a Discord forum channel | yes |
| `CODEX_DISCORD_MENTION_USER_ID` | Numeric 17–20 digit attention target | yes |
| `CODEX_DISCORD_STATE_FILE` | Override for routing state | no |

The webhook is a credential. Keep it out of shell history, screenshots, issue
reports, prompts, and repository files.
Plugin hooks default state to Codex's writable `PLUGIN_DATA` directory. For
manual shell diagnostics, set `CODEX_DISCORD_STATE_FILE` to the same explicit
absolute path used by the Codex launch environment; otherwise the standalone
command falls back to `~/.codex/codex-discord/routing.json`.

## Opt-in installed-plugin smoke

No ordinary test contacts Discord. After install, configuration, and hook
trust, start a disposable Codex task and complete two turns. Confirm the first
`Stop` creates a forum post and the second appends to it. Trigger only a
harmless permission request, deny it, and confirm the attention message
mentions only the configured user. The test is live and creates durable
Discord content, so it remains explicitly opt-in.

For a transport-only release smoke, assign a fresh
`CODEX_DISCORD_STATE_FILE` and run `doctor --send-test` twice. The first
delivery creates the diagnostic forum post and the second updates that same
post. Diagnostic output is credential-free.

## Remaining limitations

- Delivery is best effort. There is no durable outbound queue, so an outage
  that outlasts bounded retries can lose a notification.
- Replay suppression is not distributed exactly-once delivery. A crash after
  Discord accepts a message but before state replacement can duplicate it.
- Routing state has no automatic expiry, and resetting it starts new forum
  posts without deleting old Discord content.
- Lifecycle evidence is version- and surface-specific. Desktop
  `PermissionRequest` remains unobserved, and Codex upgrades require renewed
  offline and opt-in live verification.
- Push-notification behavior remains unknown because the validating user's
  macOS and phone notifications were disabled. Mention rendering itself was
  verified.
- The package currently requires Python 3.9+, POSIX `fcntl`, and Codex plugin
  support. Windows is unsupported.
- A real `codex plugin add` remains a user opt-in because it mutates
  process-wide Codex configuration.

Discord-to-Codex replies and commands are deliberately absent. A future
two-way design must authenticate the Discord actor and bind it to the intended
Codex session, authorize every action, isolate permission decisions, reject
replay, defend against prompt injection and hostile message content, preserve
an audit trail, and rate-limit control traffic. Incoming Discord text must
never become an implicit tool approval.

## Disable and remove

Removing the plugin must preserve unrelated hooks:

1. Run `codex plugin remove codex-discord@codex-discord`, restart
   Codex, and verify `/hooks` no longer lists the plugin's two handlers.
   Disabling all hooks globally is broader and is not required.
2. Delete `PLUGIN_DATA/config.json` and stop exporting the three configuration
   variables. Removing a local value does not revoke the Discord webhook.
3. Retain `PLUGIN_DATA/routing.json` and its adjacent lock file for thread
   continuity, or remove both only after the hooks are disabled. Removing
   state does not delete Discord posts.
4. Delete the Discord webhook to revoke it, and remove its value from the
   chosen secret manager.
5. Remove the marketplace separately only if no other installed plugin uses
   it.

The non-mutating removal checklist is also available with:

```sh
/usr/bin/python3 scripts/codex-discord uninstall
```
