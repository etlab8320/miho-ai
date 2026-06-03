"""Tests for student performance record chart image generation."""

from __future__ import annotations

import json
import struct

import plugins.academy_ops.student_record_chart_tool as chart_tool
from plugins.academy_ops.student_record_chart_tool import _student_record_chart_image_tool_handler


def _payload(raw: str) -> dict:
    return json.loads(raw)


def _png_header(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height)


class _ChartClient:
    def search_paca_students(self, query: str) -> list[dict]:
        if query == "김동혁":
            return [{"id": 101, "name": "김동혁", "school": "일산고", "grade": "고3", "status": "active"}]
        return []

    def list_paca_students(self, *, status: str = "active") -> list[dict]:
        return [
            {"id": 101, "name": "김동혁", "school": "일산고", "grade": "고3", "status": status},
            {"id": 102, "name": "박동혁", "school": "강남고", "grade": "고3", "status": status},
        ]

    def list_peak_students(self) -> list[dict]:
        return [{"id": 501, "paca_student_id": 101, "name": "김동혁"}]

    def list_peak_records(self, peak_student_id: int) -> list[dict]:
        assert peak_student_id == 501
        rows = []
        for index, value in enumerate([236, 240, 244, 248, 250], start=1):
            rows.append(
                {
                    "record_type_name": "제자리멀리뛰기",
                    "measured_at": f"2026-05-{20 + index:02d}",
                    "value": str(value),
                    "unit": "cm",
                    "direction": "higher",
                }
            )
        for index, value in enumerate([9.1, 9.3, 9.5], start=1):
            rows.append(
                {
                    "record_type_name": "메디신볼",
                    "measured_at": f"2026-05-{25 + index:02d}",
                    "value": str(value),
                    "unit": "m",
                    "direction": "higher",
                }
            )
        return rows


def test_student_record_chart_image_recovers_typo_and_renders_png(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    captured: dict[str, object] = {}

    def fake_capture(html_path, image_path, **kwargs):
        captured["html"] = html_path.read_text(encoding="utf-8")
        captured["width"] = kwargs.get("width")
        captured["height"] = kwargs.get("height")
        image_path.write_bytes(_png_header(int(kwargs["width"]), int(kwargs["height"])))

    monkeypatch.setattr(chart_tool, "capture_html_to_png", fake_capture)

    result = _payload(
        _student_record_chart_image_tool_handler(
            {
                "student_query": "깅동혁 최근 5회차실기기록들 각 종목별 그래프로 그려서 이미지로줘",
                "limit": 5,
                "today": "2026-06-03",
                "period_days": 60,
            },
            client=_ChartClient(),
        )
    )

    assert result["ok"] is True
    assert result["student"]["name"] == "김동혁"
    assert result["media_tag"] == f"MEDIA:{result['image_path']}"
    assert "김동혁 최근 5회차 실기 그래프" in result["message"]
    assert "제자리멀리뛰기" in str(captured["html"])
    assert "메디신볼" in str(captured["html"])
    assert "<svg" in str(captured["html"])
    assert captured["width"] == 1240
    assert captured["height"] >= 760


def test_student_record_chart_image_rejects_invalid_png_after_capture(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    def fake_capture(html_path, image_path, **kwargs):
        image_path.write_bytes(b"not a png")

    monkeypatch.setattr(chart_tool, "capture_html_to_png", fake_capture)

    result = _payload(
        _student_record_chart_image_tool_handler(
            {
                "student_query": "김동혁",
                "limit": 5,
                "today": "2026-06-03",
                "period_days": 60,
            },
            client=_ChartClient(),
        )
    )

    assert result["ok"] is False
    assert "검수" in result["message"]


def test_student_record_chart_image_rejects_short_canvas_after_capture(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    def fake_capture(html_path, image_path, **kwargs):
        image_path.write_bytes(_png_header(int(kwargs["width"]), 120))

    monkeypatch.setattr(chart_tool, "capture_html_to_png", fake_capture)

    result = _payload(
        _student_record_chart_image_tool_handler(
            {
                "student_query": "김동혁",
                "limit": 5,
                "today": "2026-06-03",
                "period_days": 60,
            },
            client=_ChartClient(),
        )
    )

    assert result["ok"] is False
    assert "검수" in result["message"]


def test_student_record_chart_image_returns_plain_not_found_message() -> None:
    class EmptyClient(_ChartClient):
        def search_paca_students(self, query: str) -> list[dict]:
            return []

        def list_paca_students(self, *, status: str = "active") -> list[dict]:
            return []

    result = _payload(
        _student_record_chart_image_tool_handler(
            {"student_query": "없는학생", "today": "2026-06-03"},
            client=EmptyClient(),
        )
    )

    assert result["ok"] is False
    assert result["message"] == "학생을 찾지 못했어. 이름이나 학교를 조금 더 정확히 알려줘."


def test_lower_direction_record_improvement_goes_up_on_svg() -> None:
    records = [
        {"value": 15.5, "unit": "초", "direction": "lower"},
        {"value": 15.1, "unit": "초", "direction": "lower"},
        {"value": 14.8, "unit": "초", "direction": "lower"},
    ]

    svg = chart_tool._svg(records)
    first_y = float(svg.split("points='")[1].split("'")[0].split()[0].split(",")[1])
    latest_y = float(svg.split("points='")[1].split("'")[0].split()[-1].split(",")[1])

    assert latest_y < first_y


def test_chart_height_scales_to_full_content_for_many_events() -> None:
    groups = [
        {"records": [{"value": value, "unit": "cm", "direction": "higher"} for value in range(5)]}
        for _ in range(6)
    ]

    assert chart_tool._chart_height(groups) >= 1700
