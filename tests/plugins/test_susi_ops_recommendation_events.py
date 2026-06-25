"""Recommendation event display normalization tests."""

from __future__ import annotations


def test_event_info_separates_seokyeong_stage1_events_from_stage2_analysis() -> None:
    from plugins.susi_ops.recommendation_events import recommendation_event_info

    payload = {
        "events": [{"name": "스포츠분야 분석 및 질의응답"}],
        "stage1_events": [
            {"name": "제자리멀리뛰기"},
            {"name": "메디신볼던지기"},
            {"name": "10m왕복달리기"},
            {"name": "좌전굴"},
        ],
        "selection_rule": "1단계 과목측정은 400% 선발용, 최종 2단계 실기 컴포넌트는 스포츠분야 분석 및 질의응답 800점",
    }

    info = recommendation_event_info(payload)

    assert info["events"] == ["제자리멀리뛰기", "메디신볼던지기", "10m왕복달리기", "좌전굴"]
    assert info["display_events"] == [
        "1단계: 제자리멀리뛰기, 메디신볼던지기, 10m왕복달리기, 좌전굴",
        "2단계: 스포츠분야 분석·질의응답",
    ]
    assert "실기 100%" in info["event_note"]


def test_event_info_keeps_normal_practical_events() -> None:
    from plugins.susi_ops.recommendation_events import recommendation_event_info

    info = recommendation_event_info(
        {"events": [{"name": "제자리 멀리뛰기"}, {"name": "좌전굴"}], "selection_rule": "전 종목 반영"}
    )

    assert info["events"] == ["제자리 멀리뛰기", "좌전굴"]
    assert info["display_events"] == ["제자리 멀리뛰기", "좌전굴"]
    assert info["event_note"] is None
