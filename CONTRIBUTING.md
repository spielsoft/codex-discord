# Contributing

Contributions should preserve Codex independence, credential safety, and the
one-session-to-one-forum-post contract.

## Development setup

The project uses Python's standard library and `unittest`; no dependency
installation is required. Use Python 3.9 or newer on a POSIX system.

Run the complete offline suite:

```sh
env -u CODEX_DISCORD_WEBHOOK_URL \
  -u CODEX_DISCORD_MENTION_USER_ID \
  -u CODEX_DISCORD_STATE_FILE \
  PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s tests -v
```

The tests use loopback fake Discord services. They must not contact Discord or
require live credentials.

## Change workflow

1. Add or update a test through a public command, hook input, marketplace, or
   plugin interface.
2. Make the smallest implementation change that satisfies that contract.
3. Keep `codex_discord/` and
   `plugins/codex-discord/runtime/codex_discord/` identical.
4. Run the full offline suite and package checks.
5. Keep live Discord smoke tests explicit and opt-in.

Do not commit webhook URLs, Discord user IDs, routing state, hook captures,
transcripts, or local configuration. Use synthetic values in tests.

## Package checks

```sh
python3 -m json.tool \
  plugins/codex-discord/.codex-plugin/plugin.json >/dev/null
python3 -m json.tool \
  plugins/codex-discord/hooks/hooks.json >/dev/null
python3 -m json.tool \
  .agents/plugins/marketplace.json >/dev/null
diff -ru --exclude=__pycache__ \
  codex_discord \
  plugins/codex-discord/runtime/codex_discord
```

When available, also run the current `plugin-creator` validator against
`plugins/codex-discord` and the skill validator against each bundled skill.

## Pull requests

Explain the user-visible behavior, tests run, credential impact, and any live
Discord interaction. Do not include secrets or sanitized-but-identifiable
production captures in an issue or pull request.
