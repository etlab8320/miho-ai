"""Graduate-mode content adapter for hakjong audit reports."""

from __future__ import annotations

from typing import Any


def adapt_for_graduate(content: dict[str, Any]) -> dict[str, Any]:
    """Convert enrolled-student planning content into completed-record review mode."""
    if not isinstance(content, dict):
        return content
    student = str((content.get("student") or {}).get("name") or "학생")
    university = content.get("university") if isinstance(content.get("university"), dict) else {}
    department = str(university.get("department") or "지원 학과")
    track = str(university.get("track") or "학종")
    keyword_text = _metric_value(content, "키워드") or department
    source_text = _track_source(content) or f"{department} 공식 전형 자료"

    content.setdefault("badge", {})["action"] = "완성 생기부 재해석"
    cover = content.setdefault("cover", {})
    cover["key_judgment"] = {
        "headline": "지원 가능성 판단: 완성 생기부 검토",
        "body": (
            f"{student}의 완성 생기부 기록 근거를 {keyword_text} 중심으로 읽고, "
            f"{source_text} 기준에서 {department} 지원 가능성을 판단한다. "
            "면접이 있으면 활동 동기, 한계, 배운 점을 질문별로 방어한다."
        ),
    }

    track_section = content.get("track_section") if isinstance(content.get("track_section"), dict) else {}
    track_section["caution_points"] = {
        "title": "주의",
        "bullets": [
            "새 활동을 만든다는 표현 없이 완성된 기록의 강점과 한계를 분리한다",
            "학교별 평가언어와 실제 과목 기록이 닿는 부분만 지원 근거로 쓴다",
        ],
    }

    diagnosis = content.get("diagnosis_section") if isinstance(content.get("diagnosis_section"), dict) else {}
    strength = diagnosis.get("strength") if isinstance(diagnosis.get("strength"), dict) else {}
    if strength:
        strength["body"] = (
            f"완성 생기부 안의 실제 과목·활동 기록 근거가 {keyword_text} 흐름과 연결된다. "
            f"{department} 관점에서는 새 기록 추가가 아니라 이미 남은 기록의 일관성과 설명력이 핵심이다."
        )

    strategy = content.setdefault("strategy_section", {})
    strategy.pop("gap_plan", None)
    strategy["heading"] = "완성 생기부 활용 전략"
    strategy["actions"] = _graduate_actions(department, track, keyword_text, source_text)
    strategy["final_judgment"] = {
        "body": (
            f"지원 가능성 판단: {student}의 완성 생기부 기록 근거를 기준으로 {department} 적합성을 검토한다. "
            "면접 방어는 활동 동기, 방법, 한계, 배운 점을 질문별로 설명하는 방식으로 준비한다."
        )
    }
    strategy["checklist"] = {
        "title": "완성 생기부 검증 체크",
        "bullets": ["기록 근거", "평가언어", "지원 가능성 판단", "면접 방어"],
        "tags": [str(university.get("name") or ""), department, track],
    }
    return content


def _graduate_actions(department: str, track: str, keyword_text: str, source_text: str) -> list[dict[str, str]]:
    return [
        {
            "title": "기존 기록 재해석",
            "body": f"완성 생기부의 과목·활동 기록 근거가 {department} 평가언어와 맞물리는 지점을 먼저 표시한다.",
        },
        {
            "title": "학교별 평가언어 연결",
            "body": f"{track}에서는 {keyword_text} 흐름과 {source_text} 근거를 중심으로 강점과 약점을 나눠 판단한다.",
        },
        {
            "title": "면접 방어",
            "body": "면접이 있으면 활동 동기, 방법, 한계, 배운 점을 질문별로 정리해 설명력과 방어 포인트를 확보한다.",
        },
        {
            "title": "최종 점검",
            "body": "지원 가능성 판단은 새 기록 추가가 아니라 이미 있는 기록의 일관성, 학과 적합성, 전형 구조 적합성으로 확인한다.",
        },
    ]


def _metric_value(content: dict[str, Any], label: str) -> str:
    for item in ((content.get("cover") or {}).get("metrics") or []):
        if isinstance(item, dict) and str(item.get("label") or "") == label:
            return str(item.get("value") or "").strip()
    return ""


def _track_source(content: dict[str, Any]) -> str:
    section = content.get("track_section") if isinstance(content.get("track_section"), dict) else {}
    for item in section.get("rows") or []:
        if isinstance(item, dict) and str(item.get("label") or "") == "최신 학과 흐름":
            value = str(item.get("official") or "").strip()
            return value.replace("교수 논문/뉴스 근거:", "").replace("학종 DB/공식 학과 방향:", "").strip()
    return ""
