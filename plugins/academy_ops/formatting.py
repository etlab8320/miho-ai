"""Korean user-facing formatting for academy operations."""

from __future__ import annotations

from .catalog import OperationSpec, grouped_operations
from .intent import IntentDraft


def format_catalog() -> str:
    lines = [
        "PACA/Peak 디스코드 운영 기능",
        "",
        "새 PACA/Peak API를 먼저 만들 필요는 거의 없어. 1차는 기존 API를 안전하게 연결해.",
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
        f"- 기존 API: {op.endpoint.service} {op.endpoint.method} {op.endpoint.path}",
    ]
    if op.requires_confirmation:
        lines.append("- 확인: 디스코드 버튼 승인 필요")
    if op.requires_audit_log:
        lines.append("- 로그: 감사 로그 필요")
    lines.append(f"- 새 API 필요: {'예' if op.needs_new_backend_api else '아니오'}")
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


def format_login_button_prompt(expires_minutes: int, *, is_local: bool) -> str:
    lines = [
        "학원관리 연결부터 할게.",
        "",
        "PACA랑 Peak은 같은 로그인 토큰을 써서 한 번만 연결하면 둘 다 쓸 수 있어.",
        f"아래 버튼으로 로그인해줘. 링크는 {expires_minutes}분 동안 유효해.",
    ]
    if is_local:
        lines.append("지금 링크는 로컬 개발용이라 다른 기기에서는 안 열릴 수 있어.")
    return "\n".join(lines)


def format_binding_status(name: str, academy_name: str, role: str) -> str:
    return f"연결됨: {name} / {academy_name} / {role}"


def _title(op: OperationSpec) -> str:
    suffix = " 확인필수" if op.requires_confirmation else ""
    return f"{op.title}{suffix}"
