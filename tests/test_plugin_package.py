import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, parse, request


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCE = REPOSITORY_ROOT / "plugins" / "codex-discord"
MENTION_USER_ID = "123456789012345678"
WEBHOOK_TOKEN = "offline-plugin-contract-token"


class PluginDiscordHandler(BaseHTTPRequestHandler):
    requests = []
    response_status = 200
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
        self.send_response(self.__class__.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        pass


class PluginPackageTests(unittest.TestCase):
    def setUp(self):
        PluginDiscordHandler.requests = []
        PluginDiscordHandler.response_status = 200
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

    def environment(self, *, configured=True):
        environment = os.environ.copy()
        environment.update(
            {
                "PLUGIN_ROOT": str(self.install_root),
                "PLUGIN_DATA": str(self.plugin_data),
            }
        )
        environment.pop("CODEX_DISCORD_WEBHOOK_URL", None)
        environment.pop("CODEX_DISCORD_MENTION_USER_ID", None)
        environment.pop("CODEX_DISCORD_STATE_FILE", None)
        environment.pop("CODEX_DISCORD_DESTINATION_TYPE", None)
        if configured:
            environment.update(
                {
                    "CODEX_DISCORD_WEBHOOK_URL": self.endpoint,
                    "CODEX_DISCORD_MENTION_USER_ID": MENTION_USER_ID,
                    "CODEX_DISCORD_DESTINATION_TYPE": "forum-channel",
                }
            )
        return environment

    def run_plugin(self, *arguments, input=None, environment=None):
        return subprocess.run(
            [
                sys.executable,
                str(self.install_root / "scripts" / "codex-discord"),
                *arguments,
            ],
            cwd=self.temporary_directory.name,
            env=environment or self.environment(),
            input=input,
            text=True,
            capture_output=True,
            check=False,
            timeout=8,
        )

    def start_onboarding(self):
        process = subprocess.Popen(
            [
                sys.executable,
                str(self.install_root / "scripts" / "codex-discord"),
                "onboard",
                "--no-open",
                "--timeout-seconds",
                "8",
            ],
            cwd=self.temporary_directory.name,
            env=self.environment(configured=False),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdout is not None
        announcement = json.loads(process.stdout.readline())
        self.assertEqual(announcement["status"], "connection-required")
        self.assertTrue(announcement["url"].startswith("http://127.0.0.1:"))
        return process, announcement["url"]

    def submit_onboarding(self, onboarding_url, values, *, path="connect"):
        endpoint = parse.urljoin(onboarding_url, path)
        return request.urlopen(
            request.Request(
                endpoint,
                data=parse.urlencode(values).encode(),
                method="POST",
            ),
            timeout=4,
        )

    def finish_onboarding(self, process):
        stdout, stderr = process.communicate(timeout=8)
        return process.returncode, json.loads(stdout.strip()), stderr

    def test_manifest_and_default_hook_discovery_are_installable(self):
        manifest = json.loads(
            (self.install_root / ".codex-plugin" / "plugin.json").read_text()
        )
        hooks = json.loads(
            (self.install_root / "hooks" / "hooks.json").read_text()
        )

        self.assertEqual(manifest["name"], "codex-discord")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        self.assertTrue((self.install_root / ".mcp.json").is_file())
        self.assertTrue((self.install_root / "mcp" / "server.py").is_file())
        self.assertNotIn("hooks", manifest)
        self.assertEqual(set(hooks["hooks"]), {"Stop", "PermissionRequest"})
        for event in hooks["hooks"].values():
            handler = event[0]["hooks"][0]
            self.assertIn("$PLUGIN_ROOT", handler["command"])
            self.assertIn("$PLUGIN_DATA", handler["command"])

    def test_listing_and_router_make_connection_the_first_action(self):
        manifest = json.loads(
            (self.install_root / ".codex-plugin" / "plugin.json").read_text()
        )
        router_skill = (
            self.install_root / "skills" / "discord" / "SKILL.md"
        ).read_text()

        self.assertIn(
            "Connect a Discord text or forum channel",
            manifest["interface"]["longDescription"],
        )
        self.assertEqual(
            manifest["interface"]["defaultPrompt"][0],
            "Connect Discord.",
        )
        self.assertIn("scripts/codex-discord", router_skill)
        self.assertIn("onboard", router_skill)
        self.assertIn("Never ask the user to run", router_skill)
        self.assertNotIn("connect --send-test", router_skill)
        self.assertIn("Never ask the user to paste", router_skill)
        self.assertIn("PersonalAssistant", router_skill)

    def test_browser_onboarding_stores_config_tests_send_and_allows_hooks(self):
        process, onboarding_url = self.start_onboarding()
        with request.urlopen(onboarding_url, timeout=4) as response:
            setup_page = response.read().decode()
        self.assertIn("Connect Discord", setup_page)
        self.assertIn('type="password"', setup_page)
        self.assertIn("Connect and test", setup_page)
        self.assertIn('value="text-channel" checked', setup_page)
        self.assertIn('value="forum-channel"', setup_page)
        self.assertIn("Recommended", setup_page)
        self.assertIn("formnovalidate", setup_page)
        self.assertNotIn(str(self.install_root), setup_page)

        with self.submit_onboarding(
            onboarding_url,
            {
                "webhook": self.endpoint,
                "mention_user_id": MENTION_USER_ID,
            },
        ) as response:
            success_page = response.read().decode()

        returncode, result, stderr = self.finish_onboarding(process)
        self.assertEqual(returncode, 0, stderr)
        self.assertIn("Discord is connected", success_page)
        self.assertIn("plugin-message", success_page)
        self.assertEqual(result["status"], "connected")
        self.assertEqual(result["attention_mentions"], "configured")
        self.assertEqual(result["verification"]["status"], "sent")
        self.assertEqual(result["verification"]["message_id"], "plugin-message")
        self.assertEqual(result["destination"], "text-channel")
        self.assertEqual(
            result["verification"]["destination_type"],
            "text-channel",
        )
        self.assertEqual(
            result["verification"]["channel_id"],
            "plugin-thread",
        )
        self.assertNotIn("thread_id", result["verification"])
        self.assertEqual(
            result["next_action"],
            "Ask Codex to send a message to Discord.",
        )
        combined = json.dumps(result) + stderr
        self.assertNotIn(WEBHOOK_TOKEN, combined)
        self.assertNotIn(MENTION_USER_ID, combined)
        config_file = self.plugin_data / "config.json"
        self.assertTrue(config_file.is_file())
        self.assertEqual(stat.S_IMODE(config_file.stat().st_mode), 0o600)

        doctor = self.run_plugin(
            "doctor",
            environment=self.environment(configured=False),
        )
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertEqual(json.loads(doctor.stdout)["status"], "ready")
        self.assertEqual(len(PluginDiscordHandler.requests), 1)
        self.assertEqual(
            PluginDiscordHandler.requests[0]["body"]["content"],
            "Codex Discord is connected and ready.",
        )
        self.assertNotIn(
            "thread_name",
            PluginDiscordHandler.requests[0]["body"],
        )

        definition = json.loads(
            (self.install_root / "hooks" / "hooks.json").read_text()
        )
        handler = definition["hooks"]["Stop"][0]["hooks"][0]
        PluginDiscordHandler.requests = []
        hook = subprocess.run(
            handler["command"],
            cwd=self.temporary_directory.name,
            env=self.environment(configured=False),
            input=json.dumps(
                {
                    "hook_event_name": "Stop",
                    "session_id": "configured-session",
                    "turn_id": "configured-turn",
                    "cwd": "/synthetic/project",
                    "last_assistant_message": "Private connection is active.",
                }
            ),
            text=True,
            capture_output=True,
            check=False,
            shell=True,
            timeout=handler["timeout"],
        )
        self.assertEqual(hook.returncode, 0, hook.stderr)
        self.assertEqual(len(PluginDiscordHandler.requests), 1)
        self.assertNotIn(
            "thread_name",
            PluginDiscordHandler.requests[0]["body"],
        )

    def test_browser_onboarding_can_select_forum_delivery(self):
        process, onboarding_url = self.start_onboarding()
        with self.submit_onboarding(
            onboarding_url,
            {
                "webhook": self.endpoint,
                "mention_user_id": "",
                "destination_type": "forum-channel",
            },
        ):
            pass
        returncode, result, stderr = self.finish_onboarding(process)

        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(result["destination"], "forum-channel")
        self.assertEqual(
            result["verification"]["thread_id"],
            "plugin-thread",
        )
        self.assertEqual(
            PluginDiscordHandler.requests[0]["body"]["thread_name"],
            "Codex Discord",
        )
        stored = json.loads((self.plugin_data / "config.json").read_text())
        self.assertEqual(
            stored["CODEX_DISCORD_DESTINATION_TYPE"],
            "forum-channel",
        )

    def test_browser_onboarding_rejects_invalid_values_without_storing_or_echoing(self):
        invalid_webhook = (
            "https://example.invalid/api/webhooks/123456789012345678/"
            f"{WEBHOOK_TOKEN}"
        )
        process, onboarding_url = self.start_onboarding()
        with self.assertRaises(error.HTTPError) as raised:
            self.submit_onboarding(
                onboarding_url,
                {
                    "webhook": invalid_webhook,
                    "mention_user_id": "not-a-numeric-id",
                },
            )
        response_body = raised.exception.read().decode()
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("valid webhook", response_body)
        self.assertNotIn(WEBHOOK_TOKEN, response_body)
        self.assertFalse((self.plugin_data / "config.json").exists())

        with self.submit_onboarding(onboarding_url, {}, path="cancel"):
            pass
        returncode, result, stderr = self.finish_onboarding(process)
        self.assertEqual(returncode, 1)
        self.assertEqual(result["status"], "cancelled")
        combined = json.dumps(result) + stderr
        self.assertNotIn(WEBHOOK_TOKEN, combined)
        self.assertNotIn(invalid_webhook, combined)

    def test_browser_onboarding_allows_send_only_configuration(self):
        process, onboarding_url = self.start_onboarding()
        with self.submit_onboarding(
            onboarding_url,
            {"webhook": self.endpoint, "mention_user_id": ""},
        ):
            pass
        returncode, result, stderr = self.finish_onboarding(process)

        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(result["status"], "connected")
        self.assertEqual(result["attention_mentions"], "not-configured")
        self.assertEqual(result["verification"]["status"], "sent")
        stored = json.loads((self.plugin_data / "config.json").read_text())
        self.assertNotIn("CODEX_DISCORD_MENTION_USER_ID", stored)
        self.assertEqual(
            stored["CODEX_DISCORD_DESTINATION_TYPE"],
            "text-channel",
        )

        doctor = self.run_plugin(
            "doctor",
            environment=self.environment(configured=False),
        )
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        doctor_result = json.loads(doctor.stdout)
        self.assertEqual(doctor_result["status"], "ready")
        self.assertEqual(
            doctor_result["checks"]["mention_user_id"],
            "not-configured",
        )
        self.assertEqual(len(PluginDiscordHandler.requests), 1)

    def test_browser_onboarding_failure_is_visible_and_not_saved(self):
        PluginDiscordHandler.response_status = 503
        process, onboarding_url = self.start_onboarding()
        with self.assertRaises(error.HTTPError) as raised:
            self.submit_onboarding(
                onboarding_url,
                {"webhook": self.endpoint, "mention_user_id": ""},
            )
        response_body = raised.exception.read().decode()
        self.assertEqual(raised.exception.code, 502)
        self.assertIn("Discord returned transient HTTP 503", response_body)
        self.assertFalse((self.plugin_data / "config.json").exists())
        self.assertEqual(len(PluginDiscordHandler.requests), 3)
        self.assertNotIn(WEBHOOK_TOKEN, response_body)

        with self.submit_onboarding(onboarding_url, {}, path="cancel"):
            pass
        returncode, result, stderr = self.finish_onboarding(process)
        self.assertEqual(returncode, 1)
        self.assertEqual(result["status"], "cancelled")
        self.assertNotIn(WEBHOOK_TOKEN, json.dumps(result) + stderr)

    def test_superseded_terminal_interfaces_are_not_exposed(self):
        for command in ("setup", "connect", "send"):
            completed = self.run_plugin(command, input="{}\n")

            self.assertEqual(completed.returncode, 1)
            self.assertIn(f"unknown operation: {command}", completed.stderr)
        self.assertEqual(PluginDiscordHandler.requests, [])

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

    def test_superseded_milestone_surface_is_not_packaged(self):
        completed = self.run_plugin("milestone", input="{}")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("unknown operation: milestone", completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(PluginDiscordHandler.requests, [])
        self.assertFalse(
            (
                self.install_root
                / "skills"
                / "discord-milestone"
                / "SKILL.md"
            ).exists()
        )

    def test_uninstall_command_is_non_mutating_guidance(self):
        uninstall = self.run_plugin("uninstall")

        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        uninstall_result = json.loads(uninstall.stdout)
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
