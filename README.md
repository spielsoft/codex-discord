# Codex Discord

Codex Discord is a one-way Codex plugin that sends completion and
needs-attention updates to a private Discord forum.

Each Codex task gets one forum post. Later turns append to that post, and only
attention states deliberately mention the configured user. The plugin never
reads Discord, approves tools, or lets Discord control Codex.

## Install

Requirements:

- Codex with plugin and lifecycle-hook support;
- macOS or another POSIX system with Python 3.9+ at `/usr/bin/python3`;
- a private Discord server with a forum channel and incoming webhook;
- the numeric Discord user ID that should receive attention mentions.

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

Restart Codex and start a new task after installation. Inspect and trust the
plugin's `Stop` and `PermissionRequest` hooks before enabling them.

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

Choose the plugin starter **Set up Codex Discord notifications**, or invoke
`$discord-setup`. It guides you through:

1. creating a webhook for the destination Discord forum channel;
2. copying your numeric Discord user ID;
3. running the masked local setup command;
4. running the local-only health check;
5. sending one explicit test notification.

The webhook is entered in a hidden terminal prompt and stored in the plugin's
private `PLUGIN_DATA/config.json` with owner-only permissions. Do not paste it
into a Codex prompt, command argument, issue, screenshot, or repository file.

The plugin does not require a pre-existing forum post or post name. The first
event for a session creates `Codex task — <project>` and stores the returned
Discord thread ID. Later events for that session append to the same post.

See the [plugin guide](plugins/codex-discord/README.md) for managed environment
overrides, diagnostics, removal, and live verification.

## Behavior

| Codex state | Discord behavior |
| --- | --- |
| Completed | Post without a mention |
| Needs input or approval | Post and mention the configured user |
| Blocked or failed | Post and mention the configured user |
| Explicit milestone | Post without a mention |
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

- [Plugin setup and operation](plugins/codex-discord/README.md)
- [Release readiness and limitations](docs/release-readiness.md)
- [Architecture and project history](docs/architecture-history.md)
- [Lifecycle compatibility evidence](docs/lifecycle-spike.md)
- [Product requirements](docs/product-requirements.md)
- [Implementation roadmap](docs/implementation-roadmap.md)
- [Public publishing checklist](docs/publishing.md)

## Distribution status

The GitHub/repo-marketplace layout is ready for local, CLI, and team
distribution. Repository metadata identifies SpielSoft as the publisher and
the project is licensed under MIT. Public universal-directory submission is a
separate process that still requires final listing assets and hosted support,
privacy-policy, and terms-of-service URLs.

## License

Codex Discord is available under the [MIT License](LICENSE).
