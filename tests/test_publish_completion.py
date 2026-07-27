import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class RecordingDiscordHandler(BaseHTTPRequestHandler):
    requests = []
    next_thread_number = 1
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
            {"id": "message-123", "channel_id": thread_id}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        pass


class PublishCompletionTests(unittest.TestCase):
    def setUp(self):
        RecordingDiscordHandler.requests = []
        RecordingDiscordHandler.next_thread_number = 1
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temporary_directory.name) / "routing.json"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingDiscordHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()
        self.temporary_directory.cleanup()

    def publish_command(self, *extra_arguments):
        endpoint = f"http://127.0.0.1:{self.server.server_port}/api/webhooks/test/token"
        return [
            sys.executable,
            "-m",
            "codex_discord",
            "publish",
            "--endpoint",
            endpoint,
            "--state-file",
            str(self.state_file),
            *extra_arguments,
        ]

    def run_publish(self, notification, *extra_arguments):
        return self.run_publish_input(
            json.dumps(notification),
            *extra_arguments,
        )

    def run_publish_input(self, serialized_notification, *extra_arguments):
        return subprocess.run(
            self.publish_command(*extra_arguments),
            cwd=REPOSITORY_ROOT,
            input=serialized_notification,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_public_command_creates_a_forum_post_and_reports_routing_identity(self):
        notification = {
            "session_id": "session-abc",
            "task_title": "Add Discord completion notifications",
            "project": "Codex to Discord",
            "result": "A local completion was published successfully.",
            "validation": "Behavioral test passed against a fake service.",
            "next_action": "Add persistent routing.",
        }
        completed = self.run_publish(notification)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "session_id": "session-abc",
                "status": "published",
                "thread_id": "thread-1",
            },
        )
        self.assertEqual(len(RecordingDiscordHandler.requests), 1)

        request = RecordingDiscordHandler.requests[0]
        self.assertEqual(request["path"], "/api/webhooks/test/token?wait=true")
        self.assertEqual(
            request["body"]["thread_name"],
            "Add Discord completion notifications — Codex to Discord",
        )
        self.assertIn("🟢 Completed — Add Discord completion notifications", request["body"]["content"])
        self.assertIn("Project: Codex to Discord", request["body"]["content"])
        self.assertIn(
            "Result: A local completion was published successfully.",
            request["body"]["content"],
        )
        self.assertIn(
            "Checks: Behavioral test passed against a fake service.",
            request["body"]["content"],
        )
        self.assertIn("Next: Add persistent routing.", request["body"]["content"])
        self.assertEqual(
            request["body"]["allowed_mentions"],
            {
                "parse": [],
                "users": [],
                "roles": [],
                "replied_user": False,
            },
        )

    def test_next_action_is_optional(self):
        completed = self.run_publish(
            {
                "session_id": "session-without-next",
                "task_title": "Finish the first slice",
                "project": "Codex to Discord",
                "result": "The completion path works.",
                "validation": "Offline suite passed.",
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("Next:", RecordingDiscordHandler.requests[0]["body"]["content"])

    def test_routing_survives_commands_and_keeps_sessions_separate(self):
        first = self.run_publish(
            {
                "session_id": "session-a",
                "task_title": "First turn",
                "project": "Routing",
                "result": "Created the task post.",
                "validation": "Creation observed.",
            }
        )
        repeated = self.run_publish(
            {
                "session_id": "session-a",
                "task_title": "Second turn",
                "project": "Routing",
                "result": "Continued the task.",
                "validation": "Append observed.",
            }
        )
        separate = self.run_publish(
            {
                "session_id": "session-b",
                "task_title": "Independent task",
                "project": "Routing",
                "result": "Created another task post.",
                "validation": "Separate creation observed.",
            }
        )

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(separate.returncode, 0, separate.stderr)
        self.assertEqual(json.loads(first.stdout)["thread_id"], "thread-1")
        self.assertEqual(json.loads(repeated.stdout)["thread_id"], "thread-1")
        self.assertEqual(json.loads(separate.stdout)["thread_id"], "thread-2")

        first_request, repeated_request, separate_request = (
            RecordingDiscordHandler.requests
        )
        self.assertIn("thread_name", first_request["body"])
        self.assertNotIn("thread_name", repeated_request["body"])
        self.assertEqual(
            parse_qs(urlsplit(repeated_request["path"]).query)["thread_id"],
            ["thread-1"],
        )
        self.assertIn("thread_name", separate_request["body"])

    def test_initially_empty_state_needs_no_manual_repair(self):
        self.state_file.write_text("")

        completed = self.run_publish(
            {
                "session_id": "session-from-empty-state",
                "task_title": "Recover empty state",
                "project": "Routing",
                "result": "Published successfully.",
                "validation": "Empty state accepted.",
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("thread_name", RecordingDiscordHandler.requests[0]["body"])

    def test_concurrent_commands_do_not_lose_routes(self):
        notifications = [
            {
                "session_id": f"concurrent-{number}",
                "task_title": f"Concurrent task {number}",
                "project": "Routing",
                "result": "Published concurrently.",
                "validation": "Initial command completed.",
            }
            for number in range(2)
        ]
        processes = [
            subprocess.Popen(
                self.publish_command(),
                cwd=REPOSITORY_ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in notifications
        ]
        initial_results = [
            process.communicate(json.dumps(notification))
            for process, notification in zip(processes, notifications)
        ]

        for process, (_, stderr) in zip(processes, initial_results):
            self.assertEqual(process.returncode, 0, stderr)

        RecordingDiscordHandler.requests = []
        follow_up_results = [
            self.run_publish(
                {
                    **notification,
                    "result": "Published after both initial commands exited.",
                    "validation": "Stored route reused.",
                }
            )
            for notification in notifications
        ]

        for completed in follow_up_results:
            self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(RecordingDiscordHandler.requests), 2)
        self.assertTrue(
            all(
                "thread_name" not in recorded["body"]
                for recorded in RecordingDiscordHandler.requests
            )
        )

    def test_attention_statuses_mention_only_the_configured_user(self):
        configured_user_id = "123456789012345678"
        cases = (
            ("needs-input", "🟠 Needs input"),
            ("blocked", "🔴 Blocked"),
            ("failed", "❌ Failed"),
        )

        for status, label in cases:
            with self.subTest(status=status):
                completed = self.run_publish(
                    {
                        "session_id": f"attention-{status}",
                        "status": status,
                        "task_title": "Task needs attention",
                        "project": "Safety",
                        "result": "The user should inspect this.",
                        "validation": "Attention behavior tested.",
                    },
                    "--mention-user-id",
                    configured_user_id,
                )

                self.assertEqual(completed.returncode, 0, completed.stderr)
                request_body = RecordingDiscordHandler.requests[-1]["body"]
                self.assertTrue(
                    request_body["content"].startswith(
                        f"<@{configured_user_id}>\n{label} — "
                    ),
                    request_body["content"],
                )
                self.assertEqual(
                    request_body["allowed_mentions"],
                    {
                        "parse": [],
                        "users": [configured_user_id],
                        "roles": [],
                        "replied_user": False,
                    },
                )

    def test_completed_notification_stays_quiet_when_a_user_is_configured(self):
        configured_user_id = "123456789012345678"
        completed = self.run_publish(
            {
                "session_id": "quiet-completion",
                "status": "completed",
                "task_title": "Quiet task",
                "project": "Safety",
                "result": "Finished without needing attention.",
                "validation": "Quiet behavior tested.",
            },
            "--mention-user-id",
            configured_user_id,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        request_body = RecordingDiscordHandler.requests[0]["body"]
        self.assertNotIn(f"<@{configured_user_id}>", request_body["content"])
        self.assertEqual(
            request_body["allowed_mentions"],
            {
                "parse": [],
                "users": [],
                "roles": [],
                "replied_user": False,
            },
        )

    def test_milestones_are_suppressed_until_explicitly_enabled(self):
        notification = {
            "session_id": "milestone-session",
            "status": "milestone",
            "task_title": "Long-running task",
            "project": "Safety",
            "result": "Reached a meaningful checkpoint.",
            "validation": "Intermediate checks passed.",
        }

        suppressed = self.run_publish(notification)

        self.assertEqual(suppressed.returncode, 0, suppressed.stderr)
        self.assertEqual(
            json.loads(suppressed.stdout),
            {
                "session_id": "milestone-session",
                "status": "suppressed",
            },
        )
        self.assertEqual(RecordingDiscordHandler.requests, [])

        published = self.run_publish(notification, "--enable-milestones")

        self.assertEqual(published.returncode, 0, published.stderr)
        self.assertIn(
            "🔵 Milestone — Long-running task",
            RecordingDiscordHandler.requests[0]["body"]["content"],
        )
        self.assertEqual(
            RecordingDiscordHandler.requests[0]["body"]["allowed_mentions"]["users"],
            [],
        )

    def test_task_content_cannot_create_discord_mentions(self):
        configured_user_id = "123456789012345678"
        hostile_text = (
            "@everyone @here <@111111111111111111> <@!222222222222222222> "
            "<@&333333333333333333> <#444444444444444444>"
        )
        completed = self.run_publish(
            {
                "session_id": "mention-safety",
                "status": "blocked",
                "task_title": hostile_text,
                "project": hostile_text,
                "result": hostile_text,
                "validation": hostile_text,
                "next_action": hostile_text,
            },
            "--mention-user-id",
            configured_user_id,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        request_body = RecordingDiscordHandler.requests[0]["body"]
        content_after_deliberate_mention = request_body["content"].split("\n", 1)[1]
        for mention in (
            "@everyone",
            "@here",
            "<@111111111111111111>",
            "<@!222222222222222222>",
            "<@&333333333333333333>",
            "<#444444444444444444>",
        ):
            self.assertNotIn(mention, content_after_deliberate_mention)
            self.assertNotIn(mention, request_body["thread_name"])
        self.assertEqual(
            request_body["allowed_mentions"]["users"],
            [configured_user_id],
        )

    def test_long_unicode_content_is_readable_and_within_discord_limits(self):
        long_text = "🚀e\u0301" * 2000
        completed = self.run_publish(
            {
                "session_id": "unicode-limits",
                "task_title": long_text,
                "project": long_text,
                "result": long_text,
                "validation": long_text,
                "next_action": long_text,
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        request_body = RecordingDiscordHandler.requests[0]["body"]
        content = request_body["content"]
        thread_name = request_body["thread_name"]
        self.assertLessEqual(len(content.encode("utf-16-le")) // 2, 2000)
        self.assertLessEqual(len(thread_name.encode("utf-16-le")) // 2, 100)
        self.assertIn("Result:", content)
        self.assertIn("Checks:", content)
        self.assertIn("Next:", content)
        self.assertIn("…", content)
        self.assertTrue(thread_name.endswith("…"), thread_name)

    def test_malformed_unicode_is_replaced_without_breaking_delivery(self):
        completed = self.run_publish(
            {
                "session_id": "malformed-unicode",
                "task_title": "Broken \ud800 title",
                "project": "Safety",
                "result": "The malformed scalar is handled.",
                "validation": "Public command completed.",
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        request_body = RecordingDiscordHandler.requests[0]["body"]
        self.assertIn("Broken � title", request_body["content"])
        self.assertIn("Broken � title", request_body["thread_name"])

    def test_empty_malformed_and_unknown_status_inputs_fail_without_delivery(self):
        cases = (
            (
                {
                    "session_id": "empty-title",
                    "task_title": " \u0000\n\t ",
                    "project": "Safety",
                    "result": "No result",
                    "validation": "Not delivered",
                },
                "task_title must be a non-empty string",
            ),
            (
                {
                    "session_id": "malformed-result",
                    "task_title": "Malformed input",
                    "project": "Safety",
                    "result": ["not", "text"],
                    "validation": "Not delivered",
                },
                "result must be a non-empty string",
            ),
            (
                {
                    "session_id": "unknown-status",
                    "status": "urgent",
                    "task_title": "Unknown status",
                    "project": "Safety",
                    "result": "Not delivered",
                    "validation": "Not delivered",
                },
                "status must be one of",
            ),
        )

        for notification, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                completed = self.run_publish(notification)
                self.assertEqual(completed.returncode, 1)
                self.assertIn(expected_error, completed.stderr)
        self.assertEqual(RecordingDiscordHandler.requests, [])

    def test_attention_requires_a_valid_configured_user(self):
        notification = {
            "session_id": "invalid-user",
            "status": "needs-input",
            "task_title": "Needs input",
            "project": "Safety",
            "result": "Waiting for the user.",
            "validation": "Not delivered.",
        }

        missing = self.run_publish(notification)
        malformed = self.run_publish(
            notification,
            "--mention-user-id",
            "@everyone",
        )

        self.assertEqual(missing.returncode, 1)
        self.assertIn("mention user ID is required", missing.stderr)
        self.assertEqual(malformed.returncode, 1)
        self.assertIn("mention user ID must be a Discord user ID", malformed.stderr)
        self.assertEqual(RecordingDiscordHandler.requests, [])

    def test_malformed_json_fails_without_delivery(self):
        completed = self.run_publish_input('{"session_id": "unfinished"')

        self.assertEqual(completed.returncode, 1)
        self.assertIn("publish failed:", completed.stderr)
        self.assertEqual(RecordingDiscordHandler.requests, [])


if __name__ == "__main__":
    unittest.main()
