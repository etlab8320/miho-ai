"""PACA expense write tools for academy operations."""

from __future__ import annotations

from datetime import date
import re
from typing import Any

from .academy_api import AcademyApiError
from .academy_query_tools import _date_arg, _json_error, _json_ok, _resolve_client


AMOUNT_PATTERN = re.compile(r"(?P<amount>\d[\d,]*)\s*원?")
DATE_PATTERN = re.compile(
    r"(?P<year>\d{4})[-./](?P<month>\d{1,2})[-./](?P<day>\d{1,2})"
    r"|(?P<short_month>\d{1,2})[./](?P<short_day>\d{1,2})"
)
# 파카(pacapro) 지출 등록 폼 select 옵션과 1:1 — 미호도 이 코드로만 저장한다.
EXPENSE_CATEGORIES = (
    "utilities",   # 공과금
    "rent",        # 임대료
    "supplies",    # 소모품
    "marketing",   # 홍보비
    "salary",      # 급여
    "refund",      # 환불
    "other",       # 기타
)


def register_expense_tools(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_expense_create",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["utilities", "rent", "supplies", "marketing", "salary", "refund", "other"],
                    "description": (
                        "파카 지출 카테고리 코드. 지출 내용을 보고 네가 직접 가장 알맞은 코드를 골라라: "
                        "utilities(공과금·전기·수도·가스·인터넷·관리비), rent(임대료·월세·임차료), "
                        "supplies(소모품·비품·교재·문구·간식 등 구입 물품), marketing(홍보비·광고·마케팅), "
                        "salary(급여·인건비), refund(환불), other(위 어디에도 딱 맞지 않으면 기타). 생략하면 other."
                    ),
                },
                "amount": {"type": "integer", "minimum": 1, "description": "원 단위 지출 금액."},
                "description": {
                    "type": "string",
                    "description": (
                        "지출 내용을 한글로 짧고 자연스럽게 적어라. 예: '6월 전기요금', '학생 간식 구입', "
                        "'체육관 임대료', '교재 구입'. 사용자가 말한 표현을 살려서 작성하고, "
                        "카테고리 코드(영어)나 사용자 원문 전체를 그대로 넣지 마라."
                    ),
                },
                "date": {"type": "string", "description": "지출일. YYYY-MM-DD 형식. 생략하면 오늘."},
                "today": {"type": "string", "description": "기준일. YYYY-MM-DD 형식."},
                "request": {"type": "string", "description": "사용자 원문. 빠른 라우팅 보정용."},
            },
            "required": ["amount"],
            "additionalProperties": False,
        },
        handler=_expense_create_tool_handler,
        description=(
            "Create one PACA expense row. Use only for explicit 지출 등록/기록/추가 requests. "
            "Requires amount; category/description/date are normalized before calling PACA."
        ),
    )


def _expense_create_tool_handler(args: dict[str, Any] | None = None, *, client: Any = None, **_: Any) -> str:
    payload = dict(args or {})
    request = str(payload.get("request") or "").strip()
    amount = _amount_value(payload.get("amount")) or _amount_from_request(request)
    if amount is None:
        return _json_error("지출 금액을 원 단위로 알려줘. 예: 교재비 1000원 지출 등록")
    category = _category_value(payload.get("category"))
    expense_date = _expense_date(payload, request)
    if expense_date is None:
        return _json_error("지출일을 YYYY-MM-DD 형식으로 알려줘.")
    description = _description_value(payload.get("description"), request, category, amount)
    resolved = _resolve_client(client)
    if isinstance(resolved, str):
        return _json_error(resolved)
    try:
        created = resolved.create_paca_expense(
            category=category,
            amount=amount,
            description=description,
            expense_date=expense_date,
        )
    except AcademyApiError as exc:
        return _json_error(f"지출 등록을 완료하지 못했어: {exc}")
    expense = _safe_expense(created, category=category, amount=amount, description=description, day=expense_date)
    return _json_ok(
        {
            "operation": "expense.create",
            "write_enabled": True,
            "write_executed": True,
            "expense": expense,
            "message": _expense_message(expense),
        }
    )


def _amount_value(value: Any) -> int | None:
    try:
        amount = int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def _amount_from_request(request: str) -> int | None:
    match = AMOUNT_PATTERN.search(request)
    return _amount_value(match.group("amount")) if match else None


def _category_value(value: Any) -> str:
    # LLM이 schema enum에서 고른 파카 코드를 그대로 쓴다. 키워드 하드코딩 매핑 없음.
    direct = str(value or "").strip().lower()
    return direct if direct in EXPENSE_CATEGORIES else "other"


def _expense_date(payload: dict[str, Any], request: str) -> date | None:
    explicit = _date_arg(payload.get("date"))
    if explicit:
        return explicit
    parsed = _date_from_request(request, _date_arg(payload.get("today")))
    if parsed:
        return parsed
    return _date_arg(payload.get("today")) or date.today()


def _date_from_request(request: str, today: date | None) -> date | None:
    match = DATE_PATTERN.search(request)
    if not match:
        return None
    if match.group("year"):
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))
    else:
        year = today.year if today else date.today().year
        month = int(match.group("short_month"))
        day = int(match.group("short_day"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _description_value(value: Any, request: str, category: str, amount: int) -> str:
    # LLM이 schema 안내대로 한글로 짧게 채운다. 미지정 시 빈 값(영어 코드/원문 노출 금지).
    return str(value or "").strip()


def _safe_expense(
    row: dict[str, Any],
    *,
    category: str,
    amount: int,
    description: str,
    day: date,
) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "category": str(row.get("category") or category),
        "amount": _amount_value(row.get("amount")) or amount,
        "description": str(row.get("description") or description),
        "date": str(row.get("date") or day.isoformat())[:10],
        "created_at": str(row.get("created_at") or "")[:19],
    }


def _expense_message(expense: dict[str, Any]) -> str:
    return (
        f"지출 등록 완료: {expense['date']} {expense['category']} "
        f"{int(expense['amount']):,}원"
    )
