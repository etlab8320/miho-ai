"""Tests for hakjong_report_schema — T2 content JSON validation."""

from __future__ import annotations

from plugins.academy_ops.hakjong_report_schema import validate_content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _body(n: int = 1) -> str:
    """Return a substantive body text ≤ 230 chars."""
    base = (
        "학생부의 세특과 진로활동을 대학 평가요소와 대조해 강점과 보완점을 분리하고 "
        "지원 판단에 바로 반영할 수 있도록 정리한다."
    )
    return (base + " ") * n


def _base_content(stage: str = "grade3") -> dict:
    """Minimal valid content dict matching the real template structure."""
    long_body = _body(1)
    school_body = (
        "지원 가능성 판단: 이 학생의 세특과 진로활동은 해당 학과 인재상에 부합한다. "
        "1학기 입력 전 과세특 세특 보완이 필요한 부분을 정리하면 대학 평가 요소에서 강점으로 작용한다. "
        "대학 학과 평가 요소 기준으로 추천 가능하다."
    )
    return {
        "student": {"name": "홍길동"},
        "university": {"name": "성균관대학교", "department": "스포츠과학과", "college": "사범대학", "track": "성균인재"},
        "badge": {"grade": "평가등급 B", "action": "지원 추천"},
        "title_lines": ["홍길동 학생 학종 전략 리포트"],
        "cover": {
            "pills": ["성균관대학교", "성균인재"],
            "key_judgment": {"headline": "세특 일관성이 핵심 강점이다", "body": long_body},
            "metrics": [
                {"label": "지원적합도", "value": "높음"},
                {"label": "전공적합성", "value": "우수"},
                {"label": "보완 필요", "value": "면접"},
            ],
        },
        "track_section": {
            "heading": "성균인재 전형 핵심 분석",
            "info_cards": [
                {"label": "전형 방법", "value": "서류 100%", "sub": ""},
                {"label": "모집 인원", "value": "20명", "sub": ""},
                {"label": "수능 최저", "value": "없음", "sub": ""},
            ],
            "rows": [{"label": "서류", "official": "학생부", "judgment": school_body}],
            "strong_points": {"title": "강점 포인트", "bullets": ["세특 일관성", "진로활동 연계"]},
            "caution_points": {"title": "주의 포인트", "bullets": ["면접 준비 필요"]},
            "footnote": "성균관대학교 2027 입학전형 기준",
        },
        "diagnosis_section": {
            "heading": "학생부 객관 진단",
            "strength": {"headline": "탐구 지속성 강함", "body": school_body},
            "risk": {"headline": "출결 기록 확인 필요", "body": school_body},
            "rows": [
                {"area": "세특", "record": school_body, "interpretation": long_body, "check": "확인 불요"},
            ],
            "gauges": [
                {"label": "전공적합성", "level": "상", "note": "탐구 연속성 있음", "tone": "blue", "percent": 80},
                {"label": "학업역량", "level": "중상", "note": "등급 안정적", "tone": "orange", "percent": 65},
                {"label": "발전가능성", "level": "상", "note": "면접 방어 가능", "tone": "blue", "percent": 75},
            ],
            "footnote": "생기부 원문 기준 분석",
        },
        "strategy_section": {
            "heading": "맞춤 보완 전략",
            "actions": [
                {"title": "세특 마무리", "body": school_body},
                {"title": "진로활동 정리", "body": school_body},
                {"title": "면접 준비", "body": school_body},
                {"title": "최종 점검", "body": school_body},
            ],
            "interview_rows": [{"question": "탐구 과정 설명", "point": school_body}],
            "final_judgment": {"body": school_body},
            "checklist": {
                "title": "지원 전 체크리스트",
                "bullets": ["세특 입력 완료", "면접 준비"],
                "tags": ["성균관대학교", "성균인재"],
            },
            "footnote": "맥스체대입시 일산교육원",
        },
    }


def _base_evidence() -> list[str]:
    return ["life_record_lookup", "qualitative_profile"]


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------

def test_valid_grade3_content_passes() -> None:
    ok, errors = validate_content(_base_content(), student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is True, errors


def test_missing_student_name_fails() -> None:
    content = _base_content()
    content["student"]["name"] = ""
    ok, errors = validate_content(content, student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is False
    assert any("student.name" in e for e in errors)


def test_missing_university_fails() -> None:
    content = _base_content()
    del content["university"]
    ok, errors = validate_content(content, student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is False
    assert any("university" in e for e in errors)


def test_university_missing_track_fails() -> None:
    content = _base_content()
    content["university"]["track"] = ""
    ok, errors = validate_content(content, student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is False
    assert any("university.track" in e for e in errors)


def test_missing_badge_fails() -> None:
    content = _base_content()
    del content["badge"]
    ok, errors = validate_content(content, student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is False
    assert any("badge" in e for e in errors)


def test_cover_wrong_metrics_count_fails() -> None:
    content = _base_content()
    content["cover"]["metrics"] = [{"label": "a", "value": "b"}]
    ok, errors = validate_content(content, student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is False
    assert any("metrics" in e for e in errors)


def test_track_section_wrong_info_cards_fails() -> None:
    content = _base_content()
    content["track_section"]["info_cards"] = [{"label": "a", "value": "b"}]
    ok, errors = validate_content(content, student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is False
    assert any("info_cards" in e for e in errors)


def test_diagnosis_wrong_gauges_count_fails() -> None:
    content = _base_content()
    content["diagnosis_section"]["gauges"] = []
    ok, errors = validate_content(content, student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is False
    assert any("gauges" in e for e in errors)


def test_strategy_wrong_actions_count_fails() -> None:
    content = _base_content()
    content["strategy_section"]["actions"] = content["strategy_section"]["actions"][:2]
    ok, errors = validate_content(content, student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is False
    assert any("actions" in e for e in errors)


# ---------------------------------------------------------------------------
# Quality tests
# ---------------------------------------------------------------------------

def test_overlong_text_block_fails() -> None:
    content = _base_content()
    content["strategy_section"]["final_judgment"]["body"] = "지원 전략 설명 " * 40
    ok, errors = validate_content(content, student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is False
    assert any("230자" in e for e in errors)


def test_short_total_text_fails() -> None:
    """Replace all long bodies with one-char strings to fall below 1600 total."""
    content = _base_content()
    short = "짧"
    content["cover"]["key_judgment"]["body"] = short
    content["track_section"]["rows"] = [{"label": "l", "official": short, "judgment": short}]
    content["track_section"]["strong_points"]["bullets"] = [short]
    content["track_section"]["caution_points"]["bullets"] = [short]
    content["track_section"]["footnote"] = short
    content["diagnosis_section"]["strength"]["body"] = short
    content["diagnosis_section"]["risk"]["body"] = short
    content["diagnosis_section"]["rows"] = [{"area": short, "record": short, "interpretation": short, "check": short}]
    content["diagnosis_section"]["footnote"] = short
    for a in content["strategy_section"]["actions"]:
        a["body"] = short
    content["strategy_section"]["interview_rows"] = [{"question": short, "point": short}]
    content["strategy_section"]["final_judgment"]["body"] = short
    content["strategy_section"]["checklist"]["bullets"] = [short]
    content["strategy_section"]["footnote"] = short
    ok, errors = validate_content(content, student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is False
    assert any("1600자" in e for e in errors)


def test_banned_wording_fails() -> None:
    content = _base_content()
    content["strategy_section"]["final_judgment"]["body"] = "프리미엄 전략으로 구성했다."
    ok, errors = validate_content(content, student_stage="grade3", evidence_tools=_base_evidence())
    assert ok is False
    assert any("프리미엄" in e for e in errors)


# ---------------------------------------------------------------------------
# Stage contract tests
# ---------------------------------------------------------------------------

def test_missing_student_stage_fails() -> None:
    ok, errors = validate_content(_base_content(), student_stage="", evidence_tools=_base_evidence())
    assert ok is False
    assert any("student_stage" in e for e in errors)


def test_grade1_content_passes_with_consultation_evidence() -> None:
    content = _base_content()
    # Satisfy grade1 stage requirements in text fields
    grade1_body = (
        "상담에서 확인한 관심 학교생활 기반으로 생활기록부 시작 기록 설계와 "
        "대학 학과 인재상 평가 요소 연결을 목표로 한다."
    )
    content["strategy_section"]["final_judgment"]["body"] = grade1_body
    content["track_section"]["rows"][0]["judgment"] = grade1_body
    ok, errors = validate_content(
        content, student_stage="grade1", evidence_tools=["consultation_note", "qualitative_profile"]
    )
    assert ok is True, errors


def test_grade3_missing_life_record_fails() -> None:
    ok, errors = validate_content(
        _base_content(), student_stage="grade3", evidence_tools=["qualitative_profile"]
    )
    assert ok is False
    assert any("life_record" in e for e in errors)


def test_missing_hakjong_evidence_fails() -> None:
    ok, errors = validate_content(
        _base_content(), student_stage="grade3", evidence_tools=["life_record_lookup"]
    )
    assert ok is False
    assert any("학종" in e or "프로파일" in e for e in errors)
