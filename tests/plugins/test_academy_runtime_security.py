"""Security regressions for academy runtime routing and bindings."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from plugins.academy_ops.academy_query_tools import _resolve_client
from plugins.academy_ops.auth_flow import AcademyLoginResult, complete_login, create_login_link
from plugins.academy_ops.auth_store import AcademyBinding, encrypt_token, get_binding, save_binding
from plugins.academy_ops.context import DISCORD_USER_ID
from plugins.academy_ops.paca_client import AcademyLoginError, login_paca


def test_login_paca_requires_explicit_paca_base_url(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.delenv("MIHO_ACADEMY_PACA_BASE_URL", raising=False)

    def fail_if_network_is_touched(*_: object, **__: object) -> object:
        raise AssertionError("missing config must fail before any HTTP call")

    monkeypatch.setattr("plugins.academy_ops.paca_client.httpx.Client", fail_if_network_is_touched)

    with pytest.raises(AcademyLoginError) as exc:
        login_paca(email="owner@example.com", password="secret")

    assert str(exc.value) == "학원 서버 연결 설정을 확인하지 못했어. 관리자에게 문의해줘."


def test_login_paca_uses_configured_paca_base_url(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.delenv("MIHO_ACADEMY_PACA_BASE_URL", raising=False)
    config = tmp_path / "config.yaml"
    config.write_text("academy_ops:\n  paca_base_url: https://paca.example.test\n", encoding="utf-8")

    def handler(request):
        assert str(request.url) == "https://paca.example.test/paca/auth/login"
        return _login_response()

    result = login_paca(
        email="owner@example.com",
        password="secret",
        transport=httpx.MockTransport(handler),
    )

    assert result.academy_id == "3"


def test_complete_login_records_jwt_expiry_and_encrypts_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    token = _jwt({"userId": 11, "exp": 1_800_000_000})
    link = create_login_link(discord_user_id="discord-user-1", now=100)

    binding = complete_login(
        link.state,
        AcademyLoginResult(
            token=token,
            user_id="11",
            email="owner@example.com",
            name="원장",
            role="owner",
            academy_id="3",
            academy_name="학원",
        ),
        now=120,
    )

    assert binding.token_expires_at == 1_800_000_000
    assert get_binding("discord-user-1") == binding
    assert token not in (tmp_path / "academy_ops" / "bindings.json").read_text(encoding="utf-8")


def test_complete_login_rejects_token_academy_mismatch(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    token = _jwt({"userId": 11, "academyId": 9, "exp": 1_800_000_000})
    link = create_login_link(discord_user_id="discord-user-1", now=100)

    with pytest.raises(ValueError) as exc:
        complete_login(
            link.state,
            AcademyLoginResult(
                token=token,
                user_id="11",
                email="owner@example.com",
                name="원장",
                role="owner",
                academy_id="3",
                academy_name="학원",
            ),
            now=120,
        )

    assert str(exc.value) == "학원 계정 정보를 확인하지 못했어. 관리자에게 문의해줘."
    assert get_binding("discord-user-1") is None


def test_runtime_client_blocks_expired_bound_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    DISCORD_USER_ID.set("discord-user-1")
    save_binding(
        AcademyBinding(
            discord_user_id="discord-user-1",
            user_id="11",
            email="owner@example.com",
            name="원장",
            role="owner",
            academy_id="3",
            academy_name="학원",
            token_ciphertext=encrypt_token(_jwt({"userId": 11, "exp": 1})),
            token_expires_at=1,
            created_at=1,
            updated_at=1,
        )
    )

    assert _resolve_client() == "학원 계정 연결을 다시 확인해줘. `/academy login`으로 새로 연결해줘."


def test_runtime_client_blocks_bound_token_academy_mismatch(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setenv("MIHO_ACADEMY_PACA_BASE_URL", "https://example.test")
    DISCORD_USER_ID.set("discord-user-1")
    save_binding(
        AcademyBinding(
            discord_user_id="discord-user-1",
            user_id="11",
            email="owner@example.com",
            name="원장",
            role="owner",
            academy_id="3",
            academy_name="학원",
            token_ciphertext=encrypt_token(_jwt({"userId": 11, "academyId": 9, "exp": 1_800_000_000})),
            token_expires_at=1_800_000_000,
            created_at=1,
            updated_at=1,
        )
    )

    assert _resolve_client() == "학원 계정 정보를 확인하지 못했어. 관리자에게 문의해줘."


def _jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}
    parts = [_b64(header), _b64(payload), "signature"]
    return ".".join(parts)


def _b64(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _login_response():
    return httpx.Response(
        200,
        json={
            "token": _jwt({"userId": 11, "exp": 1_800_000_000}),
            "user": {
                "id": 11,
                "email": "owner@example.com",
                "name": "원장",
                "role": "owner",
                "academyId": 3,
                "academy": {"name": "학원"},
            },
        },
    )
