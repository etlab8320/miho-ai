"""Korean user-facing formatting for academy operations."""

from __future__ import annotations

from .catalog import OperationSpec, grouped_operations
from .intent import IntentDraft


def format_catalog() -> str:
    lines = [
        "PACA/Peak 디스코드 운영 기능",
        "",
        "현재 실제 연결된 건 PACA/Peak 로그인 바인딩이야.",
        "아래 목록은 학생 카드와 운영 자동화에 필요한 연동 후보라서, 실제 PACA/Peak route 확인 후 붙여야 해.",
    ]
    for domain, ops in grouped_operations().items():
        titles = ", ".join(_title(op) for op in ops)
        lines.append(f"- {domain}: {titles}")
    lines.extend(
        [
            "",
            "쓰기 작업은 확인 버튼과 감사 로그가 붙기 전까지 실행하지 않아.",
        ]
    )
    return "\n".join(lines)


def format_intent_preview(draft: IntentDraft) -> str:
    op = draft.operation
    if op is None:
        return "요청을 처리할 기능을 찾지 못했어."

    lines = [
        draft.message,
        "",
        f"- 기능: {op.title}",
        f"- 모드: {'쓰기' if op.mode == 'write' else '읽기'}",
        f"- 구현 상태: {_status_label(op.implementation_status)}",
        f"- API 계약: {_contract_label(op.api_contract_status)}",
        f"- 후보 API: {op.endpoint.service} {op.endpoint.method} {op.endpoint.path}",
    ]
    if op.requires_confirmation:
        lines.append("- 확인: 디스코드 버튼 승인 필요")
    if op.requires_audit_log:
        lines.append("- 로그: 감사 로그 필요")
    lines.append(f"- 새 API 필요: {_needs_api_label(op.needs_new_backend_api)}")
    return "\n".join(lines)


def format_login_link(url: str, expires_minutes: int, *, is_local: bool) -> str:
    lines = [
        "학원 계정 연결 링크를 만들었어.",
        "",
        url,
        "",
        f"{expires_minutes}분 안에 열어서 PACA/Peak 계정으로 로그인하면 돼.",
    ]
    if is_local:
        lines.append("지금 링크는 로컬 개발용이라 다른 기기에서는 안 열릴 수 있어.")
    return "\n".join(lines)


def format_binding_status(name: str, academy_name: str, role: str) -> str:
    return f"연결됨: {name} / {academy_name} / {role}"


def _title(op: OperationSpec) -> str:
    suffix = " 확인필수" if op.requires_confirmation else ""
    return f"{op.title}{suffix}"


def _status_label(status: str) -> str:
    if status == "implemented":
        return "연결됨"
    if status == "planned":
        return "연동 후보"
    return status


def _contract_label(status: str) -> str:
    if status == "verified_in_plugin":
        return "플러그인에서 확인됨"
    if status == "unverified":
        return "백엔드 확인 필요"
    return status


def _needs_api_label(value: bool | None) -> str:
    if value is True:
        return "예"
    if value is False:
        return "아니오"
    return "백엔드 route 확인 전 판단 불가"
