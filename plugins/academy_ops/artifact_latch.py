"""Current-turn latch for reviewed academy PDF artifacts."""

from __future__ import annotations

import json
import re
import threading
from collections import OrderedDict
from typing import Any

from agent.turn_context import current_turn_token


_LOCK = threading.RLock()
_TURN_RESULTS: OrderedDict[str, dict[tuple[str, ...], str]] = OrderedDict()
_MAX_TURNS = 32
_PDF_TOOLS = {
    "academy_hakjong_report_package",
    "academy_practical_reco_package",
    "academy_practical_reco_all_candidates",
}


def current_turn_reviewed_artifact(tool_name: str, args: Any) -> str:
    turn_token = current_turn_token()
    key = artifact_fingerprint(tool_name, args)
    if not turn_token or not key:
        return ""
    with _LOCK:
        turn_results = _TURN_RESULTS.get(turn_token) or {}
        return turn_results.get(key, "")


def remember_reviewed_artifact(tool_name: str, args: Any, payload: dict[str, Any]) -> None:
    if not _is_reviewed_artifact(tool_name, payload):
        return
    turn_token = current_turn_token()
    key = artifact_fingerprint(tool_name, args, payload=payload)
    if not turn_token or not key:
        return
    with _LOCK:
        turn_results = _TURN_RESULTS.setdefault(turn_token, {})
        turn_results[key] = json.dumps(payload, ensure_ascii=False)
        _TURN_RESULTS.move_to_end(turn_token)
        while len(_TURN_RESULTS) > _MAX_TURNS:
            _TURN_RESULTS.popitem(last=False)


def artifact_fingerprint(tool_name: str, args: Any, *, payload: dict[str, Any] | None = None) -> tuple[str, ...]:
    name = str(tool_name or "").strip()
    if name not in _PDF_TOOLS:
        return ()
    arg_obj = args if isinstance(args, dict) else {}
    content = _object_from_json(arg_obj.get("content"))
    if name == "academy_hakjong_report_package":
        return _hakjong_key(name, arg_obj, content, payload)
    if name == "academy_practical_reco_package":
        return _practical_key(name, arg_obj, content, payload)
    return _all_candidates_key(name, arg_obj, payload)


def _is_reviewed_artifact(tool_name: str, payload: dict[str, Any]) -> bool:
    if str(tool_name or "").strip() not in _PDF_TOOLS or payload.get("ok") is not True:
        return False
    reviewer = payload.get("reviewer")
    if not isinstance(reviewer, dict) or reviewer.get("status") != "pass":
        return False
    return bool(str(payload.get("file_path") or "").strip() and str(payload.get("media_tag") or "").strip())


def _hakjong_key(
    tool_name: str,
    args: dict[str, Any],
    content: dict[str, Any],
    payload: dict[str, Any] | None,
) -> tuple[str, ...]:
    university = content.get("university") if isinstance(content.get("university"), dict) else {}
    manifest = _manifest_hint(payload)
    names = manifest.get("university_names") if isinstance(manifest.get("university_names"), list) else []
    university_name = _norm(university.get("name") or (names[0] if names else ""))
    return (
        tool_name,
        _norm(args.get("student_name")),
        _norm(args.get("student_stage") or manifest.get("student_stage")),
        university_name,
        _norm(university.get("department")),
        _norm(university.get("track")),
    )


def _practical_key(
    tool_name: str,
    args: dict[str, Any],
    content: dict[str, Any],
    payload: dict[str, Any] | None,
) -> tuple[str, ...]:
    manifest = _manifest_hint(payload)
    rows = _comparison_rows(content)
    schools = "|".join(_norm(row.get("school")) for row in rows)
    tracks = "|".join(_norm(row.get("track")) for row in rows)
    if not schools:
        names = manifest.get("school_names") if isinstance(manifest.get("school_names"), list) else []
        schools = "|".join(_norm(name) for name in names)
    return (tool_name, _norm(args.get("student_name") or manifest.get("student_name")), schools, tracks)


def _all_candidates_key(
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any] | None,
) -> tuple[str, ...]:
    manifest = _manifest_hint(payload)
    return (
        tool_name,
        _norm(args.get("student_name") or manifest.get("student_name")),
        _norm(args.get("region") or manifest.get("region")),
    )


def _comparison_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    comparison = content.get("comparison") if isinstance(content.get("comparison"), dict) else {}
    rows = comparison.get("rows") if isinstance(comparison.get("rows"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _object_from_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _manifest_hint(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    path = str(payload.get("manifest_path") or "").strip()
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            parsed = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())
