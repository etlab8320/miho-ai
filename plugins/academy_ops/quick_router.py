"""Fast academy request routing before the general LLM loop."""

from __future__ import annotations

from .catalog import find_operation


def quick_command_for(text: str) -> str:
    clean = " ".join(text.strip().split())
    if not clean or clean.startswith("/"):
        return ""
    operation_key = classify_quick_operation(clean)
    if operation_key == "staff.attendance_day":
        return f"/academy quick staff.attendance_day {clean}"
    return ""


def classify_quick_operation(text: str) -> str:
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


def _tokens(text: str) -> set[str]:
    normalized = text.replace("/", " ").replace("_", " ").replace("-", " ")
    words = {word.strip(".,!?()[]{}") for word in normalized.split()}
    compact = "".join(normalized.split())
    if "강사" in compact:
        words.add("강사")
    if "출근" in compact:
        words.add("출근")
    if "누구" in compact:
        words.add("누구")
    if "누가" in compact:
        words.add("누구")
    return {word for word in words if word}
