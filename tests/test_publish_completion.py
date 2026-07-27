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

    def publish_command(self):
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
        ]

    def run_publish(self, notification):
        return subprocess.run(
            self.publish_command(),
            cwd=REPOSITORY_ROOT,
            input=json.dumps(notification),
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
        self.assertEqual(request["body"]["allowed_mentions"], {"parse": []})

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


if __name__ == "__main__":
    unittest.main()
