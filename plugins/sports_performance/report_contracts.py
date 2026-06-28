"""Runtime contracts for sports performance report artifacts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_NUMBER_PATTERN = re.compile(r"\d")
_BLOCKED_MODEL_MARKERS = (
    "미연동",
    "측정 대기",
    "계산 대기",
    "산출 대기",
    "모델 대기",
    "계산 불가",
    "재계산 필요",
    "재실행 필요",
    "재조회 필요",
    "판정 보류",
)


def allow_placeholders(args: dict[str, Any]) -> bool:
    mode = str(args.get("mode") or "").strip()
    return args.get("allow_placeholders") is True or mode in {"template_preview", "preview"}


def runtime_report_contract(args: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if allow_placeholders(args):
        return {"ok": True}
    failures: list[str] = []
    if not _has_measured_variables(payload):
        failures.append("실제 변인 숫자가 없습니다.")
    if not _has_reviewed_feedback(args):
        failures.append("운동 피드백 검수 통과 정보가 없습니다.")
    if missing := _missing_elite_model_variables(payload):
        failures.append(f"전국 성별 상위 1% 모델값이 없는 변인이 있습니다: {', '.join(missing[:5])}")
    if not _has_valid_comparison(payload):
        failures.append("전국 성별 상위 1% 비교 모델이 없습니다.")
    if _has_blocked_model_text((payload.get("record") or {}).get("percentile")):
        failures.append("전국 모델 요약값이 없습니다.")
    if not failures:
        return {"ok": True}
    return {
        "ok": False,
        "success": False,
        "delivery_status": "blocked",
        "next_action": "run_sports_motion_report_package",
        "errors": failures,
        "assistant_instruction": (
            "MAX API에서 학생 최신 변인과 전국 성별 상위 1% 모델을 함께 조회하고, "
            "sports_motion_feedback reviewer pass 뒤 sports_motion_report_package로 다시 생성한다."
        ),
        "user_safe_message": "전국 상위 모델 비교값이 없어 리포트 생성을 막았습니다.",
    }


def html_model_contract_error(html_path: str) -> str:
    text_path = Path(str(html_path or ""))
    if not text_path.exists():
        return "운동분석 HTML 산출물 파일을 확인하지 못했습니다."
    try:
        html = text_path.read_text(encoding="utf-8")
    except OSError:
        return "운동분석 HTML 산출물 파일을 읽지 못했습니다."
    if _has_blocked_model_text(html):
        return "전국 성별 상위 1% 모델값이 HTML에 없어 PDF 생성을 중단했습니다."
    return ""


def has_valid_model_value(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and _has_number(text) and not _has_blocked_model_text(text)


def _has_measured_variables(payload: dict[str, Any]) -> bool:
    for group in payload.get("variable_groups") or []:
        for variable in group.get("variables") or []:
            if _has_number(str(variable.get("current") or "")):
                return True
    return False


def _has_reviewed_feedback(args: dict[str, Any]) -> bool:
    for key in ("feedback", "sports_motion_feedback", "motion_feedback"):
        value = args.get(key)
        if not isinstance(value, dict):
            continue
        reviewer = value.get("reviewer") if isinstance(value.get("reviewer"), dict) else {}
        if str(reviewer.get("status") or "").strip() == "pass":
            return True
    return False


def _missing_elite_model_variables(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for group in payload.get("variable_groups") or []:
        for variable in group.get("variables") or []:
            elite = variable.get("elite_1pct")
            gap = variable.get("gap")
            if has_valid_model_value(elite) and has_valid_model_value(gap):
                continue
            label = str(variable.get("display_name") or variable.get("name") or variable.get("key") or "").strip()
            missing.append(label or "unknown")
    return missing


def _has_valid_comparison(payload: dict[str, Any]) -> bool:
    for item in payload.get("comparison_summary") or []:
        label = str(item.get("label") or "")
        value = item.get("value")
        if "상위 1%" in label and has_valid_model_value(value):
            return True
    return False


def _has_blocked_model_text(value: Any) -> bool:
    text = str(value or "")
    return any(marker in text for marker in _BLOCKED_MODEL_MARKERS)


def _has_number(text: str) -> bool:
    return bool(_NUMBER_PATTERN.search(text))
