# Codex lifecycle compatibility spike

Status: compatibility observation complete on July 27, 2026.

This spike recorded only the lifecycle fields needed to choose the integration
boundary. It did not publish to Discord, read a transcript, approve a tool, or
write hook output to stdout. Raw session and turn IDs became deterministic
pseudonyms, the working directory became its basename, transcript paths became
a presence flag, and permission inputs became a keys-and-types shape with no
values. Captures are private (`0600`) and ignored by Git.

The temporary trusted hook configuration and surface marker were removed after
observation, so the recorder is no longer active.
The development-only recorder and its tests were removed during the release
cleanup. The schema-equivalent fixtures remain because they exercise the
shipped hook interfaces.

## Evidence and decision

### Official Codex documentation

The official Hooks documentation says:

- Command hooks receive one JSON object on standard input.
- Common input fields are `session_id`, `transcript_path`, `cwd`,
  `hook_event_name`, and the Codex extension `model`.
- Turn-scoped hooks include the Codex extension `turn_id`.
- `Stop` and `PermissionRequest` include `permission_mode`.
- `PermissionRequest` matchers filter by tool name; `Stop` does not support a
  matcher.
- Non-managed command hooks require review and trust. Project hooks load only
  for trusted projects.
- Hook commands run with the session working directory.
- `transcript_path` is convenient but its format is not a stable hook
  interface and may change.
- A successful hook can exit zero with no output. The spike recorder used
  exactly that behavior, so it could not approve, deny, block, or continue
  work.

Source: the freshly fetched Codex manual, Hooks section, July 27, 2026.

### Installed runtime inspection

The installed binary reports `codex-cli 0.146.0-alpha.3.1`, with the stable
`hooks` feature enabled. Its embedded command-input schemas require:

| Field | `Stop` | `PermissionRequest` |
| --- | --- | --- |
| `session_id` | yes | yes |
| `turn_id` | yes | yes |
| `cwd` | yes | yes |
| `hook_event_name` | yes | yes |
| `model` | yes | yes |
| `permission_mode` | yes | yes |
| `transcript_path` | yes, nullable | yes, nullable |
| `last_assistant_message` | yes, nullable | no |
| `stop_hook_active` | yes | no |
| `tool_name` | no | yes |
| `tool_input` | no | yes |

Neither documented common fields nor the installed schemas contain a task
title. Static schema inspection informed the spike but did not substitute for
the surface observations below.

### Observed surface behavior

The controlled capture produced four rows. Rows 1, 2, and 4 are evidence for
this decision:

- CLI emitted `Stop` with the exact expected final message.
- The same CLI session emitted `PermissionRequest` before the human denied the
  command. Its `tool_name` was `Bash`; its `tool_input` shape contained
  `command` and `description` strings.
- A new desktop task emitted `Stop` with the exact expected final message and
  the same field set as CLI `Stop`.

Row 3 is excluded. The desktop-marker prompt was mistakenly entered into the
CLI task, so its manually armed `surface` label does not identify the emitting
surface. Row 4 came from the genuine new desktop task, has a distinct session
group, and is the desktop evidence retained in the synthetic fixture.

| Available information | CLI `Stop` | Desktop `Stop` | CLI `PermissionRequest` |
| --- | --- | --- | --- |
| Session identity | `session_id` | `session_id` | `session_id` |
| Turn identity | `turn_id` | `turn_id` | `turn_id` |
| Working directory | `cwd` | `cwd` | `cwd` |
| Stable task title | absent | absent | absent |
| Completion summary | `last_assistant_message` | `last_assistant_message` | absent |
| Permission detail | absent | absent | `tool_name`, `tool_input` |
| Permission mode | `permission_mode` | `permission_mode` | `permission_mode` |
| Transcript location | present | present | present |

The CLI Stop and PermissionRequest shared a session identity and had different
turn identities. The desktop Stop used a different session identity, as
expected for a new task. Both Stop events reported `stop_hook_active: false`.
All three usable observations included a transcript path, but the recorder did
not open it. No desktop PermissionRequest was observed, so permission-hook
support is proven only for CLI in this installed version.

The fixtures in `tests/fixtures/lifecycle/` are fully synthetic,
schema-equivalent inputs rather than copies of local identifiers or paths:

- `cli-stop.json`
- `cli-permission-request.json`
- `desktop-stop.json`

### Selected summary and title strategy

The prototype will:

1. Use bounded, mention-safe `last_assistant_message` from `Stop` as the
   automatic completion result on both observed surfaces.
2. Use the stable session ID for routing, the working-directory basename as
   project, and a generic task label when no explicit title has been supplied.
3. Let an explicit structured notification command seed a better title and
   summary for sessions that need richer Discord output.
4. Fall back to “Codex turn completed” when `last_assistant_message` is null or
   unusable.

Transcript parsing is rejected as a core contract. A future diagnostic may
offer it only as an explicitly labeled, best-effort fallback; automatic
delivery must continue to work without opening `transcript_path`.

## Limitations

- These observations describe `codex-cli 0.146.0-alpha.3.1` and the paired
  desktop build, not an immutable cross-version wire contract.
- `last_assistant_message` is nullable in the installed schema, so the generic
  completion fallback remains required.
- Hooks expose no stable task title. Rich titles require the explicit
  structured command or a later, separately validated interface.
- PermissionRequest was observed only in CLI. Desktop attention delivery must
  retain an explicit-command fallback until that surface is separately proven.
- The permission hook identifies the tool and input but does not expose the
  later human approval or denial as part of the captured request.
- The raw ignored capture retains the excluded row for auditability; automated
  tests use only synthetic equivalents of rows 1, 2, and 4.
