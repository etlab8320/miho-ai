"""Tests for school-specific grounding inside hakjong gap plans."""

from __future__ import annotations

from plugins.academy_ops.hakjong_grounding import (
    apply_gap_plan_grounding,
    validate_gap_plan_grounding,
)


def _profile() -> dict:
    return {
        "desired_record_keywords": ["운동처방", "재활운동 프로그램 설계", "기능평가"],
        "live_research": {
            "faculty_profiles": [
                {"name": "이대택", "major": "운동 생리학"},
                {"name": "이기광", "major": "운동역학"},
            ],
            "faculty_paper_sources": [
                {
                    "title": "Lower-extremity biomechanics during jump landing",
                    "snippet": "운동역학 재활 연구",
                }
            ],
            "paper_title_live_probe": [{"usable_keywords": ["하지 운동역학", "착지 안정성"]}],
            "field_news_live_probe": [{"title": "스포츠 재활 데이터 분석", "keywords": ["웨어러블", "재활 데이터"]}],
        },
    }


def _gap_subject(field: str, *, direction: str = "학과 최신 흐름에 맞춰 확장한다.") -> dict:
    return {
        "field": field,
        "current_record": f"{field} 기존 기록을 출발점으로 삼아 학생의 실제 활동을 이어 간다.",
        "school_direction": direction,
        "steps": [
            "기존 활동에서 측정 가능한 변수를 정하고 주차별 기록표를 만들어 데이터를 모은다.",
            "수집한 데이터를 그래프로 정리하고 변화 원인을 비교 분석한다.",
            "분석 과정의 한계와 개선 방향을 보고서와 발표로 정리한다.",
        ],
        "expected_effect": "탐구 지속성과 문제해결 과정을 보여준다.",
    }


def _content(subjects: list[dict]) -> dict:
    return {"strategy_section": {"gap_plan": {"title": "세특 설계", "subjects": subjects}}}


def test_gap_plan_rejects_profile_terms_only_outside_subject_plan() -> None:
    content = _content([_gap_subject("체육"), _gap_subject("과학"), _gap_subject("수학")])
    content["track_section"] = {
        "rows": [
            {
                "label": "최신 학과 흐름",
                "official": "운동처방 재활운동 프로그램 설계 하지 운동역학",
                "judgment": "표 설명에는 들어갔다.",
            }
        ]
    }

    errors = validate_gap_plan_grounding(content, _profile(), student_stage="grade3")
    joined = "\n".join(errors)

    assert "세특 설계 본문" in joined
    assert "라이브 근거" in joined


def test_apply_gap_plan_grounding_injects_rotated_school_anchors() -> None:
    content = _content([_gap_subject("체육"), _gap_subject("과학"), _gap_subject("수학")])

    changed = apply_gap_plan_grounding(content, _profile())
    visible = str(content)

    assert changed is True
    assert "운동처방" in visible or "재활운동 프로그램 설계" in visible
    assert "Lower-extremity biomechanics during jump landing" in visible
    assert not validate_gap_plan_grounding(content, _profile(), student_stage="grade3")


def test_gap_plan_grounding_is_not_required_for_graduates() -> None:
    content = _content([_gap_subject("체육")])

    assert validate_gap_plan_grounding(content, _profile(), student_stage="graduate") == []


def test_gap_plan_rejects_copy_paste_subject_design() -> None:
    same = "운동처방과 기능평가를 중심으로 웨어러블 데이터를 수집하고 재활 데이터 분석으로 확장한다."
    content = _content([
        _gap_subject("체육", direction=same),
        _gap_subject("과학", direction=same),
        _gap_subject("수학", direction=same),
    ])
    for subject in content["strategy_section"]["gap_plan"]["subjects"]:
        subject["expected_effect"] = "운동처방 기능평가 하지 운동역학 웨어러블 흐름으로 설명한다."

    errors = validate_gap_plan_grounding(content, _profile(), student_stage="grade3")

    assert any("복붙 구조" in error for error in errors)


def test_gap_plan_rejects_raw_topics_without_school_lens() -> None:
    content = _content([
        _gap_subject(
            "플라잉디스크",
            direction="운동처방과 기능평가를 중심으로 하지 운동역학 흐름을 반영한다.",
        ),
        _gap_subject(
            "스포츠 노화",
            direction="재활운동 프로그램 설계와 착지 안정성 흐름을 반영한다.",
        ),
        _gap_subject(
            "도핑",
            direction="웨어러블과 재활 데이터 흐름을 반영한다.",
        ),
    ])

    errors = validate_gap_plan_grounding(content, _profile(), student_stage="grade3")

    assert any("학교별 관점" in error for error in errors)


def test_apply_gap_plan_grounding_transforms_raw_topics_with_school_lens() -> None:
    content = _content([
        _gap_subject("플라잉디스크"),
        _gap_subject("스포츠 노화"),
        _gap_subject("도핑"),
    ])

    changed = apply_gap_plan_grounding(content, _profile())
    visible = str(content)

    assert changed is True
    assert "기능평가·운동처방" in visible
    assert "관절 가동범위" in visible
    assert "개인별 운동처방 보고서" in visible
    assert "측정 한계" in visible
    assert "문제정의:" not in visible
    assert "측정변수:" not in visible
    assert "산출물:" not in visible
    assert "면접 방어:" not in visible
    assert ".기능평가" not in visible
    assert "성로" not in visible
    assert "바꾼다는 방향" not in visible
    assert not validate_gap_plan_grounding(content, _profile(), student_stage="grade3")


def test_sports_science_lens_wins_over_region_and_education_words() -> None:
    profile = {
        "university": "서울과학기술대학교",
        "department": "스포츠과학과",
        "admission_track": "농어촌학생",
        "desired_record_keywords": ["공동교육과정", "지역", "운동생리학 탐구", "체력 측정과 데이터 분석"],
    }
    content = _content([_gap_subject("과학·생명과학 I")])

    apply_gap_plan_grounding(content, profile)
    visible = str(content)

    assert "운동역학·생리측정" in visible
    assert "체육수업 설계·피드백" not in visible


def test_gap_plan_rejects_visible_internal_labels() -> None:
    content = _content([
        _gap_subject(
            "기능평가·운동처방·체육",
            direction="문제정의: 운동처방과 기능평가를 중심으로 하지 운동역학 흐름을 반영한다.",
        )
    ])
    subject = content["strategy_section"]["gap_plan"]["subjects"][0]
    subject["steps"][0] += " 측정변수: 관절 가동범위와 회복시간."
    subject["steps"][1] += " 산출물: 개인별 운동처방 보고서."
    subject["expected_effect"] = "면접 방어: 측정 한계를 설명한다."

    errors = validate_gap_plan_grounding(content, _profile(), student_stage="grade3")

    assert any("내부 작업 라벨" in error for error in errors)


def test_gap_plan_rejects_search_ui_noise_in_visible_report() -> None:
    content = _content([
        _gap_subject(
            "기능평가·운동처방·체육",
            direction=(
                "국민대학교 스포츠건강재활학과 뉴스 최신 스포츠 과학 : "
                "네이버 검색 메뉴 영역으로 바로가기"
            ),
        )
    ])

    errors = validate_gap_plan_grounding(content, _profile(), student_stage="grade3")

    assert any("검색 UI 찌꺼기" in error for error in errors)
