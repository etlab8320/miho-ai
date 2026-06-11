"""Runtime guard for premium hakjong report delivery contracts."""

from __future__ import annotations

import json
from typing import Any

from .context import REQUEST_TEXT


_PACKAGE_TOOL = "academy_hakjong_report_package"
_SEND_TOOL = "send_message"
_POST_PACKAGE_ALLOWED_TOOLS = {_PACKAGE_TOOL, _SEND_TOOL}
_STRICT_ROUTE_ALLOWED_TOOLS = {
    _PACKAGE_TOOL,
    _SEND_TOOL,
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
    key = _state_key(session_id=session_id, task_id=task_id)
    if not key:
        return
    payload = _result_payload(result)
    if payload.get("ok") is not True:
        return
    media_tag = str(payload.get("media_tag") or "")
    if not media_tag.startswith("MEDIA:"):
        return
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
    if _is_strict_hakjong_report_route(args) and name not in _STRICT_ROUTE_ALLOWED_TOOLS:
        return _block_message(
            "이 턴은 프리미엄 학종 리포트 계약이 걸려 있어. "
            "임의 파일검색, 세션검색, 터미널, 코드 실행으로 만들지 말고 "
            "생기부 근거 도구와 `academy_hakjong_report_package` 검증 계약만 사용해."
        )
    return None


def _reset_hakjong_report_package_state() -> None:
    _PACKAGE_DONE_BY_KEY.clear()


def _state_key(*, session_id: str = "", task_id: str = "") -> str:
    session = str(session_id or "").strip()
    task = str(task_id or "").strip()
    if session:
        return f"session:{session}"
    if task:
        return f"task:{task}"
    return ""


def _has_packaged_report(*, session_id: str = "", task_id: str = "") -> bool:
    key = _state_key(session_id=session_id, task_id=task_id)
    return bool(key and key in _PACKAGE_DONE_BY_KEY)


def _is_strict_hakjong_report_route(args: Any) -> bool:
    text = _context_text(args)
    return any(marker.casefold() in text for marker in _REQUIRED_ROUTE_MARKERS)


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
