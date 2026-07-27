import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCE = REPOSITORY_ROOT / "plugins" / "codex-discord"
MENTION_USER_ID = "123456789012345678"
WEBHOOK_TOKEN = "offline-plugin-contract-token"


class PluginDiscordHandler(BaseHTTPRequestHandler):
    requests = []
    lock = threading.Lock()

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        with self.__class__.lock:
            self.__class__.requests.append(
                {
                    "path": self.path,
                    "body": body,
                }
            )
        response = json.dumps(
            {"id": "plugin-message", "channel_id": "plugin-thread"}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        pass


class PluginPackageTests(unittest.TestCase):
    def setUp(self):
        PluginDiscordHandler.requests = []
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.install_root = Path(self.temporary_directory.name) / "codex-discord"
        shutil.copytree(PLUGIN_SOURCE, self.install_root)
        self.plugin_data = Path(self.temporary_directory.name) / "plugin-data"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), PluginDiscordHandler)
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
            f"/api/webhooks/123456789012345678/{WEBHOOK_TOKEN}"
        )

    def environment(self):
        environment = os.environ.copy()
        environment.update(
            {
                "PLUGIN_ROOT": str(self.install_root),
                "PLUGIN_DATA": str(self.plugin_data),
                "CODEX_DISCORD_WEBHOOK_URL": self.endpoint,
                "CODEX_DISCORD_MENTION_USER_ID": MENTION_USER_ID,
            }
        )
        environment.pop("CODEX_DISCORD_STATE_FILE", None)
        return environment

    def run_plugin(self, *arguments, input=None):
        return subprocess.run(
            [
                sys.executable,
                str(self.install_root / "scripts" / "codex-discord"),
                *arguments,
            ],
            cwd=self.temporary_directory.name,
            env=self.environment(),
            input=input,
            text=True,
            capture_output=True,
            check=False,
            timeout=8,
        )

    def test_manifest_and_default_hook_discovery_are_installable(self):
        manifest = json.loads(
            (self.install_root / ".codex-plugin" / "plugin.json").read_text()
        )
        hooks = json.loads(
            (self.install_root / "hooks" / "hooks.json").read_text()
        )

        self.assertEqual(manifest["name"], "codex-discord")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("hooks", manifest)
        self.assertEqual(set(hooks["hooks"]), {"Stop", "PermissionRequest"})
        for event in hooks["hooks"].values():
            handler = event[0]["hooks"][0]
            self.assertIn("$PLUGIN_ROOT", handler["command"])
            self.assertIn("$PLUGIN_DATA", handler["command"])

    def test_clean_install_doctor_is_local_only_and_uses_plugin_data(self):
        completed = self.run_plugin("doctor")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(
            result["state"]["path"],
            str((self.plugin_data / "routing.json").resolve()),
        )
        self.assertFalse(result["delivery"]["attempted"])
        self.assertEqual(PluginDiscordHandler.requests, [])
        combined = completed.stdout + completed.stderr
        self.assertNotIn(WEBHOOK_TOKEN, combined)
        self.assertNotIn(MENTION_USER_ID, combined)

    def test_installed_stop_hook_delivers_through_bundled_runtime(self):
        definition = json.loads(
            (self.install_root / "hooks" / "hooks.json").read_text()
        )
        handler = definition["hooks"]["Stop"][0]["hooks"][0]
        payload = {
            "hook_event_name": "Stop",
            "session_id": "clean-install-session",
            "turn_id": "clean-install-turn",
            "cwd": "/synthetic/project",
            "last_assistant_message": "The clean-install contract passed.",
        }

        completed = subprocess.run(
            handler["command"],
            cwd=self.temporary_directory.name,
            env=self.environment(),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            shell=True,
            timeout=handler["timeout"],
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(len(PluginDiscordHandler.requests), 1)
        request = PluginDiscordHandler.requests[0]["body"]
        self.assertIn("The clean-install contract passed.", request["content"])
        self.assertEqual(request["allowed_mentions"]["users"], [])
        self.assertTrue((self.plugin_data / "routing.json").exists())

    def test_installed_attention_hook_mentions_only_the_configured_user(self):
        definition = json.loads(
            (self.install_root / "hooks" / "hooks.json").read_text()
        )
        handler = definition["hooks"]["PermissionRequest"][0]["hooks"][0]
        payload = {
            "hook_event_name": "PermissionRequest",
            "session_id": "clean-install-attention-session",
            "turn_id": "clean-install-attention-turn",
            "cwd": "/synthetic/project",
            "tool_name": "Bash",
            "tool_input": {"command": "synthetic command omitted from output"},
        }

        completed = subprocess.run(
            handler["command"],
            cwd=self.temporary_directory.name,
            env=self.environment(),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            shell=True,
            timeout=handler["timeout"],
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(len(PluginDiscordHandler.requests), 1)
        request = PluginDiscordHandler.requests[0]["body"]
        self.assertIn("Needs input", request["content"])
        self.assertNotIn("synthetic command", request["content"])
        self.assertEqual(
            request["allowed_mentions"]["users"],
            [MENTION_USER_ID],
        )

    def test_companion_milestone_command_is_explicit_and_quiet(self):
        notification = {
            "session_id": "clean-install-milestone",
            "task_title": "Clean plugin package",
            "project": "codex-discord",
            "result": "The reusable package reached a checkpoint.",
            "validation": "The isolated plugin contract passed.",
        }

        completed = self.run_plugin(
            "milestone",
            input=json.dumps(notification),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "published")
        self.assertEqual(len(PluginDiscordHandler.requests), 1)
        request = PluginDiscordHandler.requests[0]["body"]
        self.assertIn("Milestone", request["content"])
        self.assertEqual(request["allowed_mentions"]["users"], [])

    def test_setup_and_uninstall_commands_are_non_mutating_guidance(self):
        setup = self.run_plugin("setup")
        uninstall = self.run_plugin("uninstall")

        self.assertEqual(setup.returncode, 0, setup.stderr)
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        setup_result = json.loads(setup.stdout)
        uninstall_result = json.loads(uninstall.stdout)
        self.assertEqual(setup_result["status"], "setup-required")
        self.assertIn(
            "CODEX_DISCORD_WEBHOOK_URL",
            setup_result["required_environment"],
        )
        self.assertEqual(uninstall_result["status"], "removal-guidance")
        self.assertIn(
            str(self.plugin_data / "routing.json"),
            uninstall_result["retained_state"],
        )
        self.assertFalse(self.plugin_data.exists())
        self.assertEqual(PluginDiscordHandler.requests, [])

    def test_package_contains_no_local_configuration_or_live_artifacts(self):
        forbidden_names = {
            "hooks.example.json",
            "hooks.local.json",
            "routing.json",
            "captures.jsonl",
        }
        packaged_files = [
            path for path in self.install_root.rglob("*") if path.is_file()
        ]

        self.assertFalse(
            forbidden_names.intersection(path.name for path in packaged_files)
        )
        package_text = "\n".join(
            path.read_text(errors="replace") for path in packaged_files
        )
        self.assertNotIn("discord.com/api/webhooks/", package_text)
        self.assertIsNone(
            re.search(r"(?<![0-9])[0-9]{17,20}(?![0-9])", package_text)
        )
        self.assertNotIn("/Users/", package_text)


if __name__ == "__main__":
    unittest.main()
