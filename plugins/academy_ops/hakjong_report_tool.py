"""Academy tool for packaging validated hakjong PDFs for delivery.

T3: New flow — LLM supplies content JSON; this tool renders the fixed
shell template, generates the PDF via Chromium, validates it, and
promotes the result. No html_path/pdf_path/page_image_paths/contact_sheet
inputs.
"""

from __future__ import annotations

import json
from typing import Any

import jinja2

from miho_constants import get_miho_home

from . import hakjong_report_contract as _contract
from .pdf_autocorrect import autocorrect as _autocorrect
from .hakjong_live_research import apply_live_research_enrichment as _apply_live_research_enrichment
from .hakjong_manifest import build_hakjong_manifest, collect_pdf_checks
from .hakjong_grounding import apply_gap_plan_grounding
from .hakjong_grounding_checks import grounding_errors as _grounding_errors
from .hakjong_record_context import STAGE_KO as _STAGE_KO
from .hakjong_record_context import infer_stage_from_birth as _infer_stage_from_birth
from .hakjong_report_registration import register_hakjong_report_tool as _register_hakjong_report_tool
from .hakjong_report_rendering import render_html as _render_html
from .hakjong_report_rendering import render_pdf_fit as _render_pdf_fit
from .hakjong_report_rendering import _TEMPLATE_PATH
from .hakjong_report_rendering import safe_stem as _safe_stem
from .hakjong_report_rendering import unique_pair as _unique_pair
from .hakjong_report_rendering import university_names_from_content as _university_names_from_content
from .hakjong_report_rendering import validate_pdf_physical as _validate_pdf_physical
from .hakjong_report_schema import validate_content_with_checks
from .hakjong_stage_contract import normalize_student_stage





def _hakjong_report_package_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    student_name = str(payload.get("student_name") or "").strip()
    student_stage = str(payload.get("student_stage") or "").strip()

    # 단계는 미호의 추측이 아니라 생기부 생년이 결정한다(사장님 2026-06-13).
    # 생년으로 판정되면 그게 권위 있는 stage — 미호 자기신고를 덮어쓰고, 모순이면
    # 경고를 남겨 미호가 stage 인자를 맞춰 재호출하게 한다.
    inferred_stage = _infer_stage_from_birth(student_name)
    stage_conflict: tuple[str, str] | None = None
    if inferred_stage:
        reported = normalize_student_stage(student_stage)
        if reported and reported != inferred_stage:
            stage_conflict = (reported, inferred_stage)
        student_stage = inferred_stage

    content = payload.get("content")
    if isinstance(content, str):
        # LLM이 JSON 문자열로 보내는 경우가 흔하다 — 파싱해서 받아준다.
        # dict 강제로 반려하면 에이전트가 도구를 포기하고 PDF를 손제작하는
        # 우회(2026-06-12 13MB 첨부 실패 사고)로 빠진다.
        try:
            content = json.loads(content)
        except (TypeError, ValueError):
            pass
    evidence_tools = [str(t) for t in (payload.get("evidence_tools") or [])]

    if not isinstance(content, dict):
        return json.dumps(
            {"ok": False, "errors": ["content는 dict(또는 JSON 문자열)여야 한다. JSON 객체 형태로 다시 보내라."], "warnings": [], "checks": {}},
            ensure_ascii=False,
        )

    # T3 step 0: 기계적 결함 자동 보정 — 빈 표 행 제거 + 텍스트 길이 상한.
    # 빈칸/페이지 잘림으로 반려하던 왕복(2026-06-13 서연 5분+ 사고)을 없앤다.
    content = _autocorrect(
        content,
        table_specs=[
            ("track_section.rows", ("label", "official", "judgment")),
            ("diagnosis_section.rows", ("area", "record", "interpretation", "check")),
            ("diagnosis_section.gauges", ("label", "level", "note")),
            ("strategy_section.interview_rows", ("question", "point")),
            # gap_plan.subjects는 분야별 1페이지 설계 구조(field/current_record/school_direction/steps)라
            # 빈칸-행 autocorrect 대상이 아니다 — grounding이 구조를 직접 검증한다.
        ],
        char_limit=_contract.MAX_VISIBLE_TEXT_SEGMENT_CHARS,
    )

    # T3 step 0.5: 학종 DB의 공식 프로필에 붙은 교수 연구/최신뉴스 캐시를
    # 리포트 본문에 자동 주입한다. 미호가 source bundle을 읽고도 PDF content에
    # 반영하지 않는 사고를 막기 위한 안전장치다.
    matched_profile: dict[str, Any] | None = None
    try:
        from .hakjong_qualitative_tool import lookup_profiles

        university_obj = content.get("university")
        university = university_obj if isinstance(university_obj, dict) else {}
        prof_rows = lookup_profiles(
            university=str(university.get("name") or "").strip() or None,
            department=str(university.get("department") or "").strip() or None,
            admission_track=str(university.get("track") or "").strip() or None,
            limit=1,
        ).get("profiles") or []
        matched_profile = prof_rows[0] if prof_rows else None
        if not matched_profile and university.get("name") and university.get("department"):
            # Some official-rule rows are not final_ready in the qualitative DB yet
            # (e.g. newly added 예체능서류 tracks). Still run live research so the
            # report can use 교수진/논문/뉴스 flow rather than dropping to generic copy.
            from .hakjong_live_research import live_research_bundle
            from .hakjong_qualitative_tool import _db_path

            live_research = live_research_bundle(
                _db_path(),
                university=str(university.get("name") or "").strip(),
                department=str(university.get("department") or "").strip(),
                admission_track=str(university.get("track") or "").strip(),
            )
            if live_research:
                matched_profile = {"live_research": live_research}
    except Exception:
        matched_profile = None
    live_research_applied = _apply_live_research_enrichment(content, matched_profile)
    live_research_applied = apply_gap_plan_grounding(content, matched_profile) or live_research_applied

    # T3 step 1: schema + quality validation
    ok, schema_errors, schema_checks = validate_content_with_checks(
        content,
        student_stage=student_stage,
        evidence_tools=evidence_tools,
    )
    if not ok:
        return json.dumps(
            _repairable_rejection(
                "학종 리포트 내용 검증 실패. 아래 항목을 수정한 뒤 같은 턴에서 이 도구를 다시 호출하라.",
                schema_errors,
                schema_checks,
            ),
            ensure_ascii=False,
        )

    grounding = _grounding_errors(student_name, student_stage, content)
    if stage_conflict:
        reported, inferred = stage_conflict
        grounding.insert(
            0,
            f"학생 단계가 어긋난다 — 미호가 보낸 단계는 {_STAGE_KO.get(reported, reported)}인데 "
            f"생기부 생년으로는 {_STAGE_KO.get(inferred, inferred)}다. 생년이 정답이니 "
            f"student_stage를 '{inferred}'로 고치고, 그 단계에 맞는 내용으로 다시 호출하라"
            + (" (N수생/졸업생은 세특 설계 금지 — 가능성 판단 + 면접 정리만)."
               if inferred == "graduate" else ".")
        )
    if grounding:
        return json.dumps(
            _repairable_rejection(
                "학종 리포트 내용이 데이터에 발 딛고 있지 않다. 아래를 보강해 같은 턴에서 이 도구를 다시 호출하라. "
                "terminal/execute_code로 PDF를 직접 만드는 것은 금지다.",
                grounding,
                {},
            ),
            ensure_ascii=False,
        )

    # T3 step 2: render HTML
    try:
        html = _render_html(content)
    except jinja2.UndefinedError as exc:
        return json.dumps(
            {"ok": False, "errors": [f"템플릿 렌더링 실패 — 필드 누락: {exc}"], "warnings": [], "checks": {}},
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {"ok": False, "errors": [f"템플릿 렌더링 오류: {exc}"], "warnings": [], "checks": {}},
            ensure_ascii=False,
        )

    # T3 step 3: Chromium PDF generation (write HTML to temp, generate PDF)
    out_dir = get_miho_home() / "media_cache" / "susi_student_record" / "validated"
    out_dir.mkdir(parents=True, exist_ok=True)

    university_names = _university_names_from_content(content)
    department = str((content.get("university") or {}).get("department") or "").strip()
    stem = _safe_stem(student_name, university_names[0] if university_names else "", department)
    packaged_html = out_dir / f"{stem}.html"
    packaged_pdf = out_dir / f"{stem}.pdf"

    # resolve collision
    packaged_html, packaged_pdf = _unique_pair(packaged_html, packaged_pdf)

    try:
        # 페이지가 4장을 넘치면 compact 단계를 올려 한 장에 다시 맞춘다(footer는 하단 고정).
        html = _render_pdf_fit(content, packaged_html, packaged_pdf, student_stage=student_stage)
    except RuntimeError as exc:
        packaged_html.unlink(missing_ok=True)
        return json.dumps(
            {"ok": False, "errors": [str(exc)], "warnings": [], "checks": {}},
            ensure_ascii=False,
        )

    # T3 step 4: physical PDF validation
    pdf_errors: list[str] = []
    _validate_pdf_physical(
        packaged_pdf,
        content=content,
        student_name=student_name,
        university_names=university_names,
        errors=pdf_errors,
    )
    if pdf_errors:
        packaged_html.unlink(missing_ok=True)
        packaged_pdf.unlink(missing_ok=True)
        return json.dumps(
            {
                "ok": False,
                "message": "PDF 물리 검증 실패.",
                "errors": pdf_errors,
                "warnings": [],
                "checks": {},
            },
            ensure_ascii=False,
        )

    # T3 step 5: write manifest
    manifest_path = packaged_pdf.with_suffix(".hakjong_validation.json")
    live_research_bundle_path = (
        str((matched_profile or {}).get("live_research", {}).get("bundle_path"))
        if isinstance((matched_profile or {}).get("live_research"), dict)
        else ""
    )
    manifest = build_hakjong_manifest(
        pdf_path=packaged_pdf,
        html_path=packaged_html,
        student_name=student_name,
        university_names=university_names,
        student_stage=student_stage,
        schema_checks=schema_checks,
        pdf_checks=collect_pdf_checks(packaged_pdf),
        live_research_applied=live_research_applied,
        live_research_bundle_path=live_research_bundle_path,
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    media_tag = f"MEDIA:{packaged_pdf}"
    return json.dumps(
        {
            "ok": True,
            "message": f"학종 PDF 생성·검증 통과. {media_tag}",
            "file_path": str(packaged_pdf),
            "html_path": str(packaged_html),
            "manifest_path": str(manifest_path),
            "media_tag": media_tag,
            "checks": manifest["checks"],
            "semantic_review_required": True,
            "reviewer": {
                "name": "academy_result_reviewer",
                "status": "pass",
                "checked": ["내용", "근거", "요청 의도", "레이아웃", "산식"],
                "evidence_required": True,
            },
        },
        ensure_ascii=False,
    )



def register_hakjong_report_tool(ctx: Any) -> None:
    _register_hakjong_report_tool(ctx, _hakjong_report_package_tool_handler)


def _repairable_rejection(message: str, errors: list[str], checks: dict[str, Any]) -> dict[str, Any]:
    """Tell the agent this is a repair loop, not a user-facing stopping point."""
    return {
        "ok": False,
        "retry_required": True,
        "final_response_allowed": False,
        "message": message,
        "agent_instruction": (
            "이 결과를 사용자에게 최종 보고하지 마라. errors를 체크리스트로 삼아 content를 보강하고 "
            "같은 턴에서 academy_hakjong_report_package를 다시 호출하라. 기존 PDF 재첨부나 임시 PDF 생성 금지."
        ),
        "errors": errors,
        "warnings": [],
        "checks": checks,
    }
