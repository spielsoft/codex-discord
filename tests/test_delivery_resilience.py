import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEBHOOK_TOKEN = "secret-webhook-credential"


class PlannedDiscordHandler(BaseHTTPRequestHandler):
    requests = []
    responses = []
    next_thread_number = 1
    recording_lock = threading.Lock()

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        query = parse_qs(urlsplit(self.path).query)
        with self.__class__.recording_lock:
            self.__class__.requests.append({"path": self.path, "body": body})
            response_plan = (
                self.__class__.responses.pop(0)
                if self.__class__.responses
                else {}
            )
            if "thread_name" in body:
                thread_id = f"thread-{self.__class__.next_thread_number}"
                self.__class__.next_thread_number += 1
            else:
                thread_id = query["thread_id"][0]

        delay = response_plan.get("delay", 0)
        if delay:
            time.sleep(delay)

        status = response_plan.get("status", 200)
        response_body = response_plan.get(
            "body",
            {"id": "message-123", "channel_id": thread_id},
        )
        response = json.dumps(response_body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for name, value in response_plan.get("headers", {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        try:
            self.wfile.write(response)
        except BrokenPipeError:
            pass

    def log_message(self, format, *args):
        pass


class DeliveryResilienceTests(unittest.TestCase):
    def setUp(self):
        PlannedDiscordHandler.requests = []
        PlannedDiscordHandler.responses = []
        PlannedDiscordHandler.next_thread_number = 1
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temporary_directory.name) / "routing.json"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), PlannedDiscordHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()
        self.temporary_directory.cleanup()

    def notification(self, session_id="resilience-session"):
        return {
            "session_id": session_id,
            "status": "completed",
            "task_title": "Exercise delivery resilience",
            "project": "Codex to Discord",
            "result": "The public command returned a bounded delivery outcome.",
            "validation": "A local fake HTTP service observed the request.",
        }

    def run_publish(self, notification=None, *extra_arguments):
        endpoint = (
            f"http://127.0.0.1:{self.server.server_port}"
            f"/api/webhooks/test/{WEBHOOK_TOKEN}"
        )
        command = [
            sys.executable,
            "-m",
            "codex_discord",
            "publish",
            "--endpoint",
            endpoint,
            "--state-file",
            str(self.state_file),
            "--destination-type",
            "forum-channel",
            *extra_arguments,
        ]
        return subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            input=json.dumps(notification or self.notification()),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_rate_limit_honors_retry_delay_and_then_succeeds(self):
        PlannedDiscordHandler.responses = [
            {
                "status": 429,
                "body": {"message": "rate limited", "retry_after": 0.05},
                "headers": {"Retry-After": "0.05"},
            },
            {},
        ]

        started = time.monotonic()
        completed = self.run_publish()
        elapsed = time.monotonic() - started

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertGreaterEqual(elapsed, 0.04)
        self.assertLess(elapsed, 1.5)
        self.assertEqual(len(PlannedDiscordHandler.requests), 2)
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "session_id": "resilience-session",
                "status": "published",
                "thread_id": "thread-2",
                "message_id": "message-123",
                "destination_type": "forum-channel",
                "attempts": 2,
            },
        )

    def test_transient_server_failures_retry_only_to_the_attempt_limit(self):
        PlannedDiscordHandler.responses = [
            {"status": 500, "headers": {"Retry-After": "0"}},
            {"status": 503, "headers": {"Retry-After": "0"}},
            {"status": 502, "headers": {"Retry-After": "0"}},
            {},
        ]

        completed = self.run_publish()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(PlannedDiscordHandler.requests), 3)
        outcome = json.loads(completed.stdout)
        self.assertEqual(outcome["status"], "delivery-failed")
        self.assertEqual(outcome["attempts"], 3)
        self.assertTrue(outcome["retryable"])

    def test_permanent_http_failures_are_observable_but_do_not_fail_the_task(self):
        for status in (400, 401):
            with self.subTest(status=status):
                PlannedDiscordHandler.responses = [
                    {
                        "status": status,
                        "body": {
                            "message": f"do not expose {WEBHOOK_TOKEN}",
                        },
                    }
                ]
                before = len(PlannedDiscordHandler.requests)

                completed = self.run_publish(
                    self.notification(f"permanent-{status}")
                )

                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(len(PlannedDiscordHandler.requests), before + 1)
                outcome = json.loads(completed.stdout)
                self.assertEqual(outcome["status"], "delivery-failed")
                self.assertEqual(outcome["attempts"], 1)
                self.assertFalse(outcome["retryable"])
                self.assertIn(str(status), outcome["diagnostic"])
                self.assertNotIn(WEBHOOK_TOKEN, completed.stdout)
                self.assertNotIn(WEBHOOK_TOKEN, completed.stderr)

    def test_slow_responses_stop_within_the_configured_delivery_timeout(self):
        PlannedDiscordHandler.responses = [
            {"delay": 0.5},
            {"delay": 0.5},
        ]

        started = time.monotonic()
        completed = self.run_publish(
            None,
            "--request-timeout-seconds",
            "0.08",
            "--delivery-timeout-seconds",
            "0.5",
            "--max-attempts",
            "2",
        )
        elapsed = time.monotonic() - started

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertLess(elapsed, 0.8)
        outcome = json.loads(completed.stdout)
        self.assertEqual(outcome["status"], "delivery-failed")
        self.assertEqual(outcome["attempts"], 2)
        self.assertTrue(outcome["retryable"])
        self.assertIn("timed out", outcome["diagnostic"])
        self.assertNotIn(WEBHOOK_TOKEN, completed.stdout)
        self.assertNotIn(WEBHOOK_TOKEN, completed.stderr)

    def test_stale_route_is_replaced_once_without_changing_other_routes(self):
        original = self.run_publish(self.notification("stale-session"))
        other = self.run_publish(self.notification("other-session"))
        self.assertEqual(original.returncode, 0, original.stderr)
        self.assertEqual(other.returncode, 0, other.stderr)
        PlannedDiscordHandler.requests = []
        PlannedDiscordHandler.responses = [
            {"status": 404, "body": {"message": "Unknown Channel"}},
            {},
        ]

        recovered = self.run_publish(self.notification("stale-session"))

        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(
            json.loads(recovered.stdout),
            {
                "session_id": "stale-session",
                "status": "published",
                "thread_id": "thread-3",
                "message_id": "message-123",
                "destination_type": "forum-channel",
                "attempts": 2,
                "route_recovered": True,
            },
        )
        stale_request, replacement_request = PlannedDiscordHandler.requests
        self.assertEqual(
            parse_qs(urlsplit(stale_request["path"]).query)["thread_id"],
            ["thread-1"],
        )
        self.assertNotIn("thread_name", stale_request["body"])
        self.assertNotIn(
            "thread_id",
            parse_qs(urlsplit(replacement_request["path"]).query),
        )
        self.assertIn("thread_name", replacement_request["body"])

        PlannedDiscordHandler.requests = []
        stale_follow_up = self.run_publish(self.notification("stale-session"))
        other_follow_up = self.run_publish(self.notification("other-session"))
        self.assertEqual(stale_follow_up.returncode, 0, stale_follow_up.stderr)
        self.assertEqual(other_follow_up.returncode, 0, other_follow_up.stderr)
        follow_up_targets = [
            parse_qs(urlsplit(recorded["path"]).query)["thread_id"][0]
            for recorded in PlannedDiscordHandler.requests
        ]
        self.assertEqual(follow_up_targets, ["thread-3", "thread-2"])

    def test_inaccessible_stored_route_uses_the_same_recovery_rule(self):
        initial = self.run_publish(self.notification("inaccessible-session"))
        self.assertEqual(initial.returncode, 0, initial.stderr)
        PlannedDiscordHandler.requests = []
        PlannedDiscordHandler.responses = [
            {"status": 403, "body": {"message": "Missing Access"}},
            {},
        ]

        recovered = self.run_publish(self.notification("inaccessible-session"))

        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        outcome = json.loads(recovered.stdout)
        self.assertEqual(outcome["status"], "published")
        self.assertEqual(outcome["attempts"], 2)
        self.assertTrue(outcome["route_recovered"])
        self.assertEqual(len(PlannedDiscordHandler.requests), 2)

    def test_stale_route_gets_only_one_replacement_attempt(self):
        initial = self.run_publish(self.notification("one-replacement-session"))
        self.assertEqual(initial.returncode, 0, initial.stderr)
        PlannedDiscordHandler.requests = []
        PlannedDiscordHandler.responses = [
            {"status": 404, "body": {"message": "Unknown Channel"}},
            {"status": 503, "headers": {"Retry-After": "0"}},
            {},
        ]

        failed_replacement = self.run_publish(
            self.notification("one-replacement-session")
        )

        self.assertEqual(
            failed_replacement.returncode,
            0,
            failed_replacement.stderr,
        )
        outcome = json.loads(failed_replacement.stdout)
        self.assertEqual(outcome["status"], "delivery-failed")
        self.assertEqual(outcome["attempts"], 2)
        self.assertTrue(outcome["retryable"])
        self.assertIn("replacement", outcome["diagnostic"])
        self.assertEqual(len(PlannedDiscordHandler.requests), 2)

        PlannedDiscordHandler.requests = []
        later_attempt = self.run_publish(
            self.notification("one-replacement-session")
        )
        self.assertEqual(later_attempt.returncode, 0, later_attempt.stderr)
        self.assertIn(
            "thread_name",
            PlannedDiscordHandler.requests[0]["body"],
        )
        self.assertNotIn(
            "thread_id",
            parse_qs(
                urlsplit(PlannedDiscordHandler.requests[0]["path"]).query
            ),
        )


if __name__ == "__main__":
    unittest.main()
