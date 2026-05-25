"""Tests for the PACA/Peak student card image tool."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx
from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource

from plugins.academy_ops import _capture_gateway_context
from plugins.academy_ops.academy_api import AcademyApiClient
from plugins.academy_ops.student_card import (
    AcademyStudentCardService,
    RecordItem,
    StudentCardNotFoundError,
)
from plugins.academy_ops.student_card_template import render_student_card_html
from plugins.academy_ops.student_card_tool import _student_card_image_tool_handler


class FakeAcademyClient:
    def __init__(self) -> None:
        self.attendance_dates: list[str] = []

    def search_paca_students(self, query: str) -> list[dict]:
        if query == "없는학생":
            return []
        return [
            {
                "id": 101,
                "name": "김민준",
                "gender": "male",
                "school": "백마고",
                "grade": "고3",
                "status": "active",
                "weekly_count": 3,
                "time_slot": "evening",
                "phone": "010-1111-2222",
                "parent_phone": "010-3333-4444",
                "monthly_tuition": "500000",
                "discount_reason": "internal",
                "memo": "민감 메모",
            }
        ]

    def get_paca_student_detail(self, paca_student_id: int) -> dict:
        assert paca_student_id == 101
        return {
            "student": {
                "id": 101,
                "name": "김민준",
                "school": "백마고",
                "grade": "고3",
                "status": "active",
                "weekly_count": 3,
                "time_slot": "evening",
                "phone": "010-1111-2222",
                "monthly_tuition": "500000",
                "payments": [{"payment_status": "unpaid"}],
            },
            "payments": [{"payment_status": "unpaid"}],
        }

    def list_peak_students(self) -> list[dict]:
        return [
            {
                "id": 501,
                "paca_student_id": 101,
                "name": "김민준",
                "school": "백마고",
                "grade": "고3",
                "status": "active",
            }
        ]

    def get_peak_attendance(self, day: date) -> dict:
        self.attendance_dates.append(day.isoformat())
        status_by_day = {
            "2026-05-23": "absent",
            "2026-05-24": "late",
            "2026-05-25": "present",
        }
        status = status_by_day.get(day.isoformat())
        rows = []
        if status:
            rows.append({"student_id": 501, "attendance_status": status})
        return {"success": True, "date": day.isoformat(), "slots": {"evening": rows}}

    def list_peak_records(self, peak_student_id: int) -> list[dict]:
        assert peak_student_id == 501
        return [
            {
                "record_type_id": 1,
                "record_type_name": "제자리멀리뛰기",
                "measured_at": "2026-05-20",
                "value": "245",
                "unit": "cm",
                "direction": "higher",
            },
            {
                "record_type_id": 1,
                "record_type_name": "제자리멀리뛰기",
                "measured_at": "2026-05-15",
                "value": "241",
                "unit": "cm",
                "direction": "higher",
            },
            {
                "record_type_id": 1,
                "record_type_name": "제자리멀리뛰기",
                "measured_at": "2026-05-10",
                "value": "237",
                "unit": "cm",
                "direction": "higher",
            },
        ]


class FakeRenderer:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.cards: list[object] = []

    def render(self, card: object) -> Path:
        self.cards.append(card)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"png")
        return self.path


def test_student_card_service_maps_paca_to_peak_and_masks_sensitive_fields() -> None:
    client = FakeAcademyClient()
    service = AcademyStudentCardService(client)

    card = service.build("김민준", today=date(2026, 5, 25), period_days=3)
    payload = card.to_public_dict()

    assert payload["profile"]["paca_student_id"] == 101
    assert payload["profile"]["peak_student_id"] == 501
    assert payload["attendance"]["summary"] == {"present": 1, "late": 1, "absent": 1}
    assert payload["records"]["items"][0]["delta"] == 4.0
    assert payload["records"]["items"][0]["average"] == 241.0
    assert payload["records"]["items"][0]["samples"] == (237.0, 241.0, 245.0)
    assert payload["risk"]["level"] == "stable"
    assert "최근 출결 확인값 3건" in payload["risk"]["judgment"]
    assert "최근 기록 확인값 1종목" in payload["risk"]["judgment"]
    assert "리듬이 흔들" not in payload["risk"]["judgment"]

    dumped = json.dumps(payload, ensure_ascii=False)
    assert "010-" not in dumped
    assert "500000" not in dumped
    assert "discount" not in dumped
    assert "민감 메모" not in dumped


def test_student_card_html_is_rich_and_still_excludes_sensitive_fields() -> None:
    card = AcademyStudentCardService(FakeAcademyClient()).build(
        "김민준",
        today=date(2026, 5, 25),
        period_days=3,
    )

    html = render_student_card_html(card)

    assert "PACA / Peak 학생 운영 카드" in html
    assert "상담 포인트" in html
    assert "최근 기록" in html
    assert "PB" in html
    assert "AVG" in html
    assert "graph-bar" in html
    assert "결석일" in html
    assert "05.23 토" in html
    assert "다음 액션" in html
    assert "등원률" in html
    assert "고양덕양체" in html
    assert "010-" not in html
    assert "500000" not in html
    assert "discount" not in html
    assert "민감 메모" not in html


def test_student_card_html_limits_record_rows_to_prevent_footer_overlap() -> None:
    card = AcademyStudentCardService(FakeAcademyClient()).build(
        "김민준",
        today=date(2026, 5, 25),
        period_days=3,
    )
    records = [
        RecordItem(f"종목{i}", 100 + i, 110 + i, "점", i, "up", "2026-05-25")
        for i in range(1, 7)
    ]

    html = render_student_card_html(replace(card, records=records))

    assert "종목1" in html
    assert "종목3" in html
    assert "종목4" not in html
    assert "외 3개" in html
    assert "grid-template-rows: 246px 176px 292px 388px 46px" in html
    assert "overflow: hidden" in html


def test_student_card_judgment_band_keeps_long_copy_inside_card() -> None:
    card = AcademyStudentCardService(FakeAcademyClient()).build(
        "김민준",
        today=date(2026, 5, 25),
        period_days=14,
    )
    card = replace(
        card,
        risk=replace(
            card.risk,
            judgment=(
                "김민준은 최근 2주 출결과 기록 흐름을 같이 보면 안정 범위에 있지만, "
                "결석 1회와 지각 1회가 있어 다음 수업에서 컨디션과 등원 루틴만 "
                "짧게 확인하면 됩니다."
            ),
        ),
    )

    html = render_student_card_html(card)

    assert "grid-template-columns: 132px minmax(0, 1fr)" in html
    assert "align-items: center;" in html
    assert "font-size: 28px;" in html
    assert "text-wrap: pretty;" in html


def test_student_card_html_centers_attendance_metrics() -> None:
    card = AcademyStudentCardService(FakeAcademyClient()).build(
        "김민준",
        today=date(2026, 5, 25),
        period_days=3,
    )

    html = render_student_card_html(card)

    assert ".metric {" in html
    assert "display: grid;" in html
    assert "place-items: center;" in html
    assert "text-align: center;" in html


def test_student_card_service_defaults_attendance_window_to_two_weeks() -> None:
    client = FakeAcademyClient()
    service = AcademyStudentCardService(client)

    service.build("김민준", today=date(2026, 5, 25))

    assert len(client.attendance_dates) == 14
    assert client.attendance_dates[0] == "2026-05-12"
    assert client.attendance_dates[-1] == "2026-05-25"


def test_student_card_single_recent_absence_is_still_stable() -> None:
    client = FakeAcademyClient()
    service = AcademyStudentCardService(client)

    card = service.build("김민준", today=date(2026, 5, 25), period_days=14)

    assert card.attendance.summary == {"present": 1, "late": 1, "absent": 1}
    assert card.risk.level == "stable"
    assert "최근 출결 확인값" in card.risk.judgment
    assert "리듬이 흔들" not in card.risk.judgment
    assert card.risk.recommended_actions == ["결석 1회는 위험 신호가 아니라 참고 항목으로만 표시합니다."]
    assert "컨디션" not in " ".join(card.risk.recommended_actions)


def test_academy_api_client_parses_verified_route_shapes() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert request.headers["authorization"] == "Bearer token-123"
        if request.url.path == "/paca/students":
            return httpx.Response(200, json=[{"id": 101, "name": "김민준"}])
        if request.url.path == "/paca/students/101":
            return httpx.Response(200, json={"student": {"id": 101, "name": "김민준"}})
        if request.url.path == "/peak/students":
            return httpx.Response(200, json=[{"id": 501, "paca_student_id": 101}])
        if request.url.path == "/peak/attendance/students":
            return httpx.Response(200, json={"success": True, "slots": {"evening": []}})
        if request.url.path == "/peak/records":
            return httpx.Response(200, json={"success": True, "records": [{"id": 1}]})
        return httpx.Response(404)

    client = AcademyApiClient(
        token="token-123",
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )

    assert client.search_paca_students("김민준") == [{"id": 101, "name": "김민준"}]
    assert client.get_paca_student_detail(101)["student"]["id"] == 101
    assert client.list_peak_students() == [{"id": 501, "paca_student_id": 101}]
    assert client.get_peak_attendance(date(2026, 5, 25))["success"] is True
    assert client.list_peak_records(501) == [{"id": 1}]
    assert any("search=%EA%B9%80%EB%AF%BC%EC%A4%80" in url for url in seen)
    assert any("student_id=501" in url for url in seen)


def test_student_card_service_raises_plain_korean_when_student_missing() -> None:
    service = AcademyStudentCardService(FakeAcademyClient())

    with pytest.raises(StudentCardNotFoundError) as exc:
        service.build("없는학생", today=date(2026, 5, 25), period_days=3)

    assert str(exc.value) == "학생을 찾지 못했어. 이름이나 학교를 조금 더 정확히 알려줘."


def test_student_card_image_tool_returns_media_tag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "plugins.academy_ops.student_card_tool.get_binding",
        lambda user_id: SimpleNamespace(token_ciphertext="cipher", academy_name="일산 맥스체대입시"),
    )
    monkeypatch.setattr(
        "plugins.academy_ops.student_card_tool.decrypt_token",
        lambda ciphertext: "token-123",
    )
    _capture_gateway_context(
        MessageEvent(
            text="김민준 학생 카드 만들어줘",
            source=SessionSource(
                platform=Platform.DISCORD,
                user_id="discord-user-1",
                chat_id="channel-1",
                guild_id="guild-1",
            ),
        )
    )
    image_path = tmp_path / "student-card.png"

    output = _student_card_image_tool_handler(
        {"student_query": "김민준", "period_days": 3, "today": "2026-05-25"},
        client=FakeAcademyClient(),
        renderer=FakeRenderer(image_path),
    )
    payload = json.loads(output)

    assert payload["ok"] is True
    assert payload["image_path"] == str(image_path)
    assert payload["media_tag"] == f"MEDIA:{image_path}"
    assert f"MEDIA:{image_path}" in output
    assert "민감정보는 이미지에 넣지 않았어" in payload["message"]


def test_gateway_context_is_captured_for_non_slash_academy_tool_requests() -> None:
    event = MessageEvent(
        text="김민준 학생 카드 만들어줘",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-9",
            chat_id="channel-9",
            guild_id="guild-9",
        ),
    )

    assert _capture_gateway_context(event) == {"action": "allow"}

    output = _student_card_image_tool_handler(
        {"student_query": "김민준"},
        client=FakeAcademyClient(),
        renderer=FakeRenderer(Path("/tmp/student-card.png")),
    )

    assert json.loads(output)["ok"] is True
