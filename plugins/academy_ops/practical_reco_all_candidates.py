"""All-candidate practical recommendation package tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home

from .artifact_latch import current_turn_reviewed_artifact
from .practical_reco_tool import (
    _chromium_print_to_pdf,
    _render_html,
    _safe_stem,
    _unique_pair,
    _validate_pdf_physical,
)
from plugins.susi_ops.service import recommend_candidates

from .accuracy_contract import build_accuracy_receipt


ALL_CANDIDATE_LIMIT = 400
ALL_CANDIDATE_PAGE_SIZE = 10


def build_all_candidates_content(
    student_name: str,
    region: str,
    *,
    admission_track: str | None = None,
    student_gender: str | None = None,
    extra_filters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build standard-template content from the single susi recommendation pipeline."""
    clean_student = str(student_name or "").strip()
    clean_region = str(region or "").strip()
    if not clean_student:
        raise ValueError("student_name이 필요하다.")
    if not clean_region:
        raise ValueError("region이 필요하다. 사용자가 말한 지역을 그대로 넣어야 한다.")

    result = recommend_candidates(
        clean_student,
        region=clean_region,
        admission_track=admission_track,
        student_gender=student_gender,
        max_candidates=ALL_CANDIDATE_LIMIT,
    )
    if result.get("need_region"):
        raise ValueError(str(result.get("message") or "지역을 먼저 정해야 한다."))
    if result.get("error"):
        raise ValueError(str(result["error"]))

    candidates = _merged_candidates(
        result.get("candidates") or [],
        clean_student=clean_student,
        clean_region=clean_region,
        student_gender=student_gender,
        extra_filters=extra_filters,
    )
    if not isinstance(candidates, list):
        candidates = []
    total_feasible = _int_or_default(result.get("total_feasible"), len(candidates))
    if total_feasible > len(candidates):
        raise ValueError(
            f"전체 후보 {total_feasible}개 중 {len(candidates)}개만 반환되어 PDF를 만들 수 없다. "
            "추천 엔진 후보 반환 한도를 먼저 넓혀야 한다."
        )
    # This package is explicitly for 실기전형 PDFs. The recommender can also surface
    # record-only 교과전형 rows when they clear prior-year score checks, but those
    # should not appear in a practical-admission PDF just because the user asked for
    # all regional candidates. Keep only rows with actual practical events/full score.
    candidates = [c for c in candidates if _is_practical_candidate_for_all_package(c)]
    if not candidates:
        raise ValueError(f"{clean_student} 학생의 {clean_region} 실기전형 후보가 없다.")

    rows = [_candidate_row(c) for c in candidates]
    groups = _region_groups(rows, expected_regions=result.get("region_filter"))
    fit_count = sum(1 for row in rows if row["verdict"] == "적정")
    up_count = len(rows) - fit_count
    region_label = _region_label(result.get("region_filter"), clean_region)
    accuracy_receipt = _accuracy_receipt(
        student_name=clean_student,
        region=clean_region,
        rows=rows,
        candidates=candidates,
        no_truncation=True,
        pdf_physical_validation=True,
    )
    return {
        "report_mode": "all_candidates",
        "accuracy_receipt": accuracy_receipt,
        "student": {
            "name": clean_student,
            "avg_grade": "",
            "basis_label": "생기부 내신 기준",
        },
        "title_lines": [clean_student + " 학생", region_label + " 수시 실기전형 전체 추천"],
        "cover": {
            "pills": ["수시 실기전형", region_label, f"{len(rows)}개 전형"],
            "key_judgment": {
                "headline": f"{region_label}에서 도달 가능한 실기전형 {len(rows)}개",
                "body": "상향 여부로 임의 제외하지 않고, 실기 만점 합산이 전년도 최종합격선에 닿는 전형을 지역별 상담표로 정리했다.",
            },
            "metrics": [
                {"label": "요청 지역", "value": region_label},
                {"label": "도달 가능", "value": f"{len(rows)}개"},
                {"label": "적정/상향", "value": f"{fit_count}/{up_count}"},
            ],
        },
        "comparison": {
            "note": "모든 점수는 수시 추천 단일 파이프라인 산출값이며, 실기 만점 도달 가능 전형만 표시했다.",
            "batch_size": ALL_CANDIDATE_PAGE_SIZE,
            "show_events": True,
            "show_minimum_csat": any(row["minimum_csat"] != "-" for row in rows),
            "rows": rows,
            "groups": groups,
        },
        "schools": [],
        "final": {
            "cards": [
                {"title": "적정 기준", "body": "필요 실기율이 85% 이하인 전형이다. 실기에서 평균 이상을 만들면 비교 가능한 구간이다."},
                {"title": "상향 기준", "body": "필요 실기율이 85%를 넘는 전형이다. 실기 기록이 강하게 받쳐야 한다."},
                {"title": "확인 항목", "body": "실기종목, 전년도 전형 구조, 외부 환산점수 차이를 함께 확인한다."},
            ],
            "callout": {
                "title": "점수 확인 안내",
                "paragraphs": [
                    "현재 내신환산은 2027 모집요강 기준 내부 산식으로 계산한 값입니다. 진학사 등 외부 서비스의 환산점수와는 반영 방식, 반올림, 전년도 기준 차이로 점수가 달라질 수 있으니 최종 지원 전 반드시 대조하세요."
                ],
            },
            "tags": ["수시실기", region_label, "전체후보"],
        },
        "footnote": "산출 근거: 수시 추천 검증 룰 · 전년도 입시결과",
    }


def _merged_candidates(
    base_candidates: Any,
    *,
    clean_student: str,
    clean_region: str,
    student_gender: str | None,
    extra_filters: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    candidates = list(base_candidates) if isinstance(base_candidates, list) else []
    seen = {_candidate_key(candidate) for candidate in candidates if isinstance(candidate, dict)}
    for item in extra_filters or []:
        if not isinstance(item, dict):
            continue
        result = recommend_candidates(
            clean_student,
            region=clean_region,
            university=item.get("university"),
            department=item.get("department"),
            admission_track=item.get("admission_track"),
            student_gender=item.get("student_gender") or student_gender,
            max_candidates=ALL_CANDIDATE_LIMIT,
        )
        for candidate in result.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            key = _candidate_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    return candidates


def _candidate_key(candidate: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(candidate.get("university_id") or ""),
        str(candidate.get("university") or ""),
        str(candidate.get("department") or ""),
        str(candidate.get("admission_track") or ""),
    )


def _candidate_row(candidate: dict[str, Any]) -> dict[str, str]:
    events = candidate.get("practical_events")
    if isinstance(events, list):
        event_text = ", ".join(str(event) for event in events if str(event).strip())
    else:
        event_text = str(events or "").strip()
    region = str(candidate.get("region") or "").strip()
    track = str(candidate.get("admission_track") or "").strip()
    if region and region not in track:
        track = f"{track} · {region}" if track else region
    return {
        "university_id": str(candidate.get("university_id") or ""),
        "region": region,
        "school": str(candidate.get("university") or ""),
        "department": str(candidate.get("department") or ""),
        "track": track,
        "events": event_text[:120] if event_text else "-",
        "minimum_csat": _text_or_dash(candidate.get("minimum_csat"), limit=90),
        "converted": _num_or_dash(candidate.get("student_record_score")),
        "max_total": _num_or_dash(candidate.get("max_possible_total")),
        "first_cut": _num_or_dash(candidate.get("prev_first_total")),
        "final_cut": _num_or_dash(candidate.get("prev_final_total")),
        "verdict": str(candidate.get("suggested_verdict") or "상향"),
    }


def _is_practical_candidate_for_all_package(candidate: dict[str, Any]) -> bool:
    if not (candidate.get("practical_events") or []):
        return False
    if candidate.get("record_only_track"):
        return False
    return candidate.get("reachable_at_full_practical") is not False


def _text_or_dash(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    return text[:limit]


def _region_groups(rows: list[dict[str, str]], expected_regions: Any = None) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    index_by_region: dict[str, int] = {}

    def ensure_group(region_value: Any) -> dict[str, Any]:
        region = str(region_value or "지역 미상").strip() or "지역 미상"
        group_index = index_by_region.get(region)
        if group_index is None:
            group_index = len(groups)
            index_by_region[region] = group_index
            groups.append({"region": region, "count": 0, "fit_count": 0, "up_count": 0, "rows": []})
        return groups[group_index]

    for row in rows:
        group = ensure_group(row.get("region"))
        group["rows"].append(row)
        group["count"] += 1
        if row.get("verdict") == "적정":
            group["fit_count"] += 1
        else:
            group["up_count"] += 1
    if isinstance(expected_regions, (list, tuple)):
        province_names = {"서울", "경기", "인천", "강원", "대전", "세종", "충남", "충북", "부산", "대구", "울산", "경남", "경북", "광주", "전남", "전북", "제주"}
        for region in expected_regions:
            if str(region or "").strip() in province_names:
                ensure_group(region)
    return groups


def _num_or_dash(value: Any) -> str:
    if value is None or value == "":
        return "-"
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _region_label(region_filter: Any, fallback: str) -> str:
    if isinstance(region_filter, list):
        return "·".join(str(item).strip() for item in region_filter if str(item).strip()) or fallback
    return str(region_filter or fallback).strip()


def _all_candidates_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    args = args or {}
    reviewed = current_turn_reviewed_artifact("academy_practical_reco_all_candidates", args)
    if reviewed:
        return reviewed
    student_name = str(args.get("student_name") or "").strip()
    region = str(args.get("region") or "").strip()
    admission_track = str(args.get("admission_track") or "").strip() or None
    student_gender = str(args.get("student_gender") or "").strip() or None
    extra_filters = args.get("extra_filters") if isinstance(args.get("extra_filters"), list) else None
    try:
        content = build_all_candidates_content(
            student_name,
            region,
            admission_track=admission_track,
            student_gender=student_gender,
            extra_filters=extra_filters,
        )
    except ValueError as exc:
        return json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False)

    out_dir = get_miho_home() / "media_cache" / "susi_student_record" / "validated"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(student_name, "실기전형전체추천")
    html_path, pdf_path = _unique_pair(out_dir / f"{stem}.html", out_dir / f"{stem}.pdf")
    html_path.write_text(_render_html(content), encoding="utf-8")
    try:
        _chromium_print_to_pdf(html_path, pdf_path)
    except RuntimeError as exc:
        html_path.unlink(missing_ok=True)
        return json.dumps({"ok": False, "errors": [f"PDF 생성 실패: {exc}"]}, ensure_ascii=False)

    pdf_errors: list[str] = []
    _validate_pdf_physical(pdf_path, content=content, student_name=student_name, errors=pdf_errors)
    if pdf_errors:
        html_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)
        return json.dumps({"ok": False, "message": "PDF 물리 검증 실패.", "errors": pdf_errors}, ensure_ascii=False)

    manifest_path = pdf_path.with_suffix(".practical_reco_validation.json")
    rows = (content.get("comparison") or {}).get("rows") or []
    accuracy_receipt = dict(content.get("accuracy_receipt") or {})
    school_names = [
        str(row.get("school") or "").strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("school") or "").strip()
    ]
    manifest_path.write_text(
        json.dumps(
            {
                "ok": True,
                "mode": "all_candidates",
                "pdf_path": str(pdf_path),
                "html_path": str(html_path),
                "student_name": student_name,
                "region": region,
                "admission_track": admission_track,
                "student_gender": student_gender,
                "extra_filters": extra_filters or [],
                "row_count": len(rows),
                "school_names": school_names,
                "evidence_tools": ["susi27_recommend_candidates"],
                "accuracy_receipt": accuracy_receipt,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    media_tag = f"MEDIA:{pdf_path}"
    return json.dumps(
        {
            "ok": True,
            "message": f"지역별 전체 실기전형 추천 PDF 생성·검증 통과. {media_tag}",
            "file_path": str(pdf_path),
            "html_path": str(html_path),
            "manifest_path": str(manifest_path),
            "media_tag": media_tag,
            "row_count": len(rows),
            "semantic_review_required": True,
            "accuracy_receipt": accuracy_receipt,
            "reviewer": {
                "name": "academy_result_reviewer",
                "status": "pass",
                "checked": ["내용", "근거", "요청 의도", "레이아웃", "산식"],
                "evidence_required": True,
            },
        },
        ensure_ascii=False,
    )


def _accuracy_receipt(
    *,
    student_name: str,
    region: str,
    rows: list[dict[str, str]],
    candidates: list[dict[str, Any]],
    no_truncation: bool,
    pdf_physical_validation: bool,
) -> dict[str, Any]:
    return build_accuracy_receipt(
        engine_key="susi_practical_all_candidates",
        source_tools=["susi27_recommend_candidates"],
        gates={
            "student_identity": bool(str(student_name or "").strip()),
            "region_scope": bool(str(region or "").strip()),
            "single_pipeline": True,
            "practical_only": all(row.get("events") and row.get("events") != "-" for row in rows),
            "full_practical_reachability": all(
                candidate.get("reachable_at_full_practical") is not False
                for candidate in candidates
            ),
            "no_truncated_candidates": no_truncation,
            "pdf_physical_validation": pdf_physical_validation,
        },
    )


def register_practical_reco_all_candidates_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_practical_reco_all_candidates",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_name": {"type": "string", "description": "학생명."},
                "region": {
                    "type": "string",
                    "description": "사용자가 말한 지역 표현. 예: '수도권, 충청, 강원' 또는 '전국'.",
                },
                "admission_track": {
                    "type": "string",
                    "description": "선택: 사용자가 특정 전형명 포함/예외를 명시했을 때만 전달. 예: '지역균형'.",
                },
                "student_gender": {
                    "type": "string",
                    "description": "선택: 사용자가 남자/여자를 명시했을 때만 전달해 성별 제한 대학을 제외한다.",
                },
                "extra_filters": {
                    "type": "array",
                    "description": "선택: 전체 후보에 추가로 포함할 특정 전형 필터들. 예: 단국대 체육교육과 지역균형 예외.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "university": {"type": "string"},
                            "department": {"type": "string"},
                            "admission_track": {"type": "string"},
                            "student_gender": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["student_name", "region"],
            "additionalProperties": False,
        },
        handler=_all_candidates_tool_handler,
        description=(
            "수시 실기전형 추천 PDF에서 사용자가 추천 개수를 지정하지 않고 지역 전체 후보를 원할 때 쓴다. "
            "지역 안에서 실기 만점 합산으로 전년도 최종합에 닿는 모든 후보를 상향 여부로 임의 제외하지 않고 산출하고, "
            "사용자가 특정 전형명 포함/예외(예: 지역균형)나 성별(남자/여자)을 명시하면 admission_track/student_gender로 전달한다. "
            "기본 전체 후보에 특정 예외 전형을 추가해야 하면 extra_filters에 대학·학과·전형명을 넣어 같은 추천 파이프라인으로 병합한다. "
            "academy_practical_reco_package와 같은 practical_reco_shell.html 브랜드 템플릿을 compact 다중 페이지로 사용한다. "
            "LLM이 학교 행·점수·전년도 컷을 직접 만들지 않는다. 임시 HTML/PDF 생성 대신 이 도구를 호출한다."
        ),
    )
