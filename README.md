# Codex Discord

Codex Discord is a one-way Codex plugin that sends explicit messages,
completion updates, and needs-attention updates to a private Discord text or
forum channel.

Regular text-channel delivery creates ordinary messages without threads.
Optional forum delivery maps each Codex task or logical route to one forum
post. The plugin never reads Discord, approves tools, or lets Discord control
Codex.

## Install

Requirements:

- Codex with plugin and lifecycle-hook support;
- macOS or another POSIX system with Python 3.9+ at `/usr/bin/python3`;
- a private Discord server with a text or forum channel and incoming webhook;
- optionally, the numeric Discord user ID that should receive automatic
  attention mentions.

To install from GitHub:

```sh
codex plugin marketplace add SpielSoft/codex-discord
codex plugin add codex-discord@codex-discord
```

To install from a local clone:

```sh
git clone https://github.com/SpielSoft/codex-discord.git
cd codex-discord
codex plugin marketplace add .
codex plugin add codex-discord@codex-discord
```

Restart Codex and start a new task after installation. The plugin's `Stop` and
`PermissionRequest` hooks are optional; inspect and trust them only if you want
automatic lifecycle notifications.

The repository is a standard Codex repo marketplace:

```text
.agents/plugins/marketplace.json
plugins/codex-discord/
├── .codex-plugin/plugin.json
├── hooks/hooks.json
├── runtime/codex_discord/
├── scripts/codex-discord
└── skills/
```

## First run

Choose the plugin starter **Connect Discord**, or invoke `$discord`. It guides
you through:

1. choosing ordinary text-channel delivery (recommended) or forum delivery;
2. creating a webhook for that Discord channel;
3. optionally copying a numeric user ID for automatic attention mentions;
4. pasting the webhook into a private connection window opened by Codex;
5. receiving one visible Discord connection-test message and confirmation.

The webhook field is password-style and the connection window is served only
from localhost. Codex does not ask you to run a terminal command or expose the
installed plugin path. Configuration is saved only after Discord accepts the
test, in the plugin's private `PLUGIN_DATA/config.json` with owner-only
permissions. Do not paste the webhook into a Codex prompt, issue, screenshot,
or repository file. PersonalAssistant does not need lifecycle hooks or an
attention user ID.

To send one free-form message to the configured destination, ask Codex to send
or post it to Discord, or invoke `$discord-outgoing-message`. Codex calls the
native `discord_send_message` tool, analogous to Slack's direct send-message
surface. Explicit send intent writes immediately; asking for a draft does not.
A deterministic idempotency key can suppress duplicate automation runs.

For a text channel, each tool call creates one ordinary channel message and no
Discord thread. For a forum channel, the first event for a route creates a
forum post and later events can append to it.

See the [plugin guide](plugins/codex-discord/README.md) for managed environment
overrides, diagnostics, removal, and live verification.

## Behavior

| Codex state | Discord behavior |
| --- | --- |
| Completed | Post without a mention |
| Needs input or approval | Post and mention the configured user |
| Blocked or failed | Post and mention the configured user |
| Explicit outgoing message | Send one ordinary text-channel message or one routed forum message |
| Routine tool activity | No post |

Delivery is bounded and best effort. Discord failure never changes the Codex
task result. Messages are sanitized, length-limited, and sent with restrictive
mention controls.

## Development

The root `codex_discord/` package is the development source. The distributable
runtime under `plugins/codex-discord/runtime/codex_discord/` must remain
identical.

Run the offline suite:

```sh
env -u CODEX_DISCORD_WEBHOOK_URL \
  -u CODEX_DISCORD_DESTINATION_TYPE \
  -u CODEX_DISCORD_MENTION_USER_ID \
  -u CODEX_DISCORD_STATE_FILE \
  PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s tests -v
```

Validate the package:

```sh
python3 /path/to/plugin-creator/scripts/validate_plugin.py \
  plugins/codex-discord
diff -ru --exclude=__pycache__ \
  codex_discord \
  plugins/codex-discord/runtime/codex_discord
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes and
[SECURITY.md](SECURITY.md) before reporting a credential or delivery issue.

## Documentation

- [Plugin connection and operation](plugins/codex-discord/README.md)
- [Release readiness and limitations](docs/release-readiness.md)
- [Architecture and project history](docs/architecture-history.md)
- [Lifecycle compatibility evidence](docs/lifecycle-spike.md)
- [Product requirements](docs/product-requirements.md)
- [Implementation roadmap](docs/implementation-roadmap.md)
- [Outgoing-message MVP decision](docs/outgoing-message-mvp.md)
- [Public publishing checklist](docs/publishing.md)

## Distribution status

The GitHub/repo-marketplace layout is ready for local, CLI, and team
distribution. Repository metadata identifies SpielSoft as the publisher and
the project is licensed under MIT. Public universal-directory submission is a
separate process that still requires final listing assets and hosted support,
privacy-policy, and terms-of-service URLs.

## License

Codex Discord is available under the [MIT License](LICENSE).
