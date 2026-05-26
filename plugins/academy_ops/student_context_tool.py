"""Student context lookup tool for PACA/Peak follow-up questions."""

from __future__ import annotations

from datetime import date
from typing import Any

from .academy_api import AcademyApiError
from .academy_query_tools import _date_arg, _int_arg, _json_error, _json_ok, _resolve_client
from .response_guidance import academy_response_guidance


def _student_context_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    query = str(payload.get("student_query") or "").strip()
    if not query:
        return _json_error("학생 이름이나 검색어를 알려줘.")
    target_day = _date_arg(payload.get("today")) or date.today()
    period_days = _int_arg(payload.get("period_days"), default=14, maximum=60)
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        context = client_or_error.get_student_context(query, today=target_day, period_days=period_days)
    except AcademyApiError as exc:
        return _json_error(str(exc))
    return _json_ok(
        {
            "operation": "student.context",
            **context,
            "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
        }
    )
