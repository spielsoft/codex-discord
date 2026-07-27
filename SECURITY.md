# Security policy

## Reporting a vulnerability

Do not disclose webhook credentials, private Discord content, Codex lifecycle
payloads, or exploitable details in a public issue.

After this repository is hosted on GitHub, use a private GitHub Security
Advisory to report vulnerabilities. Until a private reporting destination is
published, rotate any affected webhook immediately and avoid sharing the
credential or payload.

Include:

- the affected plugin version;
- the Codex surface and version;
- a minimal synthetic reproduction;
- the security impact;
- whether a webhook or local routing file may have been exposed.

## Credential response

A Discord webhook URL is a credential. If it appears in a prompt, transcript,
log, screenshot, issue, commit, or other shared location:

1. delete or rotate the webhook in Discord;
2. replace the locally stored value;
3. inspect Git history and artifacts for additional exposure;
4. do not rely on deleting the visible message as revocation.

The numeric Discord user ID is not an authentication secret, but this project
does not include real user-specific identifiers in source or fixtures.

## Security boundaries

The released plugin is one-way. It sends bounded notifications to Discord and
does not read Discord messages, approve tools, or control Codex. Any future
two-way design requires separate authentication, authorization, replay
prevention, auditing, and prompt-injection defenses.

Local configuration is stored under the plugin's private `PLUGIN_DATA`
directory with owner-only permissions. Environment variables can override it
for managed deployments. Delivery remains best effort and is not an
exactly-once protocol.
