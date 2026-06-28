"""Turn-scoped runtime context shared by tool handlers."""

from __future__ import annotations

import uuid
from contextvars import ContextVar


_CURRENT_TURN_TOKEN: ContextVar[str] = ContextVar("miho_current_turn_token", default="")
_CURRENT_USER_MESSAGE: ContextVar[str] = ContextVar("miho_current_user_message", default="")


def begin_turn_context(task_id: str) -> str:
    token = f"{task_id or 'turn'}:{uuid.uuid4().hex}"
    _CURRENT_TURN_TOKEN.set(token)
    _CURRENT_USER_MESSAGE.set("")
    return token


def set_current_user_message(message: str) -> None:
    _CURRENT_USER_MESSAGE.set(str(message or ""))


def current_turn_token() -> str:
    return _CURRENT_TURN_TOKEN.get("")


def current_user_message() -> str:
    return _CURRENT_USER_MESSAGE.get("")
