import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "lifecycle"
ATTENTION_COMMAND = [sys.executable, "-m", "codex_discord.attention_hook"]
WEBHOOK_ENVIRONMENT = "CODEX_DISCORD_WEBHOOK_URL"
STATE_ENVIRONMENT = "CODEX_DISCORD_STATE_FILE"
MENTION_ENVIRONMENT = "CODEX_DISCORD_MENTION_USER_ID"
MENTION_USER_ID = "123456789012345678"


class AttentionDiscordHandler(BaseHTTPRequestHandler):
    requests = []
    next_thread_number = 1
    response_status = 200
    recording_lock = threading.Lock()

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        query = parse_qs(urlsplit(self.path).query)
        with self.__class__.recording_lock:
            if "thread_name" in body:
                thread_id = f"thread-{self.__class__.next_thread_number}"
                self.__class__.next_thread_number += 1
            else:
                thread_id = query["thread_id"][0]
            self.__class__.requests.append({"path": self.path, "body": body})

        response = json.dumps(
            (
                {"id": "message-attention-hook", "channel_id": thread_id}
                if self.__class__.response_status == 200
                else {"message": "synthetic Discord failure"}
            )
        ).encode()
        self.send_response(self.__class__.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        pass


class AttentionHookTests(unittest.TestCase):
    def setUp(self):
        AttentionDiscordHandler.requests = []
        AttentionDiscordHandler.next_thread_number = 1
        AttentionDiscordHandler.response_status = 200
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temporary_directory.name) / "routing.json"
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            AttentionDiscordHandler,
        )
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()
        self.temporary_directory.cleanup()

    @property
    def endpoint(self):
        return (
            f"http://127.0.0.1:{self.server.server_port}"
            "/api/webhooks/test/token"
        )

    def fixture(self, name):
        return json.loads((FIXTURE_DIRECTORY / name).read_text())

    def environment(self):
        environment = os.environ.copy()
        environment[WEBHOOK_ENVIRONMENT] = self.endpoint
        environment[STATE_ENVIRONMENT] = str(self.state_file)
        environment[MENTION_ENVIRONMENT] = MENTION_USER_ID
        return environment

    def run_attention(self, payload, *, environment=None):
        serialized = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(
            ATTENTION_COMMAND,
            cwd=REPOSITORY_ROOT,
            env=environment or self.environment(),
            input=serialized,
            text=True,
            capture_output=True,
            check=False,
            timeout=4,
        )

    def run_publish(self, notification):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "codex_discord",
                "publish",
                "--endpoint",
                self.endpoint,
                "--state-file",
                str(self.state_file),
            ],
            cwd=REPOSITORY_ROOT,
            input=json.dumps(notification),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_permission_request_mentions_user_in_existing_session_route(self):
        payload = self.fixture("cli-permission-request.json")
        seeded = self.run_publish(
            {
                "session_id": payload["session_id"],
                "task_title": "Existing Codex task",
                "project": "codex-to-discord",
                "result": "The task started.",
                "validation": "The route was created.",
            }
        )

        completed = self.run_attention(payload)

        self.assertEqual(seeded.returncode, 0, seeded.stderr)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")
        request = AttentionDiscordHandler.requests[-1]
        self.assertNotIn("thread_name", request["body"])
        self.assertEqual(
            parse_qs(urlsplit(request["path"]).query)["thread_id"],
            ["thread-1"],
        )
        self.assertTrue(
            request["body"]["content"].startswith(
                f"<@{MENTION_USER_ID}>\n🟠 Needs input — Codex task"
            )
        )
        self.assertIn("permission for Bash", request["body"]["content"])
        self.assertNotIn("touch", request["body"]["content"])
        self.assertEqual(
            request["body"]["allowed_mentions"]["users"],
            [MENTION_USER_ID],
        )

    def test_normalized_blocked_and_failed_outcomes_keep_distinct_statuses(self):
        cases = (
            ("normalized-blocked.json", "🔴 Blocked"),
            ("normalized-failed.json", "❌ Failed"),
        )
        for fixture_name, label in cases:
            with self.subTest(fixture=fixture_name):
                payload = self.fixture(fixture_name)
                payload["session_id"] = f"{payload['session_id']}-{fixture_name}"

                completed = self.run_attention(payload)

                self.assertEqual(completed.returncode, 0, completed.stderr)
                body = AttentionDiscordHandler.requests[-1]["body"]
                self.assertIn(label, body["content"])
                self.assertIn(payload["summary"], body["content"])
                self.assertEqual(body["allowed_mentions"]["users"], [MENTION_USER_ID])

    def test_duplicate_lifecycle_delivery_is_suppressed_durably(self):
        payload = self.fixture("cli-permission-request.json")

        first = self.run_attention(payload)
        duplicate = self.run_attention(payload)

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
        self.assertEqual(first.stdout, "")
        self.assertEqual(duplicate.stdout, "")
        self.assertEqual(len(AttentionDiscordHandler.requests), 1)

        changed_turn = {**payload, "turn_id": "turn-cli-permission-second"}
        another = self.run_attention(changed_turn)
        self.assertEqual(another.returncode, 0, another.stderr)
        self.assertEqual(len(AttentionDiscordHandler.requests), 2)

        changed_request = {
            **payload,
            "tool_input": {
                **payload["tool_input"],
                "command": "touch /synthetic/different-denied-marker",
            },
        }
        distinct = self.run_attention(changed_request)
        self.assertEqual(distinct.returncode, 0, distinct.stderr)
        self.assertEqual(len(AttentionDiscordHandler.requests), 3)
        serialized_requests = json.dumps(AttentionDiscordHandler.requests)
        self.assertNotIn("different-denied-marker", serialized_requests)

    def test_routine_tool_events_malformed_input_and_missing_config_are_safe(self):
        cases = (
            {"hook_event_name": "PreToolUse", "session_id": "s", "turn_id": "t"},
            {"hook_event_name": "PostToolUse", "session_id": "s", "turn_id": "t"},
            '{"session_id":',
            [],
        )
        for payload in cases:
            with self.subTest(payload=repr(payload)):
                completed = self.run_attention(payload)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout, "")

        missing = self.environment()
        missing.pop(WEBHOOK_ENVIRONMENT)
        missing_webhook = self.run_attention(
            self.fixture("cli-permission-request.json"),
            environment=missing,
        )
        missing_mention = self.environment()
        missing_mention.pop(MENTION_ENVIRONMENT)
        missing_user = self.run_attention(
            self.fixture("normalized-blocked.json"),
            environment=missing_mention,
        )

        self.assertEqual(missing_webhook.returncode, 0)
        self.assertEqual(missing_user.returncode, 0)
        self.assertEqual(missing_webhook.stdout, "")
        self.assertEqual(missing_user.stdout, "")
        self.assertEqual(AttentionDiscordHandler.requests, [])

    def test_example_hook_registers_permission_only_and_never_controls_codex(self):
        definition = json.loads(
            (REPOSITORY_ROOT / ".codex" / "hooks.example.json").read_text()
        )

        self.assertEqual(
            set(definition["hooks"]),
            {"Stop", "PermissionRequest"},
        )
        handler = definition["hooks"]["PermissionRequest"][0]["hooks"][0]
        self.assertIn("codex_discord.attention_hook", handler["command"])
        self.assertNotIn("PreToolUse", definition["hooks"])
        self.assertNotIn("PostToolUse", definition["hooks"])

        completed = subprocess.run(
            handler["command"],
            cwd=REPOSITORY_ROOT / "tests",
            env=self.environment(),
            input=json.dumps(self.fixture("cli-permission-request.json")),
            text=True,
            capture_output=True,
            check=False,
            shell=True,
            timeout=handler["timeout"],
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_transport_failure_never_changes_the_permission_request(self):
        AttentionDiscordHandler.response_status = 503
        payload = self.fixture("cli-permission-request.json")

        completed = self.run_attention(payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(len(AttentionDiscordHandler.requests), 3)
        self.assertIn("request is unchanged", completed.stderr)
        self.assertNotIn("/api/webhooks/", completed.stderr)

        AttentionDiscordHandler.response_status = 200
        retry = self.run_attention(payload)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertEqual(len(AttentionDiscordHandler.requests), 4)

    def test_explicit_milestone_operation_requires_enablement(self):
        command = [
            sys.executable,
            "-m",
            "codex_discord",
            "milestone",
            "--endpoint",
            self.endpoint,
            "--state-file",
            str(self.state_file),
        ]
        milestone = {
            "session_id": "milestone-session",
            "task_title": "Long-running task",
            "project": "codex-to-discord",
            "result": "Reached a meaningful checkpoint.",
            "validation": "Focused checks passed.",
        }

        suppressed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            input=json.dumps(milestone),
            text=True,
            capture_output=True,
            check=False,
        )
        enabled = subprocess.run(
            [*command, "--enable"],
            cwd=REPOSITORY_ROOT,
            input=json.dumps(milestone),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(suppressed.returncode, 0, suppressed.stderr)
        self.assertEqual(json.loads(suppressed.stdout)["status"], "suppressed")
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        self.assertEqual(json.loads(enabled.stdout)["status"], "published")
        self.assertEqual(len(AttentionDiscordHandler.requests), 1)
        body = AttentionDiscordHandler.requests[0]["body"]
        self.assertIn("🔵 Milestone", body["content"])
        self.assertEqual(body["allowed_mentions"]["users"], [])


if __name__ == "__main__":
    unittest.main()
