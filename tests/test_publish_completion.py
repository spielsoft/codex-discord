import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class RecordingDiscordHandler(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        self.__class__.requests.append({"path": self.path, "body": body})

        response = json.dumps({"id": "message-123", "channel_id": "thread-456"}).encode()
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
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingDiscordHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()

    def run_publish(self, notification):
        endpoint = f"http://127.0.0.1:{self.server.server_port}/api/webhooks/test/token"
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "codex_discord",
                "publish",
                "--endpoint",
                endpoint,
            ],
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
                "thread_id": "thread-456",
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


if __name__ == "__main__":
    unittest.main()
