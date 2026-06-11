"""Runtime guard for premium hakjong report delivery contracts."""

from __future__ import annotations

import json
from typing import Any

from .context import CHANNEL_ID, REQUEST_TEXT


_PACKAGE_TOOL = "academy_hakjong_report_package"
_SEND_TOOL = "send_message"
_DEFAULT_TASK_IDS = {"", "default"}
_POST_PACKAGE_ALLOWED_TOOLS = {_PACKAGE_TOOL, _SEND_TOOL}
_REPORT_ARTIFACT_TOOLS = {
    "write_file",
    "read_file",
    "terminal",
    "academy_render_image",
    "browser_navigate",
    "browser_take_screenshot",
    "browser_snapshot",
    "browser_evaluate",
}
_READ_ONLY_EVIDENCE_TOOLS = {
    "skill_view",
    "academy_student_context",
    "academy_student_summary",
    "academy_student_record_lookup",
    "academy_student_record_cohort_latest",
}
_STRICT_ROUTE_ALLOWED_TOOLS = {
    _PACKAGE_TOOL,
    _SEND_TOOL,
    *_REPORT_ARTIFACT_TOOLS,
    *_READ_ONLY_EVIDENCE_TOOLS,
    "life_record_lookup",
    "life_record_search",
    "life_record_summary",
}
_REQUIRED_ROUTE_MARKERS = (
    "required_tool=academy_hakjong_report_package",
    "required_tool:academy_hakjong_report_package",
    "`academy_hakjong_report_package`",
)
_PACKAGE_DONE_BY_KEY: dict[str, str] = {}
_STRICT_ROUTE_KEYS: set[str] = set()


def mark_hakjong_report_required_route(event: Any = None, *, required_tool: str = "") -> None:
    """Persist a decision-twin package contract for the current gateway source."""
    if str(required_tool or "").strip() != _PACKAGE_TOOL:
        return
    _STRICT_ROUTE_KEYS.update(_event_keys(event))


def _track_hakjong_report_package_result(
    tool_name: Any = None,
    result: Any = None,
    task_id: str = "",
    session_id: str = "",
    **_: Any,
) -> None:
    """Remember successful premium-report packaging for later tool blocking."""
    if str(tool_name or "").strip() != _PACKAGE_TOOL:
        return
    payload = _result_payload(result)
    if payload.get("ok") is not True:
        return
    media_tag = str(payload.get("media_tag") or "")
    if not media_tag.startswith("MEDIA:"):
        return
    for key in _runtime_keys(session_id=session_id, task_id=task_id):
        _PACKAGE_DONE_BY_KEY[key] = media_tag


def _block_after_hakjong_report_package(
    tool_name: Any = None,
    args: Any = None,
    task_id: str = "",
    session_id: str = "",
    **_: Any,
) -> dict[str, str] | None:
    """Force premium hakjong report turns to finish through the package tool."""
    name = str(tool_name or "").strip()
    if not name:
        return None
    if _has_packaged_report(session_id=session_id, task_id=task_id):
        if name in _POST_PACKAGE_ALLOWED_TOOLS:
            return None
        return _block_message(
            "프리미엄 학종 리포트 검증·패키징이 이미 통과했어. "
            "추가 파일검색, 세션검색, 터미널, 코드 실행으로 우회하지 말고 "
            "`academy_hakjong_report_package`가 반환한 MEDIA 파일을 바로 전달해."
        )
    if _is_strict_hakjong_report_route(args, session_id=session_id, task_id=task_id) and (
        name not in _STRICT_ROUTE_ALLOWED_TOOLS
    ):
        return _block_message(
            "이 턴은 프리미엄 학종 리포트 계약이 걸려 있어. "
            "세션검색, 일반 파일검색, 코드 실행으로 우회하지 말고 "
            "생기부 근거 도구, 리포트 산출물 생성, `academy_hakjong_report_package` 검증 계약만 사용해."
        )
    return None


def _reset_hakjong_report_package_state() -> None:
    _PACKAGE_DONE_BY_KEY.clear()
    _STRICT_ROUTE_KEYS.clear()


def _state_keys(*, session_id: str = "", task_id: str = "", message_id: str = "") -> set[str]:
    keys: set[str] = set()
    session = str(session_id or "").strip()
    task = str(task_id or "").strip()
    message = str(message_id or "").strip()
    if message:
        keys.add(f"message:{message}")
        if session:
            keys.add(f"session:{session}:message:{message}")
        if task and task not in _DEFAULT_TASK_IDS:
            keys.add(f"task:{task}:message:{message}")
        return keys
    if session:
        keys.add(f"session:{session}")
    if task and task not in _DEFAULT_TASK_IDS:
        keys.add(f"task:{task}")
    return keys


def _has_packaged_report(*, session_id: str = "", task_id: str = "") -> bool:
    return any(key in _PACKAGE_DONE_BY_KEY for key in _runtime_keys(session_id=session_id, task_id=task_id))


def _is_strict_hakjong_report_route(args: Any, *, session_id: str = "", task_id: str = "") -> bool:
    if any(key in _STRICT_ROUTE_KEYS for key in _runtime_keys(session_id=session_id, task_id=task_id)):
        return True
    text = _context_text(args)
    return any(marker.casefold() in text for marker in _REQUIRED_ROUTE_MARKERS)


def _runtime_keys(*, session_id: str = "", task_id: str = "") -> set[str]:
    message_id = _session_context_value("MIHO_SESSION_MESSAGE_ID")
    if message_id:
        keys = _state_keys(session_id=session_id, task_id=task_id, message_id=message_id)
        keys.update(_session_context_keys(message_id=message_id))
        channel_id = CHANNEL_ID.get().strip()
        if channel_id:
            keys.add(f"chat:{channel_id}:message:{message_id}")
        return keys
    keys = _state_keys(session_id=session_id, task_id=task_id)
    keys.update(_session_context_keys())
    channel_id = CHANNEL_ID.get().strip()
    if channel_id:
        keys.add(f"chat:{channel_id}")
    return keys


def _session_context_keys(*, message_id: str = "") -> set[str]:
    scoped_message = str(message_id or "").strip()
    env_keys = (
        ("MIHO_SESSION_KEY", "session_key"),
        ("MIHO_SESSION_CHAT_ID", "chat"),
        ("MIHO_SESSION_THREAD_ID", "thread"),
    )
    if scoped_message:
        keys: set[str] = set()
        for env_name, prefix in env_keys:
            value = _session_context_value(env_name)
            if value:
                keys.add(f"{prefix}:{value}:message:{scoped_message}")
        return keys
    keys: set[str] = set()
    for env_name, prefix in env_keys:
        value = _session_context_value(env_name)
        if value:
            keys.add(f"{prefix}:{value}")
    return keys


def _session_context_value(env_name: str) -> str:
    try:
        from gateway.session_context import get_session_env
    except Exception:
        return ""
    return str(get_session_env(env_name) or "").strip()


def _event_keys(event: Any = None) -> set[str]:
    source = getattr(event, "source", None)
    message_id = _event_message_id(event, source)
    keys: set[str] = set()
    if message_id:
        keys.add(f"message:{message_id}")
        for attr, prefix in (
            ("session_key", "session_key"),
            ("chat_id", "chat"),
            ("thread_id", "thread"),
            ("parent_chat_id", "chat"),
        ):
            value = str(getattr(source, attr, "") or "").strip()
            if value:
                keys.add(f"{prefix}:{value}:message:{message_id}")
        return keys
    for attr, prefix in (
        ("session_key", "session_key"),
        ("chat_id", "chat"),
        ("thread_id", "thread"),
        ("parent_chat_id", "chat"),
    ):
        value = str(getattr(source, attr, "") or "").strip()
        if value:
            keys.add(f"{prefix}:{value}")
    return keys


def _event_message_id(event: Any = None, source: Any = None) -> str:
    for target in (event, source):
        value = str(getattr(target, "message_id", "") or "").strip()
        if value:
            return value
    return ""


def _context_text(args: Any) -> str:
    values = [REQUEST_TEXT.get()]
    try:
        values.append(json.dumps(args or {}, ensure_ascii=False))
    except (TypeError, ValueError):
        values.append("")
    return "\n".join(str(value or "") for value in values).casefold()


def _result_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _block_message(message: str) -> dict[str, str]:
    return {"action": "block", "message": message}
