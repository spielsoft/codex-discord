---
name: discord-setup
description: Guide a user through connecting, checking, reconfiguring, or testing the Codex Discord plugin. Use when the user asks to set up Discord notifications, connect a webhook, choose a forum destination, diagnose first-run configuration, understand forum-post naming, or send the initial test notification.
---

# Set up Codex Discord

Explain that the user configures a webhook for a Discord **forum channel**, not
a pre-existing forum post. The plugin creates `Codex task — <project>` for the
first event in each Codex session, stores the returned Discord thread ID, and
appends later events from that session to the same post.

## Connect

1. Ask the user to create or select a private Discord server and forum channel.
2. In that forum channel, open **Edit Channel → Integrations → Webhooks**,
   create a webhook, select the forum channel, and copy its URL.
3. Ask the user to enable Discord Developer Mode and use **Copy User ID** on
   the account that should receive attention mentions. Usernames do not work.
4. Resolve this `SKILL.md` path. Its great-grandparent directory is the plugin
   root.
5. Tell the user to run this command in their own local terminal:

   ```sh
   /usr/bin/python3 <plugin-root>/scripts/codex-discord setup
   ```

   The command hides webhook input and writes `PLUGIN_DATA/config.json` with
   owner-only permissions. Do not ask the user to paste the webhook into the
   chat, a Codex prompt, a command argument, or a repository file.
6. Tell the user to run the same command with `doctor`, then with
   `doctor --send-test`. The latter deliberately creates a Discord post.
7. Ask the user to start a new Codex task, review and trust the plugin's `Stop`
   and `PermissionRequest` hooks, and complete a test turn.

Never read, repeat, log, or transmit the stored webhook. Report only
credential-free `setup` or `doctor` results.

## Managed deployment

Administrators may supply `CODEX_DISCORD_WEBHOOK_URL` and
`CODEX_DISCORD_MENTION_USER_ID` to the Codex process instead. Environment
values override the private config file. `CODEX_DISCORD_STATE_FILE` optionally
overrides the routing-state location.

Each user configures local plugin data independently. A team may use one shared
forum webhook while assigning each user their own numeric mention ID.

## Reconfigure or remove

Run `setup` again to replace the private configuration atomically. On removal,
revoke the Discord webhook and delete `PLUGIN_DATA/config.json`; retain or
remove routing state separately depending on whether thread continuity matters.
