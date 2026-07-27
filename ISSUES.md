# Codex to Discord Implementation Roadmap

Treat [ISSUES_PRD.md](ISSUES_PRD.md) as the product and architecture source.
Work through these tracer-bullet slices in dependency order.

## Progress

- [x] Slice 1: Publish one completion through a fake Discord service
- [x] Slice 2: Preserve task-to-thread continuity
- [x] Slice 3: Deliver safe attention notifications
- [x] Slice 4: Keep Codex independent from Discord failures
- [x] Slice 5: Prove the transport in a private Discord server
- [ ] Slice 6: Select the reliable Codex lifecycle inputs
- [ ] Slice 7: Notify automatically when a Codex turn stops
- [ ] Slice 8: Notify automatically when Codex needs attention
- [ ] Slice 9: Add setup and operational diagnostics
- [ ] Slice 10: Package the integration as a Codex plugin
- [ ] Slice 11: Clean the test suite and verify release readiness

## Slice 1: Publish one completion through a fake Discord service

### Type

`AFK`

### What to build

Establish the smallest complete local path from a structured completed-task
notification to a Discord-compatible HTTP request. A public command accepts
one notification, creates a forum post through a local fake service, captures
the returned thread identity, and reports success without requiring real
Discord credentials. This slice establishes the runtime, test harness, and
narrow publishing interface used by later slices.

### Acceptance criteria

- [x] A command accepts a completed notification with session identity, task
      title, project, result, validation summary, and optional next action.
- [x] The command sends a Discord-compatible forum-post request containing a
      readable completion message.
- [x] The request creates a thread by name and asks Discord to return the
      created message or thread identity.
- [x] The returned Discord thread identity is captured for the originating
      Codex session.
- [x] The complete behavior is tested against a local fake HTTP service using
      the public command or publishing interface.
- [x] The ordinary test suite requires neither network access nor Discord
      credentials.

### Blocked by

None - can start immediately.

### User stories covered

- User stories 1, 10–13, 24, 25, and 27.

## Slice 2: Preserve task-to-thread continuity

### Type

`AFK`

### What to build

Extend the publishing path so repeated notifications for one Codex session
append to its existing Discord thread while a different session creates a new
forum post. Persist routing across separate command invocations using a safe
local store, making the task-to-thread relationship observable through the
fake service.

### Acceptance criteria

- [x] The first notification for a session creates a forum post and persists
      its Discord thread identity.
- [x] A later notification for the same session targets the stored thread
      instead of creating another post.
- [x] A notification for a different session creates a different forum post.
- [x] Routing survives process exit and a later command invocation.
- [x] State updates cannot leave a partially written routing store.
- [x] Missing or initially empty state is handled without manual repair.
- [x] Behavioral tests verify create, append, separate-session, and restart
      scenarios without relying on the state file's private layout.

### Blocked by

- Slice 1: Publish one completion through a fake Discord service.

### User stories covered

- User stories 7–9, 22, 24, and 33.

## Slice 3: Deliver safe attention notifications

### Type

`AFK`

### What to build

Support the agreed notification policy end to end. Completed events remain
quiet, while needs-input, blocked, and failed events deliberately mention only
the configured user. Bound and sanitize all outbound content so task text
cannot create unexpected user, role, or channel mentions or exceed Discord
message limits.

### Acceptance criteria

- [x] Completed notifications do not mention the configured user.
- [x] Needs-input, blocked, and failed notifications deliberately mention the
      configured user.
- [x] Milestone notifications are rejected or suppressed unless explicitly
      enabled.
- [x] Arbitrary task content cannot mention users, roles, or everyone.
- [x] Deliberate attention mentions use a restrictive `allowed_mentions`
      policy that permits only the configured user.
- [x] Long titles and summaries are truncated into a readable,
      Discord-compatible message.
- [x] Empty, malformed, Unicode, and mention-shaped inputs have durable
      behavior tests through the public publishing interface.

### Blocked by

- Slice 1: Publish one completion through a fake Discord service.

### User stories covered

- User stories 2–6 and 14–17.

## Slice 4: Keep Codex independent from Discord failures

### Type

`AFK`

### What to build

Make outbound delivery best effort and operationally safe. Classify Discord
success, rate limiting, transient failure, permanent failure, stale routing,
and timeout outcomes. Retry only bounded transient cases, redact diagnostics,
and ensure the caller can finish promptly regardless of Discord availability.

### Acceptance criteria

- [x] Transient server and rate-limit responses receive bounded,
      delay-aware retries.
- [x] Authentication, validation, and other permanent failures are not retried
      indefinitely.
- [x] Connection failures and slow responses stop within a defined timeout and
      do not hang the caller.
- [x] A stale, deleted, or inaccessible thread mapping is handled according to
      a documented recovery rule without corrupting other mappings.
- [x] Logs and returned diagnostics never contain the webhook credential.
- [x] Delivery failure is observable but does not change the originating Codex
      task result.
- [x] Fake-service tests cover success, retry, timeout, permanent failure, and
      stale-routing recovery.

### Blocked by

- Slice 2: Preserve task-to-thread continuity.
- Slice 3: Deliver safe attention notifications.

### User stories covered

- User stories 19–23 and 26.

## Slice 5: Prove the transport in a private Discord server

### Type

`HITL`

### What to build

Provision the private Discord test destination and run the opt-in live smoke
path. Confirm that the same public publishing command creates one forum post,
appends a second message to it, creates a separate post for another session,
and produces the intended desktop and mobile notification behavior.

### Acceptance criteria

- [x] The user creates or selects a private server, forum channel, incoming
      webhook, and Discord account to mention.
- [x] Credentials and user-specific identifiers are supplied through untracked
      local configuration.
- [x] The live smoke command creates a readable forum post.
- [x] A second event for the same test session appears in the same post.
- [x] A different test session creates a different post.
- [ ] The user confirms whether ordinary completions should suppress Discord
      push notifications in addition to suppressing mentions. Unknown: the
      user keeps macOS and phone notifications disabled.
- [ ] The user confirms that attention states produce the intended mobile
      notification and mention behavior. The mention rendered correctly;
      desktop/mobile delivery is unknown because notifications are disabled.
- [x] The observed decisions are recorded without recording the webhook URL.

### Slice 5 outcome

Live forum-post creation, same-session append, separate-session creation, and
the deliberate attention mention all passed on July 27, 2026. Discord initially
returned HTTP 403 until the adapter supplied the API-required `User-Agent`;
an offline regression now protects that request contract. By explicit user
direction, desktop/mobile notification delivery and the routine-completion push
policy remain unknown rather than blocking later slices.

### Blocked by

- Slice 4: Keep Codex independent from Discord failures.

### User stories covered

- User stories 1–9, 18, 25, and 27.

## Slice 6: Select the reliable Codex lifecycle inputs

### Type

`HITL`

### What to build

Run a focused compatibility spike across Codex desktop and CLI to determine
how completion and permission events should enter the adapter and where a
stable task title and final summary can be obtained. Compare lifecycle hooks,
structured notification data, and an explicit notification command without
adopting transcript parsing as a core contract. Record one supported decision
and representative fixtures for the implementation slices.

### Acceptance criteria

- [ ] A `Stop` event is observed and recorded in sanitized form from Codex CLI.
- [ ] A `Stop` event is observed and recorded in sanitized form from Codex
      desktop.
- [ ] A `PermissionRequest` event is observed where supported without granting
      unintended authority.
- [ ] The available session identity, turn identity, working directory, title,
      summary, and permission fields are compared across surfaces.
- [ ] Transcript parsing is either rejected or isolated as a documented
      best-effort fallback rather than a stable dependency.
- [ ] One completion-summary strategy is selected for the prototype, with its
      limitations and fallback behavior documented.
- [ ] Sanitized event fixtures are retained for automated lifecycle tests.

### Blocked by

- Slice 1: Publish one completion through a fake Discord service.

### User stories covered

- User stories 28 and 29, plus the lifecycle portions of user stories 1 and 4.

## Slice 7: Notify automatically when a Codex turn stops

### Type

`AFK`

### What to build

Connect the selected completion lifecycle input to the established publishing
path. A normal Codex turn completion should automatically create or update the
correct Discord task thread using the selected title and summary strategy,
while delivery remains best effort and testable with sanitized fixtures.

### Acceptance criteria

- [ ] The supported completion event invokes the same public publishing path
      proven by earlier slices.
- [ ] The event's Codex session identity controls Discord thread routing.
- [ ] The selected task-title and summary strategy produces a useful
      notification without exposing a raw transcript.
- [ ] A second turn in the same Codex session appends to the original Discord
      thread.
- [ ] Hook execution returns within the defined timeout when Discord is
      unavailable.
- [ ] Lifecycle fixture tests verify completed delivery, repeat-turn routing,
      malformed input, and transport failure.
- [ ] An opt-in live test demonstrates an automatic completion from at least
      one supported Codex surface.

### Blocked by

- Slice 4: Keep Codex independent from Discord failures.
- Slice 5: Prove the transport in a private Discord server.
- Slice 6: Select the reliable Codex lifecycle inputs.

### User stories covered

- User stories 1, 7–13, 20, 28, and 29.

## Slice 8: Notify automatically when Codex needs attention

### Type

`AFK`

### What to build

Connect permission, blocked, and failed lifecycle outcomes to the safe
attention-notification path, and expose an explicit milestone operation for
long-running tasks. Attention messages should update the same Discord task
thread and mention only the configured user.

### Acceptance criteria

- [ ] A supported permission or input request posts a needs-attention message
      to the correct Discord task thread.
- [ ] Supported blocked and failed outcomes use their distinct status and
      deliberate mention behavior.
- [ ] Attention notifications do not approve, deny, or otherwise control
      Codex.
- [ ] An explicit milestone operation can publish to the current task thread
      when enabled.
- [ ] Routine intermediate tool activity produces no Discord messages.
- [ ] Duplicate lifecycle delivery is handled according to a documented
      idempotency rule.
- [ ] Fixture tests cover each attention state, milestone opt-in, suppression,
      and duplicate delivery.

### Blocked by

- Slice 7: Notify automatically when a Codex turn stops.

### User stories covered

- User stories 2–6 and 14–16.

## Slice 9: Add setup and operational diagnostics

### Type

`AFK`

### What to build

Provide an intentional local setup and support workflow. Users can discover
required settings, validate configuration without leaking secrets, run an
opt-in health check, inspect safe delivery diagnostics, and understand what
state or credentials remain when the integration is disabled or removed.

### Acceptance criteria

- [ ] Setup documentation identifies the required Discord objects,
      configuration values, and safe secret-storage expectations.
- [ ] A diagnostic command distinguishes missing, malformed, and usable
      configuration without printing the webhook credential.
- [ ] A health check can validate local configuration without sending a
      message, and can send an explicit opt-in test message when requested.
- [ ] Diagnostics identify common authentication, permission, forum-channel,
      routing, timeout, and rate-limit failures in actionable language.
- [ ] Users can locate, retain, or remove local routing state intentionally.
- [ ] Disable and uninstall guidance identifies hooks, configuration, state,
      and credentials separately.
- [ ] Automated tests verify diagnostics and secret redaction through public
      commands.

### Blocked by

- Slice 8: Notify automatically when Codex needs attention.

### User stories covered

- User stories 18, 19, 26, and 30–32.

## Slice 10: Package the integration as a Codex plugin

### Type

`AFK`

### What to build

Package the proven workspace implementation as a reusable Codex plugin. Bundle
the supported lifecycle hooks, notification adapter, setup and diagnostic
workflow, and a focused companion skill for explicit milestone notifications.
Verify installation in a clean environment without embedding user
configuration or secrets.

### Acceptance criteria

- [ ] The package has a valid Codex plugin manifest and bundles only the
      required hooks, runtime assets, documentation, and companion skill.
- [ ] Plugin installation exposes the lifecycle hooks and user-facing commands
      through the documented trust and setup flow.
- [ ] No Discord credential, user identifier, routing state, or live-test
      artifact is contained in the package.
- [ ] The companion skill describes explicit notification workflows without
      replacing deterministic lifecycle hooks.
- [ ] A clean-install test exercises configuration diagnostics and an offline
      notification contract.
- [ ] An opt-in installed-plugin smoke test delivers a live notification.
- [ ] Supported Codex surfaces and runtime prerequisites are stated based on
      evidence from the compatibility spike.
- [ ] Removal guidance returns Codex to its pre-plugin hook behavior and
      explains retained local data.

### Blocked by

- Slice 9: Add setup and operational diagnostics.

### User stories covered

- User stories 14, 28, and 30–34.

## Slice 11: Clean the test suite and verify release readiness

### Type

`AFK`

### What to build

Use the `test-cleanup` skill to remove or rewrite TDD scaffolding that pins
private implementation details while retaining the smallest durable
behavioral safety net. Then run the complete offline suite, architecture
checks, clean-install verification, and opt-in live smoke path needed to
declare the one-way integration ready for use.

### Acceptance criteria

- [ ] The `test-cleanup` skill is installed or made active before this slice is
      implemented.
- [ ] Tests that exist only to preserve temporary TDD structure are removed or
      rewritten around public behavior.
- [ ] Durable tests continue to protect formatting, mention safety, routing,
      persistence, transport contracts, retry bounds, secret redaction,
      lifecycle ingestion, diagnostics, and plugin installation.
- [ ] The complete offline suite passes without network access or Discord
      credentials.
- [ ] The repository's architecture and packaging checks pass.
- [ ] A clean installation completes the documented diagnostic workflow.
- [ ] The opt-in live smoke test creates and updates a forum post without
      exposing credentials in output.
- [ ] Remaining limitations and deferred two-way-control risks are documented.

### Blocked by

- Slice 10: Package the integration as a Codex plugin.

### User stories covered

- All implementation-quality and release-readiness stories, especially user
  stories 19, 20, and 24–32.
