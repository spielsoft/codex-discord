# Codex Stop hook

The Slice 7 hook turns a structured Codex `Stop` event into the same normalized
completion notification accepted by `publish_notification`. It supports the
observed Codex CLI and desktop event shapes.

## Input contract

The hook reads exactly one JSON object from standard input. It accepts only a
`Stop` event with a non-empty `session_id` and `cwd`:

- `session_id` is the stable routing key, so later turns append to the same
  Discord forum post.
- The basename of `cwd` is the project name.
- A usable `last_assistant_message` becomes the bounded, mention-safe result;
  Discord webhook URLs and obvious `token=`, `secret=`, or `password=` values
  are redacted first.
- A null, non-string, whitespace-only, or control-only message falls back to
  `Codex turn completed`.
- The automatic task title is `Codex task`. A richer explicit notification can
  create the session's post first with a better title; routing never depends
  on the title.

The hook does not inspect or open `transcript_path`.

## Configuration and exit behavior

`CODEX_DISCORD_WEBHOOK_URL` supplies the Discord forum webhook. It is required
for delivery and must be inherited by the Codex process; never put it in a
tracked hook definition. `CODEX_DISCORD_STATE_FILE` can override the routing
file. Without that override, routing is stored at
`~/.codex/codex-discord/routing.json`.

The hook writes no standard output and always exits zero. Malformed input,
missing configuration, invalid local state, and exhausted Discord delivery are
reported only by a short credential-free diagnostic on standard error. The
underlying publisher retains its three-attempt, six-second delivery budget,
and the example Codex handler applies a seven-second outer timeout. Notification
failure therefore cannot replace the Codex turn result.

## Opt-in workspace use

`.codex/hooks.example.json` is deliberately not active. It also contains the
Slice 8 `PermissionRequest` handler documented in
[attention-hook.md](attention-hook.md). To run a completion smoke check:

1. Make `CODEX_DISCORD_WEBHOOK_URL` available to the Codex CLI process through
   untracked local environment configuration.
2. Optionally set `CODEX_DISCORD_STATE_FILE` to an untracked test routing file.
3. Copy `.codex/hooks.example.json` to `.codex/hooks.json`.
4. Start a new Codex CLI session in this repository, open `/hooks`, review the
   exact project hook, and trust it.
5. Complete one ordinary turn, then complete a second turn in the same
   session. Confirm that Discord created one post and appended the second
   completion.
6. Remove `.codex/hooks.json` after the smoke test. Plugin packaging will
   replace this workspace-only activation path in Slice 10.
