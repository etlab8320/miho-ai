"""Small HTTP server for the PACA/Peak Discord login binding flow."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .auth_flow import complete_login, load_pending_logins
from .auth_pages import render_error_page, render_login_page, render_success_page
from .paca_client import AcademyLoginError, login_paca
from .rate_limit import is_limited, record_failure, record_success
from .remote_auth import (
    BrokerPendingLogin,
    consume_broker_result,
    get_broker_pending,
    save_broker_pending,
    set_broker_result,
)


class AcademyAuthHandler(BaseHTTPRequestHandler):
    server_version = "MihoAcademyAuth/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_text("ok")
            return
        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            return
        if parsed.path == "/academy/result":
            self._handle_result_request(parsed)
            return
        if parsed.path != "/academy/login":
            self._send_html(render_error_page("요청한 페이지를 찾지 못했어."), HTTPStatus.NOT_FOUND)
            return

        state = parse_qs(parsed.query).get("state", [""])[0].strip()
        if not state or (state not in load_pending_logins() and get_broker_pending(state) is None):
            self._send_html(render_error_page("로그인 링크가 만료되었거나 잘못됐어."), HTTPStatus.BAD_REQUEST)
            return
        self._send_html(render_login_page(state=state))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/academy/pending":
            self._handle_pending_registration()
            return
        if parsed.path != "/academy/login":
            self._send_html(render_error_page("요청한 페이지를 찾지 못했어."), HTTPStatus.NOT_FOUND)
            return

        form = self._read_form()
        state = form.get("state", [""])[0].strip()
        email = form.get("email", [""])[0].strip()
        password = form.get("password", [""])[0]
        if not state or not email or not password:
            self._send_html(
                render_login_page(state=state, error="이메일과 비밀번호를 입력해줘."),
                HTTPStatus.BAD_REQUEST,
            )
            return
        rate_key = self._rate_limit_key(email)
        if is_limited(rate_key):
            self._send_html(
                render_login_page(state=state, error="로그인 시도가 너무 많아. 잠시 후 다시 시도해줘."),
                HTTPStatus.TOO_MANY_REQUESTS,
            )
            return

        try:
            login_result = login_paca(
                email=email,
                password=password,
            )
            if state in load_pending_logins():
                binding = complete_login(state, login_result)
                success_name = binding.name
                success_academy = binding.academy_name
            elif get_broker_pending(state) is not None:
                set_broker_result(state, asdict(login_result))
                success_name = login_result.name
                success_academy = login_result.academy_name
            else:
                raise ValueError("로그인 링크가 만료되었거나 잘못됐어.")
        except AcademyLoginError as exc:
            record_failure(rate_key)
            self._send_html(render_login_page(state=state, error=str(exc)), HTTPStatus.UNAUTHORIZED)
            return
        except ValueError as exc:
            self._send_html(render_error_page(str(exc)), HTTPStatus.BAD_REQUEST)
            return

        record_success(rate_key)
        self._send_html(render_success_page(name=success_name, academy_name=success_academy))

    def log_message(self, fmt: str, *args: object) -> None:
        if self.path.startswith("/academy/login"):
            return
        super().log_message(fmt, *args)

    def _read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(min(length, 65536)).decode("utf-8", errors="replace")
        return parse_qs(raw, keep_blank_values=True)

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(min(length, 65536)).decode("utf-8", errors="replace")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}

    def _handle_pending_registration(self) -> None:
        try:
            payload = self._read_json()
            item = BrokerPendingLogin(
                state=str(payload.get("state") or ""),
                discord_user_id=str(payload.get("discord_user_id") or ""),
                guild_id=str(payload.get("guild_id") or ""),
                channel_id=str(payload.get("channel_id") or ""),
                created_at=int(payload.get("created_at") or 0),
                expires_at=int(payload.get("expires_at") or 0),
                claim_secret=str(payload.get("claim_secret") or ""),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            self._send_json({"ok": False, "error": "bad_request"}, HTTPStatus.BAD_REQUEST)
            return
        if not item.state or not item.claim_secret or item.expires_at <= item.created_at:
            self._send_json({"ok": False, "error": "bad_request"}, HTTPStatus.BAD_REQUEST)
            return
        save_broker_pending(item)
        self._send_json({"ok": True})

    def _handle_result_request(self, parsed) -> None:  # noqa: ANN001
        params = parse_qs(parsed.query)
        state = params.get("state", [""])[0].strip()
        claim = params.get("claim", [""])[0].strip()
        result = consume_broker_result(state, claim)
        if result is None:
            self._send_json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        if not result:
            self._send_json({"ok": False, "status": "pending"}, HTTPStatus.ACCEPTED)
            return
        self._send_json(result)

    def _send_text(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _rate_limit_key(self, email: str) -> str:
        forwarded_for = self.headers.get("X-Forwarded-For", "")
        client_ip = forwarded_for.split(",", 1)[0].strip() or self.client_address[0]
        return f"{client_ip}:{email.lower()}"


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), AcademyAuthHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Miho academy auth binding server")
    parser.add_argument("--host", default=os.getenv("MIHO_ACADEMY_AUTH_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MIHO_ACADEMY_AUTH_PORT", "8765")))
    args = parser.parse_args()
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
