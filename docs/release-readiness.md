# Release readiness

The one-way Codex-to-Discord integration is ready for use within its documented
macOS/POSIX and observed-Codex-version scope. Ordinary verification uses only
local loopback HTTP services and synthetic credentials.

## Durable offline checks

Run the complete suite with any live Discord settings removed:

```sh
env -u CODEX_DISCORD_WEBHOOK_URL \
  -u CODEX_DISCORD_DESTINATION_TYPE \
  -u CODEX_DISCORD_MENTION_USER_ID \
  -u CODEX_DISCORD_STATE_FILE \
  PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s tests -v
```

The retained tests exercise public commands, generic outgoing messages, hook
standard-input contracts, Discord-compatible HTTP requests, observable routing
and persistence, best-effort retry bounds, redaction, local diagnostics, and
an isolated copy of the plugin. The Slice 6 capture recorder and its tests were
removed after the observed event shapes were converted into synthetic public
hook fixtures.

Validate package structure and runtime parity separately:

```sh
python3 -m json.tool plugins/codex-discord/.codex-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/codex-discord/hooks/hooks.json >/dev/null
diff -ru --exclude=__pycache__ \
  codex_discord \
  plugins/codex-discord/runtime/codex_discord
```

The clean-copy diagnostic workflow is covered by the plugin package suite:

```sh
python3 -m unittest discover \
  -s tests \
  -p 'test_plugin_package.py' \
  -v
```

It copies only the packaged plugin to a temporary install root, assigns a
temporary `PLUGIN_DATA`, runs the local-only `doctor`, and exercises bundled
hooks against a loopback fake Discord service. It neither installs global
Codex configuration nor contacts Discord.

## Opt-in live release smoke

Make the real webhook and, when testing attention hooks, the numeric mention ID
available through untracked local configuration. Do not paste either value into
the command or repository. Then choose a fresh state path and run the packaged
diagnostic delivery twice:

```sh
export CODEX_DISCORD_STATE_FILE="/tmp/codex-discord-release-$(date +%s).json"
/usr/bin/python3 plugins/codex-discord/scripts/codex-discord doctor --send-test
/usr/bin/python3 plugins/codex-discord/scripts/codex-discord doctor --send-test
```

Both commands print credential-free JSON. With `text-channel`, confirm that
each delivery created an ordinary channel message and no thread. With
`forum-channel`, confirm that the first created a forum post and the second
appended to it. The smoke creates durable Discord content and is never part of
the offline suite. Remove the temporary JSON file and adjacent lock only after
the two commands finish if the state does not need to be retained.

## Remaining limitations

- Delivery is bounded and best effort; failed notifications are not queued for
  later replay.
- Durable event digests suppress acknowledged replays, but a crash between
  remote acceptance and local state replacement can duplicate a message.
- Routing entries do not expire automatically.
- The outgoing-message MVP uses the one text or forum webhook selected during
  connection; it does not select DMs, arbitrary per-call channels, or multiple
  destinations.
- The evidence covers the installed July 27, 2026 Codex CLI and paired desktop
  build. Desktop `PermissionRequest` was not observed, and future lifecycle
  schema compatibility must be retested after Codex upgrades.
- Rich automatic task titles are unavailable from the observed hook payloads.
- Discord push behavior is unknown because macOS and phone notifications were
  disabled during verification; deliberate mention rendering was verified.
- The package requires Python 3.9+, POSIX `fcntl`, and Codex plugin support.
  Windows is not supported.
- The repository includes a repo marketplace for installation, while automated
  checks use a clean package copy rather than mutating the user's process-wide
  Codex plugin configuration.

## Deferred two-way control

The release does not read Discord or let Discord start, resume, steer,
interrupt, or approve Codex work. Preserving the session-to-thread route is
only an architectural seam for a later design.

Before any inbound control is enabled, that design must provide:

- strong Discord actor authentication and session binding;
- per-action authorization, especially for tool permissions;
- replay prevention, rate limits, and auditable control events;
- prompt-injection and hostile-content isolation;
- explicit separation between a Discord message and a Codex tool approval;
- safe behavior for deleted users, compromised webhooks or bots, stale
  sessions, and concurrent replies.

Incoming text must never be treated as trusted instructions merely because it
arrived in the mapped forum post.
