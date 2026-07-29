"""Private localhost onboarding UI for the installed Discord plugin."""

from __future__ import annotations

import html
import json
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Mapping, Optional
from urllib.parse import parse_qs, urlsplit


MAX_FORM_BYTES = 16 * 1024


def _shell(body: str, *, title: str = "Connect Discord") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --brand: #5865f2;
      --brand-hover: #4752c4;
      --bg: #f5f6f8;
      --card: #ffffff;
      --text: #1e1f22;
      --muted: #5c6068;
      --line: #d9dce1;
      --soft: #eef0ff;
      --danger: #b42318;
      --danger-bg: #fff1f0;
      --success: #067647;
      --success-bg: #ecfdf3;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{ width: min(680px, calc(100% - 32px)); margin: 48px auto; }}
    .brand {{ display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }}
    .mark {{
      display: grid; place-items: center; width: 44px; height: 44px;
      border-radius: 13px; background: var(--brand); color: white;
      font-weight: 800; font-size: 21px;
    }}
    .brand strong {{ display: block; font-size: 18px; }}
    .brand span {{ color: var(--muted); font-size: 14px; }}
    .card {{
      background: var(--card); border: 1px solid var(--line);
      border-radius: 18px; padding: 32px; box-shadow: 0 12px 36px rgba(0,0,0,.08);
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: -.02em; }}
    h2 {{ margin: 28px 0 12px; font-size: 17px; }}
    p {{ margin: 0 0 16px; }}
    .lead {{ color: var(--muted); margin-bottom: 26px; }}
    ol {{ margin: 0; padding: 0; list-style: none; counter-reset: steps; }}
    li {{
      position: relative; padding: 0 0 20px 44px; counter-increment: steps;
    }}
    li::before {{
      content: counter(steps); position: absolute; left: 0; top: -2px;
      display: grid; place-items: center; width: 28px; height: 28px;
      border-radius: 50%; background: var(--soft); color: var(--brand);
      font-weight: 700; font-size: 14px;
    }}
    li strong {{ display: block; }}
    li span {{ color: var(--muted); font-size: 14px; }}
    label {{ display: block; margin: 0 0 7px; font-weight: 650; }}
    .hint {{ color: var(--muted); font-size: 13px; margin: 7px 0 18px; }}
    input {{
      width: 100%; padding: 12px 13px; border: 1px solid var(--line);
      border-radius: 9px; background: var(--card); color: var(--text);
      font: inherit;
    }}
    input:focus {{ outline: 3px solid rgba(88,101,242,.18); border-color: var(--brand); }}
    details {{ margin: 4px 0 22px; }}
    summary {{ cursor: pointer; color: var(--muted); font-weight: 600; }}
    details .field {{ margin-top: 14px; }}
    .notice {{
      border-radius: 9px; padding: 12px 14px; margin: 0 0 20px;
      font-size: 14px;
    }}
    .private {{ background: var(--soft); color: var(--text); }}
    .error {{ background: var(--danger-bg); color: var(--danger); }}
    .success {{ background: var(--success-bg); color: var(--success); }}
    .actions {{ display: flex; gap: 10px; align-items: center; margin-top: 24px; }}
    button {{
      border: 0; border-radius: 9px; padding: 12px 18px;
      font: inherit; font-weight: 700; cursor: pointer;
    }}
    .primary {{ background: var(--brand); color: white; }}
    .primary:hover {{ background: var(--brand-hover); }}
    .secondary {{ background: transparent; color: var(--muted); }}
    .meta {{
      margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--line);
      color: var(--muted); font-size: 13px;
    }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #111214; --card: #1e1f22; --text: #f2f3f5; --muted: #b5bac1;
        --line: #3f4147; --soft: #292c58; --danger: #ffb4ab;
        --danger-bg: #4a1f1c; --success: #75e0a7; --success-bg: #143629;
      }}
    }}
    @media (max-width: 560px) {{
      main {{ margin: 20px auto; }}
      .card {{ padding: 23px; }}
      .actions {{ align-items: stretch; flex-direction: column; }}
      button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="brand">
      <div class="mark">D</div>
      <div><strong>Codex Discord</strong><span>by SpielSoft</span></div>
    </div>
    <section class="card">{body}</section>
  </main>
</body>
</html>
"""


def _setup_page(action: str, error: Optional[str] = None) -> str:
    error_notice = ""
    if error:
        error_notice = (
            '<div class="notice error" role="alert">'
            f"{html.escape(error)}</div>"
        )
    return _shell(
        f"""
      <h1>Connect Discord</h1>
      <p class="lead">Choose where Codex should send messages, then verify the connection.</p>
      {error_notice}
      <ol>
        <li>
          <strong>Choose a private forum channel</strong>
          <span>In Discord, create or select the private forum channel you want Codex to use.</span>
        </li>
        <li>
          <strong>Create a webhook</strong>
          <span>Open <b>Edit Channel → Integrations → Webhooks</b>, create a webhook, and copy its URL.</span>
        </li>
        <li>
          <strong>Connect it privately</strong>
          <span>Paste the URL below. Codex will send one visible connection-test message.</span>
        </li>
      </ol>
      <div class="notice private">
        This private setup page is served only from your computer. The webhook is
        not placed in your Codex conversation, command history, or repository.
      </div>
      <form method="post" action="{html.escape(action)}" autocomplete="off">
        <label for="webhook">Discord webhook URL</label>
        <input id="webhook" name="webhook" type="password" required
               spellcheck="false" autocapitalize="none"
               placeholder="Paste the webhook URL">
        <p class="hint">Stored locally with owner-only permissions after Discord accepts the test.</p>
        <details>
          <summary>Optional lifecycle attention mentions</summary>
          <div class="field">
            <label for="mention_user_id">Discord user ID</label>
            <input id="mention_user_id" name="mention_user_id" inputmode="numeric"
                   pattern="[0-9]{{17,20}}" placeholder="17–20 digit user ID">
            <p class="hint">Not needed for PersonalAssistant or other send-only workflows.</p>
          </div>
        </details>
        <div class="actions">
          <button class="primary" type="submit">Connect and test</button>
          <button class="secondary" type="submit" formnovalidate
                  formaction="{html.escape(action.rsplit('/', 1)[0] + '/cancel')}">
            Cancel
          </button>
        </div>
      </form>
"""
    )


def _success_page(message_id: str, thread_id: str) -> str:
    return _shell(
        f"""
      <h1>Discord is connected</h1>
      <p class="lead">Codex can now send messages to your selected forum channel.</p>
      <div class="notice success" role="status">
        Connection verified. You should see a test message in Discord.
      </div>
      <h2>Ready for PersonalAssistant</h2>
      <p>No lifecycle hooks or attention user ID are required for daily brief delivery.</p>
      <div class="meta">
        Message ID: <code>{html.escape(message_id)}</code><br>
        Thread ID: <code>{html.escape(thread_id)}</code>
      </div>
      <p class="hint">You can close this window and return to Codex.</p>
""",
        title="Discord connected",
    )


class _Session:
    def __init__(
        self,
        *,
        nonce: str,
        state_file: str,
        webhook_is_usable: Callable[[str], bool],
        user_id_is_usable: Callable[[str], bool],
        publish_message: Callable[..., Mapping[str, object]],
        store_configuration: Callable[[dict[str, str]], None],
        webhook_environment: str,
        mention_environment: str,
    ) -> None:
        self.nonce = nonce
        self.state_file = state_file
        self.webhook_is_usable = webhook_is_usable
        self.user_id_is_usable = user_id_is_usable
        self.publish_message = publish_message
        self.store_configuration = store_configuration
        self.webhook_environment = webhook_environment
        self.mention_environment = mention_environment
        self.result: Optional[Mapping[str, object]] = None
        self.exit_code = 1

    @property
    def root_path(self) -> str:
        return f"/{self.nonce}"

    @property
    def connect_path(self) -> str:
        return f"{self.root_path}/connect"

    @property
    def cancel_path(self) -> str:
        return f"{self.root_path}/cancel"


class _OnboardingHandler(BaseHTTPRequestHandler):
    server_version = "CodexDiscordOnboarding/1"
    session: _Session

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(encoded)

    def _form(self) -> Mapping[str, str]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_FORM_BYTES:
            return {}
        try:
            values = parse_qs(
                self.rfile.read(length).decode("utf-8"),
                keep_blank_values=True,
                max_num_fields=4,
            )
        except (UnicodeDecodeError, ValueError):
            return {}
        return {
            key: candidates[0]
            for key, candidates in values.items()
            if candidates and key in ("webhook", "mention_user_id")
        }

    def do_GET(self) -> None:
        if urlsplit(self.path).path not in (
            self.session.root_path,
            f"{self.session.root_path}/",
        ):
            self.send_error(404)
            return
        self._send_html(_setup_page(self.session.connect_path))

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == self.session.cancel_path:
            self.session.result = {
                "status": "cancelled",
                "message": "Discord connection was cancelled. No configuration was changed.",
            }
            self._send_html(
                _shell(
                    """
                    <h1>Connection cancelled</h1>
                    <p>No Discord configuration was changed. You can close this window.</p>
                    """,
                    title="Connection cancelled",
                )
            )
            return
        if path != self.session.connect_path:
            self.send_error(404)
            return

        values = self._form()
        endpoint = values.get("webhook", "").strip()
        mention_user_id = values.get("mention_user_id", "").strip()
        if not self.session.webhook_is_usable(endpoint):
            self._send_html(
                _setup_page(
                    self.session.connect_path,
                    "Enter a valid webhook created for a Discord forum channel.",
                ),
                status=400,
            )
            return
        if mention_user_id and not self.session.user_id_is_usable(mention_user_id):
            self._send_html(
                _setup_page(
                    self.session.connect_path,
                    "Enter a numeric 17–20 digit Discord user ID, or leave it blank.",
                ),
                status=400,
            )
            return

        verification = self.session.publish_message(
            {
                "message": "Codex Discord is connected and ready.",
                "thread_name": "Codex Discord",
                "route_key": "codex-discord-connection-test",
            },
            endpoint,
            self.session.state_file,
        )
        if verification.get("status") != "sent":
            diagnostic = verification.get("diagnostic")
            safe_message = (
                diagnostic
                if isinstance(diagnostic, str) and diagnostic
                else "Discord did not accept the connection test."
            )
            self._send_html(
                _setup_page(self.session.connect_path, safe_message),
                status=502,
            )
            return

        configuration = {self.session.webhook_environment: endpoint}
        if mention_user_id:
            configuration[self.session.mention_environment] = mention_user_id
        self.session.store_configuration(configuration)
        message_id = str(verification.get("message_id", "unknown"))
        thread_id = str(verification.get("thread_id", "unknown"))
        self.session.result = {
            "status": "connected",
            "destination": "discord-forum-webhook",
            "attention_mentions": (
                "configured" if mention_user_id else "not-configured"
            ),
            "verification": {
                "status": "sent",
                "message_id": message_id,
                "thread_id": thread_id,
            },
            "next_action": "Ask Codex to send a message to Discord.",
        }
        self.session.exit_code = 0
        self._send_html(_success_page(message_id, thread_id))


def run_onboarding(
    *,
    state_file: str,
    webhook_is_usable: Callable[[str], bool],
    user_id_is_usable: Callable[[str], bool],
    publish_message: Callable[..., Mapping[str, object]],
    store_configuration: Callable[[dict[str, str]], None],
    webhook_environment: str,
    mention_environment: str,
    announce: Callable[[Mapping[str, object]], None],
    open_browser: bool = True,
    timeout_seconds: float = 900.0,
) -> tuple[Mapping[str, object], int]:
    """Run one private browser-based connection session."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    nonce = secrets.token_urlsafe(24)
    session = _Session(
        nonce=nonce,
        state_file=state_file,
        webhook_is_usable=webhook_is_usable,
        user_id_is_usable=user_id_is_usable,
        publish_message=publish_message,
        store_configuration=store_configuration,
        webhook_environment=webhook_environment,
        mention_environment=mention_environment,
    )

    # Assigning the session on the class before request dispatch avoids exposing
    # it in the handler constructor used by BaseHTTPRequestHandler.
    _OnboardingHandler.session = session
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OnboardingHandler)
    server.timeout = 0.25
    url = f"http://127.0.0.1:{server.server_port}{session.root_path}/"
    announce(
        {
            "status": "connection-required",
            "url": url,
            "message": "Complete Discord connection in the opened window.",
        }
    )
    if open_browser:
        try:
            webbrowser.open(url, new=1, autoraise=True)
        except Exception:
            pass

    deadline = time.monotonic() + timeout_seconds
    try:
        while session.result is None and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    if session.result is None:
        return (
            {
                "status": "timed-out",
                "message": "Discord connection timed out. No configuration was changed.",
            },
            1,
        )
    return session.result, session.exit_code
