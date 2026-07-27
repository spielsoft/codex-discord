# Codex to Discord

## Purpose

This workspace explores a Discord integration for Codex.

The initial goal is **one-way communication from Codex to Discord**. Codex
should be able to notify the user about completed work, failures, and work that
needs attention. Starting or controlling Codex from Discord is a possible later
phase, but it is not part of the initial implementation.

Development and testing will happen locally in this workspace. Once the design
has been proven, it should be packaged for reuse as either a Codex skill or,
more likely, a Codex plugin.

## Agreed user experience

Create a private Discord server dedicated to Codex.

```text
Codex server
├── #codex-inbox       Important alerts and failures
├── #codex-tasks       Forum: one post per Codex task
└── #codex-log         Optional low-priority activity
```

The central organizing principle is:

> One Codex task maps to one Discord forum post.

The forum post becomes a durable activity record for that Codex task. The
first notification creates the post; later turns append messages to the same
post. This keeps tasks independent without creating a large number of
top-level Discord channels.

The implementation must preserve a mapping like:

```text
Codex session ID -> Discord thread ID
```

Preserving this mapping from the beginning also creates a clean path to
two-way control in the future.

## Initial scope

The initial implementation should:

- Send messages from local Codex sessions to Discord.
- Create one Discord forum post for each Codex session.
- Append later notifications from that session to its existing post.
- Distinguish completed, needs-attention, blocked, and failed states.
- Mention the user only when attention is needed.
- Keep notifications short and useful.
- Store routing state locally.
- Avoid requiring a Discord bot or persistent service.

The initial implementation should not:

- Read messages from Discord.
- Start, resume, steer, or approve Codex work from Discord.
- Send raw transcripts, reasoning, secrets, or unrestricted command output.
- Create one Discord channel per Codex session.
- Require a hosted server.

## Proposed architecture

```text
Codex lifecycle event
        |
        v
Local notification adapter
        |
        +-- format and sanitize message
        +-- look up Codex session ID
        +-- create or reuse Discord thread
        +-- persist routing state
        |
        v
Discord incoming webhook
        |
        v
Forum post for the Codex task
```

Discord incoming webhooks are sufficient for the one-way phase. A webhook can
create a post in a forum channel using `thread_name`, then send later messages
to the resulting thread using `thread_id`. This avoids a bot token, Gateway
connection, and bot hosting.

Codex lifecycle hooks are the preferred automatic trigger:

- `Stop` for turn completion.
- `PermissionRequest` for work that needs the user's attention.
- Additional events only if testing demonstrates that they provide useful
  signal without excessive noise.

The workspace prototype now supports `Stop` and `PermissionRequest` through
notification-only hooks. Explicit normalized `blocked` and `failed` outcomes
use the same attention adapter; routine tool events are not registered.
Milestones use the separate `milestone --enable` operation. See
[docs/attention-hook.md](docs/attention-hook.md) for the public contracts and
durable duplicate-delivery rule.

The adapter should not depend heavily on parsing Codex transcript files.
Codex exposes a transcript path to hooks, but the transcript format is not a
stable public interface. During the prototype, we need to validate the best
reliable source for the final task summary. Possible approaches include:

1. Use the structured payload from Codex's notification mechanism if it
   exposes the final assistant message reliably.
2. Give Codex an explicit local `discord-notify` command or tool that accepts a
   structured summary, with a lifecycle hook as a fallback.
3. Use the Codex app-server event stream in a later, more capable version.

## Notification policy

Default behavior:

| State | Discord behavior |
| --- | --- |
| Completed | Post silently |
| Needs input or approval | Post and mention the user |
| Blocked | Post and mention the user |
| Failed | Post and mention the user |
| Milestone or progress | Post only when explicitly enabled |

Routine tool calls and intermediate reasoning should not generate messages.

A useful notification contains:

- Status.
- Task title.
- Project or workspace.
- Short result summary.
- Files changed, when relevant.
- Validation performed, when relevant.
- The next action, when there is one.

Example:

```text
🟢 Completed — Discord integration research

Project: Discord
Result: Selected an incoming-webhook architecture with one forum post per
Codex session.
Checks: OpenAI and Discord documentation reviewed.
Next: Configure a private test server and webhook.
```

Discord messages must be length-limited and sanitized. Unexpected mentions
should be disabled with `allowed_mentions`; the adapter should add the user's
mention deliberately only for attention states.

## State and configuration

The prototype needs:

- A Discord forum-channel webhook URL.
- The Discord user ID to mention for attention states.
- A small local state store mapping Codex session IDs to Discord thread IDs.
- Optional notification preferences.

Attention hooks additionally require the numeric Discord user ID in
`CODEX_DISCORD_MENTION_USER_ID`. This value and the webhook remain untracked
local configuration.

The intentional setup, local-only health check, opt-in test delivery,
credential-free diagnostic codes, routing-state lifecycle, and separate
disable/uninstall choices are documented in
[Setup and operations](docs/setup-and-operations.md). The public local check is:

```sh
python3 -m codex_discord doctor
```

It does not contact Discord unless `--send-test` is supplied explicitly.

The first state store can be a small JSON file. SQLite is unnecessary unless
concurrency or richer history makes it useful.

Secrets must not be committed to the repository. For workspace testing, the
webhook URL should come from an environment variable or the macOS Keychain.
The final packaging should provide a deliberate setup command rather than
asking users to edit source files.

## Best-effort delivery contract

The public `publish` command separates notification delivery from the result of
the Codex task that produced it. Once a notification is locally valid, the
command exits successfully and prints a JSON delivery outcome. Successful
delivery uses `status: "published"`; exhausted or permanent transport failures
use `status: "delivery-failed"` with a credential-free diagnostic, the attempt
count, and whether the failure was transient. Invalid JSON, invalid local
configuration, and invalid notification fields still produce a nonzero exit.

Default delivery is bounded to three HTTP attempts and six seconds overall.
Each connection or read operation is capped at two seconds. HTTP 429, 408, 425,
5xx responses, connection failures, and read timeouts are retryable. Retry
delays honor Discord's `Retry-After` or `X-RateLimit-Reset-After` value when
present, fall back to a short exponential delay, and are capped at two seconds.
Other 4xx responses are permanent and are not retried as ordinary transport
failures. The command exposes `--max-attempts`,
`--request-timeout-seconds`, and `--delivery-timeout-seconds` for a stricter
local budget.

A stored thread route has one narrow recovery rule. When an append to a known
thread returns HTTP 403 or 404, the adapter removes only that session's route
and makes at most one fresh forum-post attempt within the same attempt and time
budgets. A successful replacement becomes the new route. If replacement
fails, that session remains unmapped so a later invocation can try creating a
new post; routes for other sessions are unchanged. HTTP 401 and failures while
creating a new post never trigger stale-route recovery.

## Skill or plugin?

A skill can teach Codex when and how to send a structured Discord message. It
is useful for explicit notifications such as "send me a milestone update."
However, a skill alone does not provide the strongest guarantee that every
completion or permission request will be reported.

A plugin can bundle:

- Lifecycle hooks.
- The local notification adapter.
- A companion skill for explicit messages and user-facing workflows.
- Setup and diagnostic commands.
- Optional MCP tools or app-server integration in later phases.

Because automatic notifications and persistent task routing are core
requirements, the current expectation is:

> Build and validate the behavior in this workspace, then package it as a
> Codex plugin containing a small companion skill.

This remains a hypothesis until the prototype confirms the relevant Codex hook
behavior across the Codex desktop app and CLI.

## Development phases

### Phase 0 — Transport spike

- Create a private test Discord server and forum channel.
- Create an incoming webhook for the forum channel.
- Send a manually generated test message.
- Create a forum post and append a second message using its thread ID.
- Verify mobile notifications and mention behavior.

### Phase 1 — Workspace prototype

- Implement the local notification adapter in this repository.
- Read secrets from a safe local source.
- Format and sanitize messages.
- Store the session-to-thread mapping locally.
- Add automated tests using a fake HTTP endpoint; live Discord tests remain
  opt-in.

### Phase 2 — Codex lifecycle integration

- Connect completion notifications to a Codex `Stop` hook.
- Connect attention notifications to `PermissionRequest`.
- Determine the reliable source for task title and result summary.
- Test from both Codex desktop and the CLI.
- Add retry and rate-limit handling without blocking Codex completion.

### Phase 3 — Reusable package

- Package the proven implementation as a Codex plugin.
- Include a companion skill for explicit Discord updates.
- Add setup, health-check, and uninstall instructions.
- Keep tokens and user-specific configuration outside the package.

### Future phase — Two-way control

A Discord bot could listen for replies or commands, map the Discord thread back
to the Codex session, and use Codex app-server APIs to resume or steer the
task. Authentication, authorization, approval handling, and prompt-injection
risks must be designed before enabling this phase.

## Prototype acceptance criteria

The workspace prototype is successful when:

1. A completed Codex turn creates a forum post automatically.
2. A second turn in the same Codex session appends to the same post.
3. A different Codex session creates a different post.
4. Needs-attention and failure messages mention the configured user.
5. Routine successful completions do not mention the user.
6. No webhook secret or transcript content appears in repository files or
   diagnostic output.
7. A temporary Discord or network failure does not prevent Codex from
   completing its turn.
8. The core formatting, routing, sanitization, and retry behavior can be tested
   without contacting Discord.

## Open questions

- What should supply the initial forum-post title when a Codex task has no
  stable user-facing title?
- Which Codex notification surface provides the most reliable final summary in
  both the desktop app and CLI?
- Should completed notifications be silent Discord messages by default?
- Should separate projects share one forum channel and use tags, or receive
  separate forum channels?
- How long should stale session-to-thread mappings be retained?
- Should the prototype queue failed messages for retry, or make only a small
  number of immediate attempts?

## Primary references

- [Codex hooks](https://developers.openai.com/codex/hooks)
- [Codex plugins](https://developers.openai.com/plugins/build/plugins)
- [Codex app server](https://developers.openai.com/codex/app-server)
- [Discord webhooks](https://docs.discord.com/developers/resources/webhook)
- [Discord threads and forum channels](https://docs.discord.com/developers/topics/threads)
