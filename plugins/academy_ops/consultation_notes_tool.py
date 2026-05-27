"""Tool handlers for local academy consultation notes."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
import os
from typing import Any

from .academy_api import AcademyApiClient, AcademyApiError
from .auth_store import decrypt_token, get_binding
from .consultation_notes import ConsultationNoteRepository
from .context import current_discord_user_id
from .paca_client import DEFAULT_PACA_BASE_URL
from .response_guidance import academy_response_guidance
from .student_card import AcademyClient, AcademyStudentCardService, StudentCardError


def _consultation_note_save_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    student_query = str(payload.get("student_query") or "").strip()
    note = str(payload.get("note") or "").strip()
    consulted_at = str(payload.get("consulted_at") or "").strip() or None
    if not student_query:
        return _json_error("상담 기록을 남길 학생 이름을 알려줘.")
    if not note:
        return _json_error("저장할 상담 내용을 알려줘.")

    runtime = _runtime(kwargs)
    if not runtime["ok"]:
        return _json_error(str(runtime["message"]))

    try:
        card = AcademyStudentCardService(runtime["client"]).build(
            student_query,
            today=_date_arg(consulted_at),
            period_days=14,
        )
        saved = runtime["repo"].add_note(
            discord_user_id=runtime["discord_user_id"],
            academy_id=runtime["academy_id"],
            paca_student_id=card.profile.paca_student_id,
            student_name=card.profile.name,
            note=note,
            consulted_at=consulted_at,
        )
    except (AcademyApiError, StudentCardError, ValueError) as exc:
        return _json_error(str(exc))

    message = f"{card.profile.name} 상담 기록 저장했어. 다음 학생카드부터 최근 상담 기록에 같이 보여줄게."
    return json.dumps(
        {
            "ok": True,
            "operation": "consultation.note_save",
            "message": message,
            "note": saved.to_public_dict(),
            "assistant_guidance": academy_response_guidance(),
        },
        ensure_ascii=False,
    )


def attach_recent_consultation_notes(
    card: Any,
    *,
    academy_id: str,
    repo: ConsultationNoteRepository | None = None,
) -> Any:
    notes = (repo or ConsultationNoteRepository()).recent_notes(
        academy_id=academy_id,
        paca_student_id=card.profile.paca_student_id,
        limit=3,
    )
    return replace(card, consultation_notes=notes)


def register_consultation_note_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_consultation_note_save",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_query": {"type": "string", "description": "학생 이름, 부분 이름, 또는 PACA 검색어."},
                "note": {"type": "string", "description": "저장할 상담 기록 본문."},
                "consulted_at": {"type": "string", "description": "상담일. YYYY-MM-DD 형식."},
            },
            "required": ["student_query", "note"],
            "additionalProperties": False,
        },
        handler=_consultation_note_save_tool_handler,
        description=(
            "Save a local academy consultation note for one student after the user asks to record 상담 기록. "
            "This is not long-term memory and does not write to PACA/Peak. "
            "Resolve the student through PACA first and store only the note text, date, academy id, and student id."
        ),
    )


def _runtime(kwargs: dict[str, Any]) -> dict[str, Any]:
    if kwargs.get("client") is not None:
        return {
            "ok": True,
            "client": kwargs["client"],
            "repo": kwargs.get("repo") or ConsultationNoteRepository(),
            "discord_user_id": str(kwargs.get("discord_user_id") or "test-user"),
            "academy_id": str(kwargs.get("academy_id") or "test-academy"),
        }
    discord_user_id = current_discord_user_id()
    if not discord_user_id:
        return {"ok": False, "message": "디스코드 사용자 정보를 확인하지 못했어. 디스코드에서 다시 요청해줘."}
    binding = get_binding(discord_user_id)
    if binding is None:
        return {"ok": False, "message": "학원 계정 연결이 필요해. `/academy login`으로 먼저 연결해줘."}
    token = decrypt_token(binding.token_ciphertext) or ""
    if not token:
        return {"ok": False, "message": "학원 계정 연결을 복호화하지 못했어. `/academy login`으로 다시 연결해줘."}
    client = AcademyApiClient(token=token, base_url=os.getenv("MIHO_ACADEMY_PACA_BASE_URL", DEFAULT_PACA_BASE_URL))
    return {
        "ok": True,
        "client": _typed_client(client),
        "repo": kwargs.get("repo") or ConsultationNoteRepository(),
        "discord_user_id": discord_user_id,
        "academy_id": binding.academy_id,
    }


def _typed_client(client: Any) -> AcademyClient:
    return client


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


def _date_arg(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
