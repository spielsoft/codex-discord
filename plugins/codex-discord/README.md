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
- `skills/discord-milestone/`: focused workflow for user-requested milestones.

The manifest intentionally omits a `hooks` field. Codex discovers
`hooks/hooks.json` by convention. Hook commands resolve installed code through
`PLUGIN_ROOT` and default writable routing state to
`PLUGIN_DATA/routing.json`. No credential or user-specific configuration is
stored in the package.

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

This repository package intentionally contains no marketplace or user-global
configuration. To test it as an installed plugin, place the complete
`codex-discord` directory under a local marketplace's `plugins/` directory and
add a marketplace entry whose source is `./plugins/codex-discord`. Then:

```sh
codex plugin marketplace add /absolute/path/to/marketplace
codex plugin add codex-discord@your-marketplace-name
```

Those commands mutate the user's Codex plugin configuration and are therefore
an explicit opt-in step. Start a new Codex task after installation, run
`/hooks`, inspect the plugin source, and trust exactly the two packaged hooks.
Changed hook definitions require review again.

The installed `codex-cli 0.146.0-alpha.3.1` exposes no `--config-dir` or
`--config-file` option on `plugin`, `plugin marketplace add`, or `plugin add`.
Codex's documented configuration base is the process-wide `CODEX_HOME`;
repository checks intentionally do not repoint `CODEX_HOME` or `HOME`.
Package tests instead perform a clean copy into a temporary install root and
exercise the same manifest, hooks, commands, and bundled runtime without
invoking the user-config-mutating plugin CLI. A real marketplace add/install
remains the explicit opt-in procedure above.

## Configure and diagnose

Supply configuration to the process that launches Codex:

| Variable | Purpose | Required |
| --- | --- | --- |
| `CODEX_DISCORD_WEBHOOK_URL` | Incoming webhook for a Discord forum channel | yes |
| `CODEX_DISCORD_MENTION_USER_ID` | Numeric 17–20 digit attention target | yes |
| `CODEX_DISCORD_STATE_FILE` | Override for routing state | no |

The webhook is a credential. Keep it in local secret storage and never in
plugin files, shell history, screenshots, issue reports, or command output.
Plugin hooks default state to Codex's writable `PLUGIN_DATA` directory. For
manual shell diagnostics, set `CODEX_DISCORD_STATE_FILE` to the same explicit
absolute path used by the Codex launch environment; otherwise the standalone
command falls back to `~/.codex/codex-discord/routing.json`.

From the installed plugin directory, run:

```sh
/usr/bin/python3 scripts/codex-discord setup
/usr/bin/python3 scripts/codex-discord doctor
```

`doctor` is local-only by default. It validates configuration and state without
contacting Discord or printing credentials. An explicit test delivery is:

```sh
/usr/bin/python3 scripts/codex-discord doctor --send-test
```

## Opt-in installed-plugin smoke

No ordinary test contacts Discord. After install, configuration, and hook
trust, start a disposable Codex task and complete two turns. Confirm the first
`Stop` creates a forum post and the second appends to it. Trigger only a
harmless permission request, deny it, and confirm the attention message
mentions only the configured user. The test is live and creates durable
Discord content, so it remains explicitly opt-in.

## Disable and remove

Removing the plugin must preserve unrelated hooks:

1. Run `codex plugin remove codex-discord@your-marketplace-name`, restart
   Codex, and verify `/hooks` no longer lists the plugin's two handlers.
   Disabling all hooks globally is broader and is not required.
2. Stop exporting the three configuration variables. Removing an environment
   value does not revoke a stored credential.
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
