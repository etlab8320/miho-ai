"""Authentication gate for natural-language academy requests."""

from __future__ import annotations

import json
import time
from typing import Any

from .auth_store import AcademyBinding, decrypt_token
from .natural_router import (
    ROUTER_MAX_ATTEMPTS,
    AcademyNaturalRoute,
    Resolver,
    ToolHandler,
    TOOL_CONTRACTS,
    resolve_and_execute_academy_request,
)
from .token_metadata import (
    ACADEMY_BINDING_ERROR_MESSAGE,
    TOKEN_EXPIRED_MESSAGE,
    binding_token_error,
)


AUTH_GATE_ROUTER_TIMEOUT_SECONDS = 8
AUTH_GATE_TOOL_TIMEOUT_SECONDS = 1
LOGIN_REQUIRED_MESSAGE = "학원 계정 연결이 필요해. `/academy login`으로 먼저 연결해줘."


def binding_auth_error(binding: AcademyBinding | None, *, now: int | None = None) -> str:
    if binding is None:
        return LOGIN_REQUIRED_MESSAGE
    current = int(now or time.time())
    if binding.token_expires_at is not None and binding.token_expires_at <= current:
        return TOKEN_EXPIRED_MESSAGE
    token = decrypt_token(binding.token_ciphertext)
    if not token:
        return ACADEMY_BINDING_ERROR_MESSAGE
    return binding_token_error(token, academy_id=binding.academy_id, now=current)


async def academy_request_needs_login(
    text: str,
    *,
    context_key: str | None = None,
    today: str | None = None,
    resolver: Resolver | None = None,
    resolver_timeout: float = AUTH_GATE_ROUTER_TIMEOUT_SECONDS,
) -> bool:
    route = await resolve_and_execute_academy_request(
        text,
        resolver=resolver or _default_resolver,
        handlers=_login_only_handlers(),
        context_key=context_key,
        today=today,
        resolver_timeout=resolver_timeout,
        resolver_attempts=ROUTER_MAX_ATTEMPTS,
        tool_timeout=AUTH_GATE_TOOL_TIMEOUT_SECONDS,
        synthesize=False,
    )
    return route == AcademyNaturalRoute.HANDLED


def _login_only_handlers() -> dict[str, ToolHandler]:
    return {tool_name: _login_required_handler for tool_name in TOOL_CONTRACTS}


def _login_required_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    return json.dumps(
        {"ok": False, "message": LOGIN_REQUIRED_MESSAGE},
        ensure_ascii=False,
    )


async def _default_resolver(messages: list[dict[str, str]]) -> Any:
    from .natural_router import default_resolver

    return await default_resolver(messages)
