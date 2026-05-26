"""Fast academy request routing before the general LLM loop."""

from __future__ import annotations

import re

from .catalog import find_operation


def quick_command_for(text: str) -> str:
    clean = " ".join(text.strip().split())
    if not clean or clean.startswith("/"):
        return ""
    operation_key = classify_quick_operation(clean)
    if operation_key == "staff.attendance_day":
        return f"/academy quick staff.attendance_day {clean}"
    if operation_key == "plan.by_date":
        return f"/academy quick plan.by_date {clean}"
    return ""


def classify_quick_operation(text: str) -> str:
    plan_operation = find_operation("plan.by_date")
    if plan_operation is not None and _is_plan_request(text):
        return plan_operation.key
    operation = find_operation("staff.attendance_day")
    if operation is None:
        return ""
    tokens = _tokens(f"{operation.title} {operation.notes}")
    request_tokens = _tokens(text)
    if "출근" not in request_tokens:
        return ""
    score = len(tokens & request_tokens)
    if score >= 2 or {"누구", "출근"} <= request_tokens:
        return operation.key
    return ""


def _is_plan_request(text: str) -> bool:
    request_tokens = _tokens(text)
    if not ({"운동", "계획"} <= request_tokens or "운동계획" in request_tokens or "계획서" in request_tokens):
        return False
    return bool({"강사", "선생", "선생님", "쌤"} & request_tokens) or bool(_korean_names(text))


def _tokens(text: str) -> set[str]:
    normalized = text.replace("/", " ").replace("_", " ").replace("-", " ")
    words = {word.strip(".,!?()[]{}") for word in normalized.split()}
    compact = "".join(normalized.split())
    if "강사" in compact:
        words.add("강사")
    if "선생님" in compact:
        words.add("선생님")
    if "선생" in compact:
        words.add("선생")
    if "쌤" in compact:
        words.add("쌤")
    if "운동" in compact:
        words.add("운동")
    if "계획" in compact:
        words.add("계획")
    if "운동계획" in compact:
        words.add("운동계획")
    if "계획서" in compact:
        words.add("계획서")
    if "출근" in compact:
        words.add("출근")
    if "누구" in compact:
        words.add("누구")
    if "누가" in compact:
        words.add("누구")
    return {word for word in words if word}


def _korean_names(text: str) -> list[str]:
    return [match.group(1) for match in re.finditer(r"([가-힣]{2,5})\s*(?:운동\s*계획서?|계획서)", text)]
