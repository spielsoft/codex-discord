# Codex to Discord Notification Integration

## Problem Statement

A Codex user who supervises multiple tasks needs a reliable way to learn when
work completes, fails, becomes blocked, or requires attention without remaining
at the computer or repeatedly checking the Codex application.

Discord is already the user's team communication surface, but Codex does not
provide a first-party Discord integration comparable to its Slack
integrations. Existing Discord integrations generally focus on controlling an
agent from Discord or exposing broad Discord access. They do not provide the
small, one-way, local-first notification path required here.

The integration must make concurrent Codex tasks easy to distinguish. Creating
a Discord channel for every Codex task would clutter the server and require
unnecessary channel management. A notification feed alone would avoid that
clutter but would mix the histories of unrelated tasks.

The solution also needs to be safe and unobtrusive. It must not expose webhook
credentials, transcripts, reasoning, or unrestricted command output. Network
or Discord failures must not block Codex. Routine progress must not generate
notification fatigue. The initial implementation must remain small enough to
validate locally before it is packaged for reuse.

## Solution

Build a local notification adapter that sends selected Codex lifecycle events
to a private Discord server through an incoming webhook.

The Discord server will use a forum channel as the task index. Each Codex
session maps to one Discord forum post. The first notification for a session
creates a post, and subsequent notifications append to that post. A small
local routing store preserves the mapping between Codex session identifiers
and Discord thread identifiers.

The adapter will accept a normalized notification containing a session
identifier, status, title, project, result summary, validation summary, next
action, and mention policy. It will format and sanitize the notification,
resolve or create the Discord thread, deliver the message, and update routing
state behind one narrow publishing interface.

The first workspace prototype will use an incoming webhook and local
configuration, avoiding a Discord bot, hosted service, or persistent Gateway
connection. Codex completion and attention events will eventually enter
through lifecycle hooks. The prototype will explicitly test which Codex
surface supplies a reliable task title and final summary without depending on
the unstable transcript format.

After the behavior is proven from the workspace, package it as a Codex plugin
that bundles lifecycle hooks, the adapter, setup and diagnostic commands, and
a companion skill for explicit milestone notifications. A skill by itself is
not the expected final package because automatic lifecycle delivery and
persistent routing are core requirements.

## User Stories

1. As a Codex user, I want a Discord notification when a task completes, so
   that I can leave my computer without losing track of the work.
2. As a Codex user, I want a Discord notification when a task fails, so that I
   can respond promptly.
3. As a Codex user, I want a Discord notification when a task is blocked, so
   that I know intervention is required.
4. As a Codex user, I want a Discord notification when Codex requests
   permission or input, so that unattended work does not stall unnoticed.
5. As a Codex user, I want successful completions delivered without mentioning
   me, so that routine work does not create intrusive alerts.
6. As a Codex user, I want failures, blockers, and input requests to mention
   me, so that urgent events reach my Discord notification settings.
7. As a Codex user, I want one Discord forum post per Codex task, so that
   independent task histories remain separate.
8. As a Codex user, I want later turns in the same Codex session appended to
   the same forum post, so that the complete task history is easy to follow.
9. As a Codex user, I want different Codex sessions to create different forum
   posts, so that concurrent work is not mixed together.
10. As a Codex user, I want automatically generated post titles to identify the
    task and project, so that I can scan the forum quickly.
11. As a Codex user, I want concise result summaries, so that I can understand
    the outcome from a phone notification.
12. As a Codex user, I want notifications to show relevant validation results,
    so that I can distinguish completed work from merely attempted work.
13. As a Codex user, I want notifications to show the next action when one
    exists, so that I know what to do when I return.
14. As a Codex user, I want optional explicit milestone notifications, so that
    long-running tasks can report meaningful progress without reporting every
    tool call.
15. As a Codex user, I want routine intermediate activity suppressed, so that
    the Discord server remains useful rather than noisy.
16. As a Codex user, I want unexpected Discord mentions disabled, so that
    repository content or generated text cannot ping people or roles.
17. As a Codex user, I want long or malformed content safely bounded, so that
    every notification is accepted and rendered predictably by Discord.
18. As a Codex user, I want webhook credentials kept outside the repository, so
    that publishing the code does not compromise my Discord server.
19. As a Codex user, I want logs and errors to redact credentials, so that
    troubleshooting does not expose the webhook.
20. As a Codex user, I want network failures isolated from Codex completion, so
    that a Discord outage cannot prevent my task from finishing.
21. As a Codex user, I want bounded retries for transient failures, so that
    temporary Discord problems do not immediately lose a notification.
22. As a Codex user, I want routing state written safely, so that an interrupted
    update does not corrupt every session mapping.
23. As a Codex user, I want stale or invalid thread mappings recovered
    gracefully, so that an archived, deleted, or inaccessible post does not
    permanently break a session.
24. As a developer, I want the formatter, router, state store, and transport
    testable without Discord, so that most development does not contact the
    live service.
25. As a developer, I want live Discord tests to be explicitly enabled, so that
    ordinary test runs do not send messages or require secrets.
26. As a developer, I want a diagnostic command that validates configuration
    without exposing credentials, so that setup failures are understandable.
27. As a developer, I want a transport spike to prove forum-post creation and
    follow-up delivery, so that implementation rests on verified Discord
    behavior.
28. As a developer, I want Codex desktop and CLI lifecycle behavior tested, so
    that packaging does not assume one unsupported surface.
29. As a developer, I want the summary source evaluated without relying on a
    private transcript schema, so that Codex updates do not silently break
    notifications.
30. As a plugin user, I want an intentional setup workflow, so that I can
    configure a webhook, mention target, and preferences without editing
    package source.
31. As a plugin user, I want a health check, so that I can verify the
    integration before relying on it.
32. As a plugin user, I want uninstall instructions that identify retained
    state and credentials, so that removal is predictable.
33. As a future integrator, I want the Codex-session-to-Discord-thread mapping
    preserved, so that two-way control can later reuse the same task identity.
34. As a security-conscious user, I want inbound Discord control excluded from
    the first release, so that authentication and prompt-injection risks are
    not introduced prematurely.

## Implementation Decisions

- The first release is one-way: Codex sends to Discord, but Discord cannot
  start, resume, steer, or approve Codex work.
- A private Discord server contains a forum channel that serves as the task
  index.
- One Codex session maps to one Discord forum post. The stable identity is the
  Codex session identifier, not a generated title.
- Discord incoming webhooks are the transport for the one-way phase. The
  implementation will not require a bot user, Gateway connection, or hosted
  service.
- The local adapter exposes one narrow publish operation over a normalized
  notification model. Discord payload construction, thread routing, state
  persistence, retry behavior, and redaction remain encapsulated behind that
  operation.
- The normalized notification model distinguishes completed, needs-input,
  blocked, failed, and optional milestone states.
- The model carries structured fields rather than a preformatted transcript:
  session identity, task title, project, result, validation, next action, and
  intended mention behavior.
- The Discord transport creates a forum post for an unknown session and appends
  to the stored Discord thread for a known session.
- Routing state begins as a small local JSON store. Updates must be atomic, and
  access must tolerate multiple notification processes without corrupting the
  store. SQLite should only replace JSON if concurrency testing demonstrates a
  real need.
- The workspace prototype reads the webhook URL and mention target from
  environment-based configuration. macOS Keychain integration may be added
  later, but secrets will never be stored in tracked project files.
- Outbound content is length-limited and sanitized. Discord
  `allowed_mentions` is restrictive by default; the configured user mention is
  added deliberately only for attention states.
- Notifications contain summaries and validation evidence, not raw
  transcripts, hidden reasoning, complete diffs, or unrestricted tool output.
- Transport work is best effort and bounded. Hook execution must return
  promptly; retry behavior must not turn Discord availability into a Codex
  availability dependency.
- A fake HTTP service or injected transport boundary will support deterministic
  offline tests. Live Discord tests are opt-in and credential-gated.
- The transport spike will verify creation of a forum post, extraction of its
  thread identifier, and delivery of a follow-up message before lifecycle
  integration begins.
- Codex `Stop` and `PermissionRequest` hooks are the preferred lifecycle
  triggers. The implementation will validate their behavior in both Codex
  desktop and CLI.
- Transcript parsing is not a supported core dependency. A focused spike will
  compare structured Codex notification data, an explicit notification command
  or tool, and app-server events as sources for titles and summaries.
- The initial local implementation should minimize third-party runtime
  dependencies. Packaging portability will be evaluated before the workspace
  prototype is promoted to a reusable plugin.
- The target reusable artifact is a Codex plugin containing hooks, the adapter,
  configuration diagnostics, and a companion skill for explicit milestone
  updates.
- Project tags, multiple forum channels, rich interactive Discord components,
  and status-tag mutation are deferred until the simple task-thread model is
  proven.
- The Discord setup itself is a human-in-the-loop activity because a user must
  create or select the private server, forum channel, webhook, and notification
  preferences.

## Testing Decisions

- Tests will assert public behavior and stable boundaries rather than internal
  method calls, private helper structure, or the exact layout of the state
  file.
- Formatter tests will verify status presentation, length limits, explicit
  mention behavior, suppression of unexpected mentions, and safe handling of
  malformed or hostile text.
- Routing tests will verify that the first event for a session creates a forum
  post, later events append to it, and a different session creates a different
  post.
- State tests will verify persistence across processes, atomic updates,
  recovery from missing state, and safe handling of invalid or stale mappings.
- Transport contract tests will use a local fake HTTP endpoint to verify
  Discord request shapes, success responses, rate limits, transient failures,
  bounded retries, and redacted diagnostics.
- Lifecycle integration tests will feed representative `Stop` and
  `PermissionRequest` payloads through the public adapter boundary.
- Hook tests will verify that a slow or unavailable Discord endpoint cannot
  change the Codex task result and that the hook finishes within a defined
  timeout.
- Configuration tests will verify missing, malformed, and valid settings
  without printing the webhook credential.
- A manually enabled live smoke test will create a forum post and append a
  second message in the private test server.
- Human verification will confirm Discord mobile notification behavior,
  deliberate mentions, silent completion behavior, and readability.
- Desktop and CLI verification will use the same observable acceptance
  scenarios so differences in lifecycle payloads are recorded explicitly.
- Plugin packaging tests will install the package in a clean test environment,
  run its health check, exercise a notification, and verify removal guidance.
- TDD implementation slices will be followed by a dedicated test-cleanup pass.
  That pass will remove development-only scaffolding tests while preserving the
  smallest useful suite protecting formatter, routing, transport, security,
  and lifecycle contracts.
- This repository has no implementation or prior test suite yet. The first
  tracer bullet will establish the test harness and public behavioral seam;
  later tests should follow that precedent.

## Out of Scope

- Reading Discord messages.
- Starting, resuming, steering, interrupting, or approving Codex work from
  Discord.
- A Discord bot, Gateway connection, or permanently hosted relay.
- Supporting arbitrary chat platforms through a generalized notification
  framework.
- Reproducing the full Codex transcript in Discord.
- Sending hidden reasoning, secrets, complete diffs, or unrestricted command
  output.
- Creating one Discord channel per Codex task.
- A full management UI.
- Multi-user authorization and role management.
- Discord slash commands, buttons, modals, reactions, and other interactive
  controls.
- Automatic provisioning of a Discord server, forum channel, or webhook.
- Guaranteed delivery during long offline periods in the first prototype.
- App-server-based two-way control.
- Broad platform portability promises before the local workspace prototype and
  packaging spike have established the supported environments.

## Further Notes

- The immediate proving ground is this workspace on macOS.
- The user will need to perform the Discord-side provisioning and provide the
  resulting webhook through a safe local configuration mechanism.
- Completed notifications should default to non-mentioning delivery. Whether
  they also suppress Discord push notifications will be confirmed during the
  human transport test.
- A task title is presentation metadata and may improve over time; routing must
  never depend on it.
- Sending a message to an archived Discord thread can reactivate it unless the
  thread is locked. The adapter still needs explicit recovery behavior for
  deleted, locked, or inaccessible threads.
- The implementation roadmap should use thin, dependency-ordered vertical
  slices. Each automated slice must leave a demonstrable end-to-end behavior,
  not merely an isolated layer.
- Primary technical references are the official Codex hooks, plugins, and app
  server documentation and the official Discord webhook and thread
  documentation linked from the workspace overview.
