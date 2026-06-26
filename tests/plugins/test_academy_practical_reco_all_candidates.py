"""Tests for all-candidate practical recommendation packaging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plugins.academy_ops.practical_reco_all_candidates import (
    _all_candidates_tool_handler,
    _candidate_row,
    build_all_candidates_content,
)


def _candidate(index: int, *, region: str = "충남") -> dict[str, Any]:
    return {
        "university_id": str(index),
        "university": f"테스트대{index}",
        "department": "스포츠학과",
        "admission_track": "실기일반",
        "region": region,
        "practical_events": ["제자리멀리뛰기", "왕복달리기"],
        "student_record_score": 312.5 + index,
        "max_possible_total": 812.5 + index,
        "prev_first_total": 780.0,
        "prev_final_total": 800.0,
        "suggested_verdict": "적정" if index == 1 else "상향",
        "minimum_csat": "국수영탐 중 2개 합 7 이내" if index == 1 else None,
        "reachable_at_full_practical": True,
    }


def _fake_recommend(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    candidates = [_candidate(1), _candidate(2, region="강원")]
    return {
        "student": "홍길동",
        "region_filter": ["충청", "강원"],
        "total_feasible": len(candidates),
        "returned": len(candidates),
        "candidates": candidates,
    }


def _fake_chromium(_html_path: Path, pdf_path: Path) -> None:
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")


def test_build_all_candidates_content_uses_region_and_candidate_rows(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_recommend(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return _fake_recommend(*args, **kwargs)

    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_all_candidates.recommend_candidates",
        fake_recommend,
    )

    content = build_all_candidates_content("홍길동", "수도권, 충청, 강원")

    assert calls[0]["region"] == "수도권, 충청, 강원"
    assert calls[0]["max_candidates"] == 400
    assert "include_unreachable" not in calls[0]
    assert content["report_mode"] == "all_candidates"
    assert content["comparison"]["show_events"] is True
    assert content["comparison"]["show_minimum_csat"] is True
    assert len(content["comparison"]["rows"]) == 2
    assert content["comparison"]["rows"][0]["events"] == "제자리멀리뛰기, 왕복달리기"
    assert content["comparison"]["rows"][0]["minimum_csat"] == "국수영탐 중 2개 합 7 이내"
    assert "충남" in content["comparison"]["rows"][0]["track"]
    assert [group["region"] for group in content["comparison"]["groups"]] == ["충남", "강원"]
    assert content["comparison"]["groups"][0]["count"] == 1
    assert content["comparison"]["groups"][1]["rows"][0]["school"] == "테스트대2"


def test_region_groups_keeps_requested_empty_provinces_visible(monkeypatch) -> None:
    def fake_recommend(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        candidates = [_candidate(1, region="충남")]
        return {
            "student": "홍길동",
            "region_filter": ["서울", "경기", "인천", "충남", "충북", "강원"],
            "total_feasible": len(candidates),
            "returned": len(candidates),
            "candidates": candidates,
        }

    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_all_candidates.recommend_candidates",
        fake_recommend,
    )

    content = build_all_candidates_content("홍길동", "수도권, 충청, 강원")
    groups = {group["region"]: group for group in content["comparison"]["groups"]}

    assert groups["충남"]["count"] == 1
    assert groups["강원"]["count"] == 0
    assert groups["서울"]["count"] == 0


def test_build_all_candidates_filters_full_practical_unreachable_rows(monkeypatch) -> None:
    unreachable = _candidate(2, region="강원")
    unreachable["reachable_at_full_practical"] = False
    unreachable["unreachable_reason"] = "실기 만점이어도 전년도 최종합 미달"

    def fake_recommend(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        candidates = [_candidate(1, region="충남"), unreachable]
        return {
            "student": "홍길동",
            "region_filter": ["충청", "강원"],
            "total_feasible": len(candidates),
            "returned": len(candidates),
            "candidates": candidates,
        }

    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_all_candidates.recommend_candidates",
        fake_recommend,
    )

    content = build_all_candidates_content("홍길동", "수도권, 충청, 강원")
    rows = content["comparison"]["rows"]
    groups = {group["region"]: group for group in content["comparison"]["groups"]}

    assert [row["school"] for row in rows] == ["테스트대1"]
    assert groups["충남"]["count"] == 1
    assert groups["강원"]["count"] == 0


def test_build_all_candidates_rejects_truncated_recommendation(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_all_candidates.recommend_candidates",
        lambda *_args, **_kwargs: {"total_feasible": 3, "candidates": [_candidate(1), _candidate(2)]},
    )

    try:
        build_all_candidates_content("홍길동", "전국")
    except ValueError as exc:
        assert "전체 후보 3개 중 2개만 반환" in str(exc)
    else:
        raise AssertionError("잘린 전체 후보는 PDF 생성 전에 차단되어야 한다.")


def test_candidate_row_keeps_stage_practical_display_text() -> None:
    candidate = _candidate(221, region="서울")
    candidate["university"] = "서경대학교"
    candidate["department"] = "스포츠앤테크놀로지학과"
    candidate["practical_events"] = [
        "1단계: 제자리멀리뛰기, 메디신볼던지기, 10m왕복달리기, 좌전굴",
        "2단계: 스포츠분야 분석·질의응답",
    ]

    row = _candidate_row(candidate)

    assert "1단계" in row["events"]
    assert "메디신볼던지기" in row["events"]
    assert "2단계: 스포츠분야 분석·질의응답" in row["events"]


def test_all_candidates_tool_writes_standard_template_pdf(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_all_candidates.recommend_candidates",
        _fake_recommend,
    )
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_all_candidates._chromium_print_to_pdf",
        _fake_chromium,
    )
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_all_candidates._validate_pdf_physical",
        lambda *_args, **_kwargs: None,
    )

    result = json.loads(
        _all_candidates_tool_handler({"student_name": "홍길동", "region": "수도권, 충청, 강원"})
    )

    assert result["ok"] is True, result.get("errors")
    assert result["row_count"] == 2
    assert Path(result["file_path"]).is_file()
    html = Path(result["html_path"]).read_text(encoding="utf-8")
    assert "수시 실기전형 맞춤 분석" in html
    assert "compactReport" in html
    assert "충남 1개 전형" in html
    assert "강원 1개 전형" in html
    assert "* 수능최저:" in html
    assert "국수영탐 중 2개 합 7 이내" in html
    assert "만점미달" not in html
    assert "점수 확인 안내" in html
    assert "진학사" in html
    assert "선생님 최종 의견" not in html
    assert "전국 수시 실기전형 추천 전략" not in html
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["mode"] == "all_candidates"
    assert manifest["evidence_tools"] == ["susi27_recommend_candidates"]
    assert manifest["row_count"] == 2
    assert manifest["school_names"] == ["테스트대1", "테스트대2"]
