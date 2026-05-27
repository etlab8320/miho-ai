"""Remote broker support for public academy login links."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from miho_constants import get_miho_home
from utils import atomic_json_write

_HTTP_TIMEOUT_SECONDS = 5
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


@dataclass(frozen=True)
class BrokerPendingLogin:
    state: str
    discord_user_id: str
    guild_id: str
    channel_id: str
    created_at: int
    expires_at: int
    claim_secret: str
    result: dict[str, str] = field(default_factory=dict)


def is_loopback_base_url(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host in _LOOPBACK_HOSTS


def broker_store_path() -> Path:
    return get_miho_home() / "academy_ops" / "broker_logins.json"


def register_remote_pending(base_url: str, payload: dict[str, object]) -> bool:
    url = f"{base_url.rstrip('/')}/academy/pending"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            return 200 <= response.status < 300
    except (OSError, HTTPError, URLError):
        return False


def fetch_remote_result(
    base_url: str,
    *,
    state: str,
    claim_secret: str,
) -> dict[str, str] | None:
    query = urlencode({"state": state, "claim": claim_secret})
    url = f"{base_url.rstrip('/')}/academy/result?{query}"
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            if response.status == 202:
                return None
            if response.status != 200:
                return None
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 202:
            return None
        return None
    except (OSError, URLError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_broker_pending() -> dict[str, BrokerPendingLogin]:
    path = broker_store_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    items: dict[str, BrokerPendingLogin] = {}
    for state, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            item = BrokerPendingLogin(
                state=str(value.get("state") or state),
                discord_user_id=str(value.get("discord_user_id") or ""),
                guild_id=str(value.get("guild_id") or ""),
                channel_id=str(value.get("channel_id") or ""),
                created_at=int(value.get("created_at") or 0),
                expires_at=int(value.get("expires_at") or 0),
                claim_secret=str(value.get("claim_secret") or ""),
                result=value.get("result") if isinstance(value.get("result"), dict) else {},
            )
        except (TypeError, ValueError):
            continue
        items[item.state] = item
    return items


def save_broker_pending(item: BrokerPendingLogin) -> None:
    items = _purged_broker_items()
    items[item.state] = item
    _write_broker_pending(items)


def get_broker_pending(state: str, *, now: int | None = None) -> BrokerPendingLogin | None:
    current = int(now or time.time())
    item = load_broker_pending().get(state.strip())
    if item is None or item.expires_at < current:
        return None
    return item


def set_broker_result(state: str, result: dict[str, str]) -> BrokerPendingLogin:
    items = _purged_broker_items()
    item = items.get(state.strip())
    if item is None:
        raise ValueError("로그인 링크가 만료되었거나 잘못됐어.")
    updated = BrokerPendingLogin(**{**asdict(item), "result": result})
    items[updated.state] = updated
    _write_broker_pending(items)
    return updated


def consume_broker_result(state: str, claim_secret: str) -> dict[str, str] | None:
    items = _purged_broker_items()
    item = items.get(state.strip())
    if item is None or item.claim_secret != claim_secret:
        return None
    if not item.result:
        return {}
    result = dict(item.result)
    items.pop(item.state, None)
    _write_broker_pending(items)
    return result


def _purged_broker_items() -> dict[str, BrokerPendingLogin]:
    current = int(time.time())
    return {
        state: item
        for state, item in load_broker_pending().items()
        if item.expires_at >= current
    }


def _write_broker_pending(items: dict[str, BrokerPendingLogin]) -> None:
    path = broker_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json_write(path, {state: asdict(item) for state, item in items.items()})
    try:
        path.chmod(0o600)
    except OSError:
        pass
