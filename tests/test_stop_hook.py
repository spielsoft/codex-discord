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
from urllib.parse import parse_qs, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "lifecycle"
HOOK_COMMAND = [sys.executable, "-m", "codex_discord.stop_hook"]
WEBHOOK_ENVIRONMENT = "CODEX_DISCORD_WEBHOOK_URL"
STATE_ENVIRONMENT = "CODEX_DISCORD_STATE_FILE"
DESTINATION_ENVIRONMENT = "CODEX_DISCORD_DESTINATION_TYPE"


class StopHookDiscordHandler(BaseHTTPRequestHandler):
    requests = []
    response_status = 200
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
            self.__class__.requests.append(
                {
                    "path": self.path,
                    "body": body,
                }
            )

        if self.__class__.response_status == 200:
            response_body = {
                "id": "message-stop-hook",
                "channel_id": thread_id,
            }
        else:
            response_body = {"message": "synthetic Discord failure"}
        response = json.dumps(response_body).encode()
        self.send_response(self.__class__.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        pass


class StopHookTests(unittest.TestCase):
    def setUp(self):
        StopHookDiscordHandler.requests = []
        StopHookDiscordHandler.response_status = 200
        StopHookDiscordHandler.next_thread_number = 1
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temporary_directory.name) / "routing.json"
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            StopHookDiscordHandler,
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

    def run_hook(self, payload, *, environment=None, timeout=4):
        hook_environment = os.environ.copy()
        hook_environment[WEBHOOK_ENVIRONMENT] = self.endpoint
        hook_environment[STATE_ENVIRONMENT] = str(self.state_file)
        hook_environment[DESTINATION_ENVIRONMENT] = "forum-channel"
        if environment:
            hook_environment.update(environment)
        serialized = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(
            HOOK_COMMAND,
            cwd=REPOSITORY_ROOT,
            env=hook_environment,
            input=serialized,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )

    def test_example_hook_resolves_entrypoint_from_a_workspace_subdirectory(
        self,
    ):
        definition = json.loads(
            (REPOSITORY_ROOT / ".codex" / "hooks.example.json").read_text()
        )
        handler = definition["hooks"]["Stop"][0]["hooks"][0]
        environment = os.environ.copy()
        environment.pop(WEBHOOK_ENVIRONMENT, None)

        completed = subprocess.run(
            handler["command"],
            cwd=REPOSITORY_ROOT / "tests",
            env=environment,
            input=json.dumps(self.fixture("cli-stop.json")),
            text=True,
            capture_output=True,
            check=False,
            shell=True,
            timeout=handler["timeout"],
        )

        self.assertEqual(handler["type"], "command")
        self.assertEqual(handler["timeout"], 7)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_observed_stop_fixtures_publish_completion_without_reading_transcript(self):
        for fixture_name in ("cli-stop.json", "desktop-stop.json"):
            with self.subTest(fixture=fixture_name):
                payload = self.fixture(fixture_name)
                transcript_fifo = (
                    Path(self.temporary_directory.name)
                    / f"{fixture_name}.transcript"
                )
                os.mkfifo(transcript_fifo)
                payload["transcript_path"] = str(transcript_fifo)

                completed = self.run_hook(payload, timeout=2)

                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout, "")
                request = StopHookDiscordHandler.requests[-1]
                self.assertEqual(
                    request["body"]["thread_name"],
                    "Codex task — codex-to-discord",
                )
                self.assertIn(
                    f"Result: {payload['last_assistant_message']}",
                    request["body"]["content"],
                )
                self.assertIn(
                    "Checks: Codex reported a completed turn.",
                    request["body"]["content"],
                )
                self.assertEqual(
                    request["body"]["allowed_mentions"]["users"],
                    [],
                )

    def test_second_turn_for_the_same_session_appends_to_the_existing_thread(self):
        first_payload = self.fixture("cli-stop.json")
        second_payload = {
            **first_payload,
            "turn_id": "turn-cli-second-fixture",
            "last_assistant_message": "The second turn also completed.",
        }

        first = self.run_hook(first_payload)
        second = self.run_hook(second_payload)

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(len(StopHookDiscordHandler.requests), 2)
        initial_request, repeated_request = StopHookDiscordHandler.requests
        self.assertIn("thread_name", initial_request["body"])
        self.assertNotIn("thread_name", repeated_request["body"])
        self.assertEqual(
            parse_qs(urlsplit(repeated_request["path"]).query)["thread_id"],
            ["thread-1"],
        )
        self.assertIn(
            "Result: The second turn also completed.",
            repeated_request["body"]["content"],
        )

    def test_explicit_notification_can_seed_a_richer_forum_title(self):
        payload = self.fixture("cli-stop.json")
        seeded = subprocess.run(
            [
                sys.executable,
                "-m",
                "codex_discord",
                "publish",
                "--endpoint",
                self.endpoint,
                "--state-file",
                str(self.state_file),
                "--destination-type",
                "forum-channel",
            ],
            cwd=REPOSITORY_ROOT,
            input=json.dumps(
                {
                    "session_id": payload["session_id"],
                    "task_title": "Implement automatic Stop delivery",
                    "project": "codex-to-discord",
                    "result": "The task post now has an explicit title.",
                    "validation": "The public publish command seeded metadata.",
                }
            ),
            text=True,
            capture_output=True,
            check=False,
        )

        completed = self.run_hook(payload)

        self.assertEqual(seeded.returncode, 0, seeded.stderr)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        seeded_request, hook_request = StopHookDiscordHandler.requests
        self.assertEqual(
            seeded_request["body"]["thread_name"],
            "Implement automatic Stop delivery — codex-to-discord",
        )
        self.assertNotIn("thread_name", hook_request["body"])
        self.assertEqual(
            parse_qs(urlsplit(hook_request["path"]).query)["thread_id"],
            ["thread-1"],
        )

    def test_null_and_unusable_summaries_use_the_documented_fallback(self):
        for number, summary in enumerate((None, " \t\x00\u200b ")):
            with self.subTest(summary=repr(summary)):
                payload = {
                    **self.fixture("cli-stop.json"),
                    "session_id": f"fallback-session-{number}",
                    "last_assistant_message": summary,
                }

                completed = self.run_hook(payload)

                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn(
                    "Result: Codex turn completed",
                    StopHookDiscordHandler.requests[-1]["body"]["content"],
                )

    def test_summary_is_bounded_and_cannot_create_an_unexpected_mention(self):
        synthetic_webhook = (
            "https://discord.com/api/"
            "webhooks/123456789012345678/synthetic-hook-token"
        )
        payload = {
            **self.fixture("desktop-stop.json"),
            "last_assistant_message": (
                f"@everyone {synthetic_webhook} token=synthetic-secret "
                + "🙂" * 1000
            ),
        }

        completed = self.run_hook(payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        content = StopHookDiscordHandler.requests[0]["body"]["content"]
        self.assertNotIn("@everyone", content)
        self.assertNotIn("synthetic-hook-token", content)
        self.assertNotIn("synthetic-secret", content)
        self.assertIn("<redacted-webhook>", content)
        self.assertIn("<redacted-credential>", content)
        result = content.split("Result: ", 1)[1].split("\nChecks:", 1)[0]
        self.assertLessEqual(len(result.encode("utf-16-le")) // 2, 768)

    def test_malformed_or_non_stop_input_is_ignored_without_affecting_codex(self):
        malformed_inputs = (
            '{"session_id":',
            [],
            self.fixture("cli-permission-request.json"),
            {
                "hook_event_name": "Stop",
                "session_id": "",
                "cwd": "/synthetic/workspaces/project",
                "last_assistant_message": "Done.",
            },
        )

        for malformed_input in malformed_inputs:
            with self.subTest(payload=repr(malformed_input)):
                completed = self.run_hook(malformed_input)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout, "")
        self.assertEqual(StopHookDiscordHandler.requests, [])

    def test_missing_configuration_returns_promptly_without_affecting_codex(self):
        environment = os.environ.copy()
        environment.pop(WEBHOOK_ENVIRONMENT, None)
        environment[STATE_ENVIRONMENT] = str(self.state_file)
        started = time.monotonic()

        completed = subprocess.run(
            HOOK_COMMAND,
            cwd=REPOSITORY_ROOT,
            env=environment,
            input=json.dumps(self.fixture("cli-stop.json")),
            text=True,
            capture_output=True,
            check=False,
            timeout=2,
        )
        elapsed = time.monotonic() - started

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertLess(elapsed, 2)
        self.assertEqual(StopHookDiscordHandler.requests, [])

    def test_transport_failure_is_best_effort_and_bounded(self):
        StopHookDiscordHandler.response_status = 503
        started = time.monotonic()

        completed = self.run_hook(self.fixture("desktop-stop.json"), timeout=3)
        elapsed = time.monotonic() - started

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertLess(elapsed, 3)
        self.assertEqual(len(StopHookDiscordHandler.requests), 3)
        self.assertNotIn("/api/webhooks/", completed.stderr)


if __name__ == "__main__":
    unittest.main()
