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
MCP_SERVER = (
    REPOSITORY_ROOT
    / "plugins"
    / "codex-discord"
    / "mcp"
    / "server.py"
)


class McpDiscordHandler(BaseHTTPRequestHandler):
    requests = []
    response_status = 200

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.__class__.requests.append(
            {
                "path": self.path,
                "body": json.loads(self.rfile.read(length)),
            }
        )
        response = json.dumps(
            {"id": "mcp-message", "channel_id": "mcp-channel"}
        ).encode()
        self.send_response(self.__class__.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        pass


class McpServerTests(unittest.TestCase):
    def setUp(self):
        McpDiscordHandler.requests = []
        McpDiscordHandler.response_status = 200
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.plugin_data = Path(self.temporary_directory.name) / "plugin-data"
        self.plugin_data.mkdir()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), McpDiscordHandler)
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
            "/api/webhooks/123456789012345678/offline-test-token"
        )

    def environment(self):
        environment = os.environ.copy()
        environment["PLUGIN_DATA"] = str(self.plugin_data)
        environment.pop("CODEX_DISCORD_WEBHOOK_URL", None)
        environment.pop("CODEX_DISCORD_DESTINATION_TYPE", None)
        environment.pop("CODEX_DISCORD_STATE_FILE", None)
        return environment

    def run_server(self, *messages):
        completed = subprocess.run(
            [sys.executable, str(MCP_SERVER)],
            cwd=MCP_SERVER.parent.parent,
            env=self.environment(),
            input="\n".join(json.dumps(message) for message in messages) + "\n",
            text=True,
            capture_output=True,
            check=False,
            timeout=8,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return [
            json.loads(line)
            for line in completed.stdout.splitlines()
            if line.strip()
        ]

    def test_lists_a_slack_style_direct_send_tool(self):
        responses = self.run_server(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )

        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "Codex Discord")
        tool = responses[1]["result"]["tools"][0]
        self.assertEqual(tool["name"], "discord_send_message")
        self.assertEqual(tool["inputSchema"]["required"], ["message"])
        self.assertFalse(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["destructiveHint"])

    def test_text_channel_call_sends_one_ordinary_message_and_deduplicates(self):
        (self.plugin_data / "config.json").write_text(
            json.dumps(
                {
                    "CODEX_DISCORD_WEBHOOK_URL": self.endpoint,
                    "CODEX_DISCORD_DESTINATION_TYPE": "text-channel",
                }
            )
        )
        call = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "discord_send_message",
                "arguments": {
                    "message": "Daily calendar brief",
                    "route_key": "personal-assistant:daily-brief",
                    "idempotency_key": "daily-brief:2026-07-29",
                    "thread_name": "Ignored in a text channel",
                },
            },
        }

        responses = self.run_server(
            {**call, "id": 1},
            {**call, "id": 2},
        )

        first = responses[0]["result"]["structuredContent"]
        duplicate = responses[1]["result"]["structuredContent"]
        self.assertEqual(
            first,
            {
                "route_key": "personal-assistant:daily-brief",
                "status": "sent",
                "message_id": "mcp-message",
                "channel_id": "mcp-channel",
                "destination_type": "text-channel",
            },
        )
        self.assertEqual(duplicate["status"], "duplicate")
        self.assertEqual(len(McpDiscordHandler.requests), 1)
        sent = McpDiscordHandler.requests[0]
        self.assertNotIn("thread_name", sent["body"])
        self.assertNotIn("thread_id", parse_qs(urlsplit(sent["path"]).query))

    def test_missing_connection_has_clear_non_retryable_failure(self):
        response = self.run_server(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "discord_send_message",
                    "arguments": {"message": "Not delivered"},
                },
            }
        )[0]["result"]

        self.assertTrue(response["isError"])
        self.assertEqual(
            response["structuredContent"],
            {
                "status": "configuration-error",
                "retryable": False,
                "diagnostic": "Discord is not connected.",
            },
        )
        self.assertEqual(McpDiscordHandler.requests, [])

    def test_delivery_failure_is_structured_for_automation(self):
        (self.plugin_data / "config.json").write_text(
            json.dumps(
                {
                    "CODEX_DISCORD_WEBHOOK_URL": self.endpoint,
                    "CODEX_DISCORD_DESTINATION_TYPE": "text-channel",
                }
            )
        )
        McpDiscordHandler.response_status = 503

        response = self.run_server(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "discord_send_message",
                    "arguments": {"message": "Retryable alert"},
                },
            }
        )[0]["result"]

        self.assertTrue(response["isError"])
        outcome = response["structuredContent"]
        self.assertEqual(outcome["status"], "delivery-failed")
        self.assertTrue(outcome["retryable"])
        self.assertEqual(outcome["attempts"], 3)
        self.assertEqual(outcome["destination_type"], "text-channel")
        self.assertEqual(len(McpDiscordHandler.requests), 3)


if __name__ == "__main__":
    unittest.main()
