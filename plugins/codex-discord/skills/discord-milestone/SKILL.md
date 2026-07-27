---
name: discord-milestone
description: Send an explicit, non-mentioning Discord milestone for a Codex task when the user asks for a meaningful progress update.
---

# Discord milestone

Use this skill only when the user explicitly asks to send a milestone or
progress notification. Automatic completion and permission notifications
belong to the deterministic plugin hooks; do not reproduce them here.

Before delivery:

1. Confirm a stable Codex session ID is available from the calling workflow.
   Never invent one. If it is unavailable, explain that the milestone cannot
   be routed safely.
2. Summarize only the meaningful checkpoint, validation evidence, and optional
   next action. Do not include a transcript, reasoning, credentials, full
   command output, or unrestricted diffs.
3. Resolve this `SKILL.md` path and treat its great-grandparent directory as
   the plugin root (`SKILL.md` → `discord-milestone` → `skills` → plugin
   root).
4. Pipe one JSON object to:

   ```sh
   /usr/bin/python3 "<plugin-root>/scripts/codex-discord" milestone
   ```

The object must contain `session_id`, `task_title`, `project`, `result`, and
`validation`; `next_action` is optional. The command deliberately enables one
milestone and uses the plugin's configured webhook and writable data
directory. Milestones never mention the attention user.

Report the command's credential-free JSON outcome. A delivery failure is
best-effort and must not change the underlying Codex task result.
