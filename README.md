# Codex Discord

Codex Discord is a one-way Codex plugin that sends explicit messages,
completion updates, and needs-attention updates to a private Discord forum.

Each Codex task gets one forum post. Later turns append to that post, and only
attention states deliberately mention the configured user. The plugin never
reads Discord, approves tools, or lets Discord control Codex.

## Install

Requirements:

- Codex with plugin and lifecycle-hook support;
- macOS or another POSIX system with Python 3.9+ at `/usr/bin/python3`;
- a private Discord server with a forum channel and incoming webhook;
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

1. creating a webhook for the destination Discord forum channel;
2. optionally copying a numeric user ID for automatic attention mentions;
3. pasting the webhook into a private connection window opened by Codex;
4. receiving one visible Discord connection-test message and confirmation.

The webhook field is password-style and the connection window is served only
from localhost. Codex does not ask you to run a terminal command or expose the
installed plugin path. Configuration is saved only after Discord accepts the
test, in the plugin's private `PLUGIN_DATA/config.json` with owner-only
permissions. Do not paste the webhook into a Codex prompt, issue, screenshot,
or repository file. PersonalAssistant does not need lifecycle hooks or an
attention user ID.

The plugin does not require a pre-existing forum post or post name. The first
event for a session creates `Codex task — <project>` and stores the returned
Discord thread ID. Later events for that session append to the same post.

To send one free-form message to the configured destination, ask Codex to send
or post it to Discord, or invoke `$discord-outgoing-message`. Explicit send
intent writes immediately; asking for a draft does not. The skill can use a
stable route key for a recurring forum post and a deterministic idempotency key
to suppress duplicate automation runs.

See the [plugin guide](plugins/codex-discord/README.md) for managed environment
overrides, diagnostics, removal, and live verification.

## Behavior

| Codex state | Discord behavior |
| --- | --- |
| Completed | Post without a mention |
| Needs input or approval | Post and mention the configured user |
| Blocked or failed | Post and mention the configured user |
| Explicit outgoing message | Post once without a mention |
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
