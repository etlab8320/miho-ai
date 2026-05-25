"""Small HTTP server for the PACA/Peak Discord login binding flow."""

from __future__ import annotations

import argparse
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .auth_flow import complete_login, load_pending_logins
from .auth_pages import render_error_page, render_login_page, render_success_page
from .paca_client import DEFAULT_PACA_BASE_URL, AcademyLoginError, login_paca
from .rate_limit import is_limited, record_failure, record_success


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
        if parsed.path != "/academy/login":
            self._send_html(render_error_page("요청한 페이지를 찾지 못했어."), HTTPStatus.NOT_FOUND)
            return

        state = parse_qs(parsed.query).get("state", [""])[0].strip()
        if not state or state not in load_pending_logins():
            self._send_html(render_error_page("로그인 링크가 만료되었거나 잘못됐어."), HTTPStatus.BAD_REQUEST)
            return
        self._send_html(render_login_page(state=state))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
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
                base_url=os.getenv("MIHO_ACADEMY_PACA_BASE_URL", DEFAULT_PACA_BASE_URL),
            )
            binding = complete_login(state, login_result)
        except AcademyLoginError as exc:
            record_failure(rate_key)
            self._send_html(render_login_page(state=state, error=str(exc)), HTTPStatus.UNAUTHORIZED)
            return
        except ValueError as exc:
            self._send_html(render_error_page(str(exc)), HTTPStatus.BAD_REQUEST)
            return

        record_success(rate_key)
        self._send_html(render_success_page(name=binding.name, academy_name=binding.academy_name))

    def log_message(self, fmt: str, *args: object) -> None:
        if self.path.startswith("/academy/login"):
            return
        super().log_message(fmt, *args)

    def _read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(min(length, 65536)).decode("utf-8", errors="replace")
        return parse_qs(raw, keep_blank_values=True)

    def _send_text(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

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
