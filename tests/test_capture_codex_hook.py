import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "lifecycle"
CAPTURE_COMMAND = [
    sys.executable,
    str(REPOSITORY_ROOT / "scripts" / "capture_codex_hook.py"),
]


class CaptureCodexHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.capture_file = Path(self.temporary_directory.name) / "captures.jsonl"
        self.context_file = Path(self.temporary_directory.name) / "context.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def run_capture(self, payload):
        return subprocess.run(
            [
                *CAPTURE_COMMAND,
                "--output",
                str(self.capture_file),
                "--context",
                str(self.context_file),
            ],
            cwd=REPOSITORY_ROOT,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )

    def arm(self, surface):
        return subprocess.run(
            [
                *CAPTURE_COMMAND,
                "--context",
                str(self.context_file),
                "--arm",
                surface,
            ],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def read_capture(self):
        return json.loads(self.capture_file.read_text().strip())

    def read_captures(self):
        return [
            json.loads(line)
            for line in self.capture_file.read_text().splitlines()
            if line
        ]

    def test_stop_capture_keeps_safe_lifecycle_fields_without_raw_paths(self):
        armed = self.arm("cli")
        self.assertEqual(armed.returncode, 0, armed.stderr)

        completed = self.run_capture(
            {
                "session_id": "019fa-secret-session-id",
                "turn_id": "019fa-secret-turn-id",
                "transcript_path": "/Users/example/.codex/transcripts/private.jsonl",
                "cwd": "/Users/example/Code/Discord",
                "hook_event_name": "Stop",
                "model": "gpt-test",
                "permission_mode": "default",
                "last_assistant_message": "Lifecycle spike complete.",
                "stop_hook_active": False,
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")
        capture = self.read_capture()
        self.assertEqual(capture["surface"], "cli")
        self.assertEqual(capture["hook_event_name"], "Stop")
        self.assertEqual(capture["cwd_name"], "Discord")
        self.assertEqual(capture["last_assistant_message"], "Lifecycle spike complete.")
        self.assertEqual(capture["transcript_path_present"], True)
        self.assertEqual(capture["stop_hook_active"], False)
        self.assertRegex(capture["session_id"], r"^session-[0-9a-f]{12}$")
        self.assertRegex(capture["turn_id"], r"^turn-[0-9a-f]{12}$")
        serialized = json.dumps(capture)
        self.assertNotIn("019fa-secret", serialized)
        self.assertNotIn("/Users/example", serialized)

    def test_permission_capture_records_shape_without_command_values(self):
        self.arm("desktop")
        completed = self.run_capture(
            {
                "session_id": "desktop-session",
                "turn_id": "desktop-turn",
                "transcript_path": None,
                "cwd": "/Users/example/Code/Discord",
                "hook_event_name": "PermissionRequest",
                "model": "gpt-test",
                "permission_mode": "default",
                "tool_name": "Bash",
                "tool_input": {
                    "cmd": "touch /private/tmp/must-not-run",
                    "sandbox_permissions": "require_escalated",
                    "nested": {"secret": "do not retain"},
                },
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")
        capture = self.read_capture()
        self.assertEqual(capture["surface"], "desktop")
        self.assertEqual(capture["hook_event_name"], "PermissionRequest")
        self.assertEqual(capture["tool_name"], "Bash")
        self.assertEqual(
            capture["tool_input_shape"],
            {
                "cmd": "string",
                "nested": {"secret": "string"},
                "sandbox_permissions": "string",
            },
        )
        serialized = json.dumps(capture)
        self.assertNotIn("must-not-run", serialized)
        self.assertNotIn("do not retain", serialized)

    def test_rejects_unsupported_events_without_writing_a_capture(self):
        completed = self.run_capture(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "session",
                "turn_id": "turn",
            }
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(self.capture_file.exists())

    def test_malformed_input_fails_closed_without_echoing_input(self):
        completed = subprocess.run(
            [
                *CAPTURE_COMMAND,
                "--output",
                str(self.capture_file),
                "--context",
                str(self.context_file),
            ],
            cwd=REPOSITORY_ROOT,
            input='{"secret": "webhook-token"',
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("webhook-token", completed.stderr)
        self.assertFalse(self.capture_file.exists())

    def test_observed_surface_fixtures_pass_through_the_public_recorder(self):
        fixture_expectations = {
            "cli-stop.json": {
                "surface": "cli",
                "fields": {
                    "cwd",
                    "hook_event_name",
                    "last_assistant_message",
                    "model",
                    "permission_mode",
                    "session_id",
                    "stop_hook_active",
                    "transcript_path",
                    "turn_id",
                },
                "message": "Lifecycle spike CLI complete.",
            },
            "cli-permission-request.json": {
                "surface": "cli",
                "fields": {
                    "cwd",
                    "hook_event_name",
                    "model",
                    "permission_mode",
                    "session_id",
                    "tool_input",
                    "tool_name",
                    "transcript_path",
                    "turn_id",
                },
                "tool_input_shape": {
                    "command": "string",
                    "description": "string",
                },
            },
            "desktop-stop.json": {
                "surface": "desktop",
                "fields": {
                    "cwd",
                    "hook_event_name",
                    "last_assistant_message",
                    "model",
                    "permission_mode",
                    "session_id",
                    "stop_hook_active",
                    "transcript_path",
                    "turn_id",
                },
                "message": "Lifecycle spike desktop complete.",
            },
        }

        for fixture_name, expectation in fixture_expectations.items():
            with self.subTest(fixture=fixture_name):
                payload = json.loads(
                    (FIXTURE_DIRECTORY / fixture_name).read_text()
                )
                self.arm(expectation["surface"])
                completed = self.run_capture(payload)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                record = self.read_captures()[-1]
                self.assertEqual(record["surface"], expectation["surface"])
                self.assertEqual(
                    set(record["available_fields"]),
                    expectation["fields"],
                )
                if "message" in expectation:
                    self.assertEqual(
                        record["last_assistant_message"],
                        expectation["message"],
                    )
                if "tool_input_shape" in expectation:
                    self.assertEqual(
                        record["tool_input_shape"],
                        expectation["tool_input_shape"],
                    )


if __name__ == "__main__":
    unittest.main()
