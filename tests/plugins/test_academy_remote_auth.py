"""Tests for public academy login broker flow."""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from plugins.academy_ops.auth_flow import (
    AcademyLoginResult,
    create_login_link,
    load_pending_logins,
    refresh_remote_pending_logins,
)
from plugins.academy_ops.auth_store import get_binding
from plugins.academy_ops.remote_auth import (
    BrokerPendingLogin,
    consume_broker_result,
    get_broker_pending,
    save_broker_pending,
    set_broker_result,
)
from plugins.academy_ops.server import AcademyAuthHandler


def test_public_login_link_registers_broker_pending(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "plugins.academy_ops.auth_flow.register_remote_pending",
        lambda _base_url, payload: calls.append(payload) or True,
    )
    monkeypatch.setattr("plugins.academy_ops.auth_flow._start_remote_result_poll", lambda _pending: None)

    link = create_login_link(
        discord_user_id="discord-1",
        guild_id="guild-1",
        channel_id="channel-1",
        base_url="https://academy-login.etlab.kr",
        now=100,
    )

    pending = load_pending_logins()[link.state]
    assert calls and calls[0]["state"] == link.state
    assert pending.claim_secret
    assert pending.broker_base_url == "https://academy-login.etlab.kr"


def test_remote_result_refresh_binds_local_install(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr("plugins.academy_ops.auth_flow.register_remote_pending", lambda *_args: True)
    monkeypatch.setattr("plugins.academy_ops.auth_flow._start_remote_result_poll", lambda _pending: None)
    link = create_login_link(discord_user_id="discord-2", base_url="https://academy-login.etlab.kr")
    pending = load_pending_logins()[link.state]
    pending_payload = asdict(pending)
    pending_payload.pop("broker_base_url", None)
    save_broker_pending(BrokerPendingLogin(**pending_payload))

    set_broker_result(
        link.state,
        asdict(
            AcademyLoginResult(
                token="paca-token",
                user_id="paca-user",
                email="owner@example.com",
                name="정으뜸",
                role="owner",
                academy_id="academy-1",
                academy_name="일산 맥스체대입시",
            )
        ),
    )
    monkeypatch.setattr(
        "plugins.academy_ops.auth_flow.fetch_remote_result",
        lambda _base_url, *, state, claim_secret: consume_broker_result(state, claim_secret),
    )

    assert refresh_remote_pending_logins() == 1
    binding = get_binding("discord-2")
    assert binding is not None
    assert binding.name == "정으뜸"
    assert binding.academy_name == "일산 맥스체대입시"


def test_broker_pending_endpoint_serves_login_page(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), AcademyAuthHandler)
    port = server.server_address[1]
    try:
        import threading

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        payload = {
            "state": "state-1",
            "discord_user_id": "discord-3",
            "guild_id": "guild-1",
            "channel_id": "channel-1",
            "created_at": 100,
            "expires_at": 9999999999,
            "claim_secret": "claim-1",
        }
        req = Request(
            f"http://127.0.0.1:{port}/academy/pending",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=5) as response:
            assert response.status == 200

        assert get_broker_pending("state-1") is not None
        with urlopen(f"http://127.0.0.1:{port}/academy/login?state=state-1", timeout=5) as response:
            body = response.read().decode("utf-8")
        assert "Miho 학원 계정 연결" in body
    finally:
        server.shutdown()
        server.server_close()


def test_broker_result_endpoint_returns_result_once(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), AcademyAuthHandler)
    port = server.server_address[1]
    try:
        import threading

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        from plugins.academy_ops.remote_auth import save_broker_pending

        save_broker_pending(
            BrokerPendingLogin(
                state="state-2",
                discord_user_id="discord-4",
                guild_id="",
                channel_id="",
                created_at=100,
                expires_at=9999999999,
                claim_secret="claim-2",
            )
        )
        set_broker_result(
            "state-2",
            {
                "token": "token",
                "user_id": "user",
                "email": "owner@example.com",
                "name": "정으뜸",
                "role": "owner",
                "academy_id": "academy",
                "academy_name": "맥스",
            },
        )

        query = urlencode({"state": "state-2", "claim": "claim-2"})
        with urlopen(f"http://127.0.0.1:{port}/academy/result?{query}", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["token"] == "token"
        assert get_broker_pending("state-2") is None
    finally:
        server.shutdown()
        server.server_close()
