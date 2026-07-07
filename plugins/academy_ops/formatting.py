"""Korean user-facing formatting for academy operations."""

from __future__ import annotations

from .catalog import CONNECTED_APIS, OperationSpec, grouped_operations


def format_catalog() -> str:
    lines = [
        "PACA/Peak 디스코드 운영 기능",
        "",
        "슬래시 메뉴는 로그인/상태/후보 기능 확인용이야.",
        "연결된 읽기 도구는 자연어로 물으면 미호가 맥락에 맞게 호출해.",
        "",
        "연결된 기능:",
        *[f"- {op.domain}: {op.title}" for op in CONNECTED_APIS],
        "",
        "연동 후보:",
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


def format_login_link(url: str, expires_minutes: int, *, is_local: bool) -> str:
    lines = [
        "학원 계정 연결 링크를 만들었어.",
        "",
        f"<{url}>",
        "",
        f"{expires_minutes}분 안에 열어서 PACA/Peak 계정으로 로그인하면 돼.",
        "방금 발급한 이 링크만 사용해줘. 이전 학원 계정 연결 링크는 무효야.",
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
