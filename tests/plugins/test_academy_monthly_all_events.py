"""All-events (event_query 없음) full table image for monthly test records.

When the user asks for "전체 종목 표 이미지" with no specific event, the tool
must NOT ask which event — it renders every event × participant as one report
image with gender-split averages.
"""

from __future__ import annotations

import json

import plugins.academy_ops.monthly_test_records_tool as m

PAYLOAD = {
    "test": {"test_name": "2026년 5월 월말 테스트", "test_month": "2026-05"},
    "record_types": [
        {"record_type_id": "1", "name": "제자리멀리뛰기", "unit": "cm", "direction": "desc"},
        {"record_type_id": "2", "name": "20m왕복달리기", "unit": "초", "direction": "asc"},
    ],
    "participants": [
        {"name": "남학생가", "gender": "M", "school": "A고", "records": {"1": 295, "2": 13.7}},
        {"name": "남학생나", "gender": "M", "school": "B고", "records": {"1": 256, "2": 14.9}},
        {"name": "여학생가", "gender": "F", "school": "A고", "records": {"1": 230, "2": 16.2}},
    ],
}


def _mock_capture(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    captured = {}

    def fake(html_path, image_path, **kw):
        captured["html"] = html_path.read_text(encoding="utf-8")
        image_path.write_bytes(b"PNG")

    monkeypatch.setattr(m, "capture_html_to_png", fake)
    return captured


def test_all_events_image_has_every_event_and_gender_averages(monkeypatch, tmp_path):
    cap = _mock_capture(monkeypatch, tmp_path)
    path = m._all_events_table_image(PAYLOAD, exclude_schools=set())
    assert path is not None
    html = cap["html"]
    assert "제자리멀리뛰기" in html and "20m왕복달리기" in html  # 전체 종목
    assert "남자 평균" in html and "여자 평균" in html           # 성별 분리
    assert "남학생가" in html and "여학생가" in html              # 참가자 전원


def test_direction_maps_to_best():
    assert m._direction_best("asc") == "low"     # 시간류 작을수록 우수
    assert m._direction_best("desc") == "high"   # 거리류 클수록 우수


def test_school_query_filters(monkeypatch, tmp_path):
    cap = _mock_capture(monkeypatch, tmp_path)
    m._all_events_table_image(PAYLOAD, exclude_schools=set(), school_query="A고")
    html = cap["html"]
    assert "남학생가" in html and "여학생가" in html  # A고
    assert "남학생나" not in html                      # B고 제외


def test_handler_without_event_does_not_ask_for_event(monkeypatch, tmp_path):
    _mock_capture(monkeypatch, tmp_path)

    class _Client:
        def list_peak_monthly_tests(self):
            return [{"id": 13, "test_month": "2026-05", "status": "active"}]

        def get_peak_monthly_test_records(self, _tid):
            return PAYLOAD

    monkeypatch.setattr(m, "_resolve_client", lambda _c: _Client())
    res = json.loads(m._monthly_test_records_tool_handler({}))  # no event_query
    assert res["ok"] is True
    assert "MEDIA:" in res["message"]
    assert "종목을 알려줘" not in res["message"]  # 되묻지 않음
