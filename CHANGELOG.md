# Changelog

All notable changes to Codex Discord are documented here.

## 0.3.0

- Added a Slack-analogous `discord-outgoing-message` skill for explicit,
  free-form Discord sends.
- Added the `codex-discord send` command with configured-destination routing,
  optional idempotency, Discord message IDs, and automation-safe exit codes.
- Removed the superseded `discord-milestone` skill, `milestone` command,
  milestone status flags, and original completion compatibility alias.
- Replaced the setup-only skill with a Slack-inspired `discord` router and a
  private browser-based connection flow launched by Codex.
- Removed the superseded terminal `connect` interface and cache-path
  onboarding instructions.
- Added localhost-only guided setup, password-style webhook entry,
  verify-before-save behavior, cancellation, retryable validation errors, and
  credential-free success confirmation.
- Made the attention user ID optional so send-only workflows can connect with
  only their forum webhook.
- Reused the lifecycle publisher's forum routing, retry bounds, stale-route
  recovery, mention safety, and atomic duplicate-suppression state.
- Documented the outgoing-message MVP decision, contract, exclusions, and
  PersonalAssistant automation guidance.

## 0.2.1

- Added the canonical repo-marketplace layout for GitHub and team distribution.
- Added install-first public documentation, GitHub CI, contribution guidance,
  and a security policy.
- Moved completed planning documents under `docs/`.
- Finalized the SpielSoft GitHub metadata and MIT license for public release.

## 0.2.0

- Added Slack-inspired guided setup with masked webhook entry.
- Added private per-user configuration under `PLUGIN_DATA`.
- Added install-surface starter prompts and a setup skill.

## 0.1.0

- Added one-way `Stop` and `PermissionRequest` lifecycle notifications.
- Added session-to-forum-thread routing, safe mentions, retry bounds,
  diagnostics, and the explicit milestone skill.
