"""One-time login link flow for Discord-to-PACA/Peak account binding."""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlencode

from miho_constants import get_miho_home
from utils import atomic_json_write

from .auth_store import AcademyBinding, encrypt_token, save_binding
from .remote_auth import (
    fetch_remote_result,
    is_loopback_base_url,
    register_remote_pending,
)


DEFAULT_AUTH_BASE_URL = "https://academy-login.etlab.kr"
LINK_TTL_SECONDS = 10 * 60


@dataclass(frozen=True)
class LoginLink:
    state: str
    url: str
    expires_at: int


@dataclass(frozen=True)
class PendingLogin:
    state: str
    discord_user_id: str
    guild_id: str
    channel_id: str
    created_at: int
    expires_at: int
    claim_secret: str = ""
    broker_base_url: str = ""


@dataclass(frozen=True)
class AcademyLoginResult:
    token: str
    user_id: str
    email: str
    name: str
    role: str
    academy_id: str
    academy_name: str


def create_login_link(
    *,
    discord_user_id: str,
    guild_id: str = "",
    channel_id: str = "",
    base_url: str | None = None,
    now: int | None = None,
) -> LoginLink:
    current = int(now or time.time())
    state = secrets.token_urlsafe(32)
    auth_base = resolve_auth_base_url(base_url).rstrip("/")
    claim_secret = ""
    broker_base_url = ""
    if not is_loopback_base_url(auth_base):
        claim_secret = secrets.token_urlsafe(32)
        broker_base_url = auth_base
    pending = PendingLogin(
        state=state,
        discord_user_id=str(discord_user_id),
        guild_id=str(guild_id or ""),
        channel_id=str(channel_id or ""),
        created_at=current,
        expires_at=current + LINK_TTL_SECONDS,
        claim_secret=claim_secret,
        broker_base_url=broker_base_url,
    )
    _save_pending(pending)
    if broker_base_url:
        register_remote_pending(broker_base_url, asdict(pending))
        _start_remote_result_poll(pending)
    query = urlencode({"state": state})
    return LoginLink(
        state=state,
        url=f"{auth_base}/academy/login?{query}",
        expires_at=pending.expires_at,
    )


def complete_login(state: str, result: AcademyLoginResult, *, now: int | None = None) -> AcademyBinding:
    pending = consume_pending_login(state, now=now)
    current = int(now or time.time())
    binding = AcademyBinding(
        discord_user_id=pending.discord_user_id,
        user_id=str(result.user_id),
        email=result.email,
        name=result.name,
        role=result.role,
        academy_id=str(result.academy_id),
        academy_name=result.academy_name,
        token_ciphertext=encrypt_token(result.token),
        created_at=current,
        updated_at=current,
    )
    save_binding(binding)
    return binding


def consume_pending_login(state: str, *, now: int | None = None) -> PendingLogin:
    clean = state.strip()
    pending = load_pending_logins()
    item = pending.pop(clean, None)
    _write_pending(pending)
    if item is None:
        raise ValueError("로그인 링크가 만료되었거나 이미 사용됐어.")
    if item.expires_at < int(now or time.time()):
        raise ValueError("로그인 링크가 만료됐어. 디스코드에서 다시 로그인 링크를 받아줘.")
    return item


def load_pending_logins() -> dict[str, PendingLogin]:
    path = pending_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    items: dict[str, PendingLogin] = {}
    for state, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            items[str(state)] = PendingLogin(
                state=str(value.get("state") or state),
                discord_user_id=str(value.get("discord_user_id") or ""),
                guild_id=str(value.get("guild_id") or ""),
                channel_id=str(value.get("channel_id") or ""),
                created_at=int(value.get("created_at") or 0),
                expires_at=int(value.get("expires_at") or 0),
                claim_secret=str(value.get("claim_secret") or ""),
                broker_base_url=str(value.get("broker_base_url") or ""),
            )
        except (TypeError, ValueError):
            continue
    return items


def has_pending_login_for_user(discord_user_id: str, *, now: int | None = None) -> bool:
    current = int(now or time.time())
    user_id = str(discord_user_id)
    return any(
        item.discord_user_id == user_id and item.expires_at >= current for item in load_pending_logins().values()
    )


def refresh_remote_pending_logins(*, now: int | None = None) -> int:
    current = int(now or time.time())
    completed = 0
    for pending in list(load_pending_logins().values()):
        if not pending.broker_base_url or not pending.claim_secret:
            continue
        if pending.expires_at < current:
            continue
        if _complete_remote_pending(pending):
            completed += 1
    return completed


def purge_expired_pending(*, now: int | None = None) -> int:
    current = int(now or time.time())
    pending = load_pending_logins()
    kept = {key: value for key, value in pending.items() if value.expires_at >= current}
    removed = len(pending) - len(kept)
    if removed:
        _write_pending(kept)
    return removed


def pending_path() -> Path:
    return get_miho_home() / "academy_ops" / "pending_logins.json"


def resolve_auth_base_url(base_url: str | None = None) -> str:
    if base_url:
        return base_url
    env_value = os.getenv("MIHO_ACADEMY_AUTH_BASE_URL", "").strip()
    if env_value:
        return env_value
    try:
        from miho_cli.config import cfg_get, load_config

        cfg_value = cfg_get(load_config(), "academy_ops", "auth_base_url", default="")
    except Exception:
        cfg_value = ""
    if isinstance(cfg_value, str) and cfg_value.strip():
        return cfg_value.strip()
    return DEFAULT_AUTH_BASE_URL


def _save_pending(pending: PendingLogin) -> None:
    items = load_pending_logins()
    items[pending.state] = pending
    _write_pending(items)


def _complete_remote_pending(pending: PendingLogin) -> bool:
    payload = fetch_remote_result(
        pending.broker_base_url,
        state=pending.state,
        claim_secret=pending.claim_secret,
    )
    if not payload:
        return False
    try:
        complete_login(pending.state, AcademyLoginResult(**payload))
    except (TypeError, ValueError):
        return False
    return True


def _start_remote_result_poll(pending: PendingLogin) -> None:
    def _poll() -> None:
        while int(time.time()) <= pending.expires_at:
            if _complete_remote_pending(pending):
                return
            time.sleep(2.0)

    threading.Thread(
        target=_poll,
        name=f"academy-login-poll-{pending.state[:8]}",
        daemon=True,
    ).start()


def _write_pending(items: dict[str, PendingLogin]) -> None:
    payload = {key: asdict(value) for key, value in items.items()}
    pending_path().parent.mkdir(parents=True, exist_ok=True)
    atomic_json_write(pending_path(), payload)
