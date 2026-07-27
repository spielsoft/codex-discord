import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEBHOOK_ENVIRONMENT = "CODEX_DISCORD_WEBHOOK_URL"
MENTION_ENVIRONMENT = "CODEX_DISCORD_MENTION_USER_ID"
STATE_ENVIRONMENT = "CODEX_DISCORD_STATE_FILE"
WEBHOOK_TOKEN = "slice-nine-secret-webhook-token"
MENTION_USER_ID = "123456789012345678"


class DiagnosticDiscordHandler(BaseHTTPRequestHandler):
    requests = []
    responses = []
    response_lock = threading.Lock()

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        with self.__class__.response_lock:
            self.__class__.requests.append(body)
            response_plan = (
                self.__class__.responses.pop(0)
                if self.__class__.responses
                else {}
            )
        delay = response_plan.get("delay", 0)
        if delay:
            time.sleep(delay)
        response_body = json.dumps(
            response_plan.get(
                "body",
                {
                    "id": "diagnostic-message",
                    "channel_id": "diagnostic-thread",
                },
            )
        ).encode()
        self.send_response(response_plan.get("status", 200))
        self.send_header("Content-Type", "application/json")
        for name, value in response_plan.get("headers", {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        try:
            self.wfile.write(response_body)
        except BrokenPipeError:
            pass

    def log_message(self, format, *args):
        pass


class SetupDiagnosticTests(unittest.TestCase):
    def setUp(self):
        DiagnosticDiscordHandler.requests = []
        DiagnosticDiscordHandler.responses = []
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temporary_directory.name) / "routing.json"
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            DiagnosticDiscordHandler,
        )
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()
        self.temporary_directory.cleanup()

    def environment(self, *, local_endpoint=False):
        environment = os.environ.copy()
        environment[WEBHOOK_ENVIRONMENT] = (
            f"http://127.0.0.1:{self.server.server_port}"
            f"/api/webhooks/123456789012345678/{WEBHOOK_TOKEN}"
            if local_endpoint
            else (
                "https://discord.com/api/webhooks/123456789012345678/"
                f"{WEBHOOK_TOKEN}"
            )
        )
        environment[MENTION_ENVIRONMENT] = MENTION_USER_ID
        environment[STATE_ENVIRONMENT] = str(self.state_file)
        return environment

    def run_doctor(self, *arguments, environment=None):
        return subprocess.run(
            [sys.executable, "-m", "codex_discord", "doctor", *arguments],
            cwd=REPOSITORY_ROOT,
            env=environment or self.environment(),
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )

    def assert_secret_free(self, completed):
        combined = completed.stdout + completed.stderr
        self.assertNotIn(WEBHOOK_TOKEN, combined)
        self.assertNotIn(MENTION_USER_ID, combined)
        self.assertNotIn("/api/webhooks/", combined)

    def test_default_health_check_is_local_only_and_reports_ready_configuration(self):
        completed = self.run_doctor()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        outcome = json.loads(completed.stdout)
        self.assertEqual(outcome["status"], "ready")
        self.assertEqual(
            outcome["checks"],
            {
                "mention_user_id": "usable",
                "state": "ready",
                "webhook": "usable",
            },
        )
        self.assertEqual(outcome["delivery"]["status"], "not-run")
        self.assertFalse(outcome["delivery"]["attempted"])
        self.assertEqual(outcome["state"]["path"], str(self.state_file.resolve()))
        self.assertFalse(outcome["state"]["exists"])
        self.assertEqual(DiagnosticDiscordHandler.requests, [])
        self.assertFalse(self.state_file.exists())
        self.assert_secret_free(completed)

    def test_missing_configuration_is_distinguished_and_actionable(self):
        environment = os.environ.copy()
        environment.pop(WEBHOOK_ENVIRONMENT, None)
        environment.pop(MENTION_ENVIRONMENT, None)
        environment[STATE_ENVIRONMENT] = str(self.state_file)

        completed = self.run_doctor(environment=environment)

        self.assertEqual(completed.returncode, 1)
        outcome = json.loads(completed.stdout)
        self.assertEqual(outcome["status"], "configuration-error")
        self.assertEqual(outcome["checks"]["webhook"], "missing")
        self.assertEqual(outcome["checks"]["mention_user_id"], "missing")
        self.assertIn(WEBHOOK_ENVIRONMENT, outcome["issues"][0]["action"])
        self.assertIn(MENTION_ENVIRONMENT, json.dumps(outcome["issues"]))
        self.assertEqual(DiagnosticDiscordHandler.requests, [])
        self.assert_secret_free(completed)

    def test_malformed_values_and_invalid_state_are_reported_without_echoing_them(self):
        environment = self.environment()
        environment[WEBHOOK_ENVIRONMENT] = (
            f"https://example.invalid/api/webhooks/123/{WEBHOOK_TOKEN}"
        )
        environment[MENTION_ENVIRONMENT] = "IanSpielman"
        self.state_file.write_text('{"routes":{"session":7}}')

        completed = self.run_doctor(environment=environment)

        self.assertEqual(completed.returncode, 1)
        outcome = json.loads(completed.stdout)
        self.assertEqual(outcome["checks"]["webhook"], "malformed")
        self.assertEqual(outcome["checks"]["mention_user_id"], "malformed")
        self.assertEqual(outcome["checks"]["state"], "invalid")
        self.assertEqual(
            {issue["code"] for issue in outcome["issues"]},
            {"mention-user-id-malformed", "state-invalid", "webhook-malformed"},
        )
        self.assertEqual(DiagnosticDiscordHandler.requests, [])
        self.assert_secret_free(completed)

    def test_existing_state_is_summarized_without_exposing_session_or_thread_ids(self):
        self.state_file.write_text(
            json.dumps(
                {
                    "routes": {
                        "private-session-one": "private-thread-one",
                        "private-session-two": "private-thread-two",
                    },
                    "delivered_events": ["private-event"],
                }
            )
        )

        completed = self.run_doctor()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        outcome = json.loads(completed.stdout)
        self.assertTrue(outcome["state"]["exists"])
        self.assertEqual(outcome["state"]["route_count"], 2)
        self.assertEqual(outcome["state"]["delivered_event_count"], 1)
        self.assertNotIn("private-session", completed.stdout)
        self.assertNotIn("private-thread", completed.stdout)
        self.assertNotIn("private-event", completed.stdout)
        self.assert_secret_free(completed)

    def test_test_delivery_requires_explicit_opt_in_and_reuses_the_publisher(self):
        completed = self.run_doctor(
            "--send-test",
            environment=self.environment(local_endpoint=True),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        outcome = json.loads(completed.stdout)
        self.assertEqual(outcome["status"], "ready")
        self.assertTrue(outcome["delivery"]["attempted"])
        self.assertEqual(outcome["delivery"]["status"], "published")
        self.assertTrue(outcome["state"]["exists"])
        self.assertEqual(outcome["state"]["route_count"], 1)
        self.assertEqual(len(DiagnosticDiscordHandler.requests), 1)
        request = DiagnosticDiscordHandler.requests[0]
        self.assertIn("Codex Discord health check", request["content"])
        self.assertEqual(request["allowed_mentions"]["users"], [])
        self.assert_secret_free(completed)

    def test_test_delivery_reports_automatic_stale_route_recovery(self):
        self.state_file.write_text(
            json.dumps(
                {
                    "routes": {
                        "codex-discord-health-check": "deleted-health-thread"
                    },
                    "delivered_events": [],
                }
            )
        )
        DiagnosticDiscordHandler.responses = [
            {"status": 404, "body": {"message": "Unknown Channel"}},
            {},
        ]

        completed = self.run_doctor(
            "--send-test",
            environment=self.environment(local_endpoint=True),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        outcome = json.loads(completed.stdout)
        self.assertEqual(outcome["delivery"]["status"], "published")
        self.assertEqual(outcome["delivery"]["code"], "route-recovered")
        self.assertIn("stale", outcome["delivery"]["action"].lower())
        self.assertEqual(len(DiagnosticDiscordHandler.requests), 2)
        self.assert_secret_free(completed)

    def test_test_delivery_classifies_common_discord_failures_actionably(self):
        cases = (
            (400, "forum-configuration", "forum"),
            (401, "authentication-failed", "webhook"),
            (403, "permission-denied", "permission"),
            (404, "webhook-not-found", "webhook"),
            (429, "rate-limited", "retry"),
        )
        for status, code, action_word in cases:
            with self.subTest(status=status):
                DiagnosticDiscordHandler.responses = [
                    {
                        "status": status,
                        "headers": {"Retry-After": "0"},
                        "body": {"message": f"failure {WEBHOOK_TOKEN}"},
                    }
                ]
                completed = self.run_doctor(
                    "--send-test",
                    "--max-attempts",
                    "1",
                    environment=self.environment(local_endpoint=True),
                )

                self.assertEqual(completed.returncode, 2)
                outcome = json.loads(completed.stdout)
                self.assertEqual(outcome["status"], "delivery-failed")
                self.assertEqual(outcome["delivery"]["code"], code)
                self.assertIn(
                    action_word,
                    outcome["delivery"]["action"].lower(),
                )
                self.assert_secret_free(completed)

    def test_timeout_diagnostic_is_bounded_and_actionable(self):
        DiagnosticDiscordHandler.responses = [{"delay": 0.5}]
        started = time.monotonic()

        completed = self.run_doctor(
            "--send-test",
            "--max-attempts",
            "1",
            "--request-timeout-seconds",
            "0.05",
            "--delivery-timeout-seconds",
            "0.2",
            environment=self.environment(local_endpoint=True),
        )
        elapsed = time.monotonic() - started

        self.assertEqual(completed.returncode, 2)
        self.assertLess(elapsed, 0.4)
        outcome = json.loads(completed.stdout)
        self.assertEqual(outcome["delivery"]["code"], "timeout")
        self.assertIn("network", outcome["delivery"]["action"].lower())
        self.assert_secret_free(completed)

    def test_help_documents_exit_semantics_and_network_opt_in(self):
        completed = self.run_doctor("--help")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        normalized_help = " ".join(completed.stdout.split())
        self.assertIn("does not contact Discord", normalized_help)
        self.assertIn("--send-test", normalized_help)
        self.assertIn("Exit 0", normalized_help)
        self.assertIn("exit 1", normalized_help)
        self.assertIn("exit 2", normalized_help)


if __name__ == "__main__":
    unittest.main()
