"""Tests for local academy consultation-note tools."""

from __future__ import annotations

import json
from datetime import date

from plugins.academy_ops.consultation_notes import ConsultationNoteRepository
from plugins.academy_ops.consultation_notes_tool import (
    _consultation_note_save_tool_handler,
    attach_recent_consultation_notes,
)
from plugins.academy_ops.student_card import AcademyStudentCardService
from plugins.academy_ops.student_card_template import render_student_card_html
from tests.plugins.test_academy_student_card import FakeAcademyClient


def test_consultation_note_tool_saves_local_student_note(tmp_path) -> None:
    repo = ConsultationNoteRepository(tmp_path / "notes.sqlite3")

    output = _consultation_note_save_tool_handler(
        {
            "student_query": "김민준",
            "note": "금요일 결석 사유 확인. 다음 수업 전 컨디션 체크.",
            "consulted_at": "2026-05-25",
        },
        client=FakeAcademyClient(),
        repo=repo,
        academy_id="academy-1",
        discord_user_id="discord-user-1",
    )
    payload = json.loads(output)

    assert payload["ok"] is True
    assert payload["operation"] == "consultation.note_save"
    assert payload["note"]["student_name"] == "김민준"
    assert payload["note"]["paca_student_id"] == "101"
    assert "금요일 결석 사유" in payload["note"]["note"]


def test_student_card_includes_recent_consultation_notes(tmp_path) -> None:
    repo = ConsultationNoteRepository(tmp_path / "notes.sqlite3")
    repo.add_note(
        discord_user_id="discord-user-1",
        academy_id="academy-1",
        paca_student_id=101,
        student_name="김민준",
        note="부모 상담 후 금요일 등원 루틴 확인하기.",
        consulted_at="2026-05-24",
    )
    card = AcademyStudentCardService(FakeAcademyClient()).build(
        "김민준",
        today=date(2026, 5, 25),
        period_days=3,
    )

    card = attach_recent_consultation_notes(card, academy_id="academy-1", repo=repo)
    html = render_student_card_html(card)

    assert "상담 기록" in html
    assert "부모 상담 후 금요일 등원 루틴 확인하기." in html
    assert card.to_public_dict()["consultation_notes"][0]["student_name"] == "김민준"
