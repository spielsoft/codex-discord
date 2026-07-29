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


class MessageDiscordHandler(BaseHTTPRequestHandler):
    requests = []
    response_statuses = []
    lock = threading.Lock()

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        with self.__class__.lock:
            self.__class__.requests.append({"path": self.path, "body": body})
            response_status = (
                self.__class__.response_statuses.pop(0)
                if self.__class__.response_statuses
                else 200
            )

        response = json.dumps(
            {"id": "message-123", "channel_id": "thread-123"}
        ).encode()
        self.send_response(response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Retry-After", "0")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        pass


class SendMessageTests(unittest.TestCase):
    def setUp(self):
        MessageDiscordHandler.requests = []
        MessageDiscordHandler.response_statuses = []
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temporary_directory.name) / "routing.json"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), MessageDiscordHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()
        self.temporary_directory.cleanup()

    def run_send(self, payload):
        endpoint = (
            f"http://127.0.0.1:{self.server.server_port}"
            "/api/webhooks/test/token"
        )
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "codex_discord",
                "send",
                "--endpoint",
                endpoint,
                "--state-file",
                str(self.state_file),
            ],
            cwd=REPOSITORY_ROOT,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            timeout=8,
        )

    def test_send_preserves_formatting_and_returns_discord_identities(self):
        completed = self.run_send(
            {
                "message": "# Morning brief\n\n- First event\n- @everyone stays quiet",
                "thread_name": "Daily Brief",
                "route_key": "personal-assistant:daily-brief",
                "idempotency_key": "daily-brief:2026-07-29",
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "route_key": "personal-assistant:daily-brief",
                "status": "sent",
                "thread_id": "thread-123",
                "message_id": "message-123",
            },
        )
        self.assertEqual(len(MessageDiscordHandler.requests), 1)
        request = MessageDiscordHandler.requests[0]
        self.assertEqual(request["body"]["thread_name"], "Daily Brief")
        self.assertIn("# Morning brief\n\n- First event", request["body"]["content"])
        self.assertIn("@\u200beveryone", request["body"]["content"])
        self.assertEqual(
            request["body"]["allowed_mentions"],
            {
                "parse": [],
                "users": [],
                "roles": [],
                "replied_user": False,
            },
        )

    def test_route_reuse_and_idempotency_suppress_duplicate_posts(self):
        payload = {
            "message": "Calendar brief",
            "thread_name": "Daily Brief",
            "route_key": "personal-assistant:daily-brief",
            "idempotency_key": "daily-brief:2026-07-29",
        }
        first = self.run_send(payload)
        duplicate = self.run_send(payload)
        follow_up = self.run_send(
            {
                **payload,
                "message": "Next calendar brief",
                "idempotency_key": "daily-brief:2026-07-30",
            }
        )

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
        self.assertEqual(follow_up.returncode, 0, follow_up.stderr)
        self.assertEqual(json.loads(duplicate.stdout)["status"], "duplicate")
        self.assertEqual(len(MessageDiscordHandler.requests), 2)
        follow_up_request = MessageDiscordHandler.requests[1]
        self.assertNotIn("thread_name", follow_up_request["body"])
        self.assertEqual(
            parse_qs(urlsplit(follow_up_request["path"]).query)["thread_id"],
            ["thread-123"],
        )

    def test_delivery_failure_is_structured_and_exits_two(self):
        MessageDiscordHandler.response_statuses = [503, 503, 503]

        completed = self.run_send({"message": "Calendar brief"})

        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "delivery-failed")
        self.assertEqual(result["attempts"], 3)
        self.assertTrue(result["retryable"])
        self.assertNotIn("token", completed.stdout)

    def test_invalid_message_exits_one_without_delivery(self):
        completed = self.run_send({"message": "x" * 2001})

        self.assertEqual(completed.returncode, 1)
        self.assertIn("2000-character limit", completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(MessageDiscordHandler.requests, [])


if __name__ == "__main__":
    unittest.main()
