"""Academy tool for packaging validated practical_reco (수시 실기전형 추천) PDFs.

Renders the fixed practical_reco_shell.html template with supplied content JSON,
generates a PDF via Chromium, validates it physically, and promotes the result
to ~/.miho/media_cache/susi_student_record/validated/.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import jinja2

from miho_constants import get_miho_home

from .brand_assets import academy_brand_logo_src
from . import hakjong_report_contract as _contract
from .pdf_autocorrect import autocorrect as _autocorrect
from .hakjong_report_contract import BRAND_TEXT
from .practical_reco_recalc import validate_recalculated_scores
from .practical_reco_schema import validate_content
from .report_fonts import report_font_css
from .student_card_capture import find_browser_executable


_KST = ZoneInfo("Asia/Seoul")
_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "practical_reco_shell.html"
_BRAND_TEXT = BRAND_TEXT

_RECOMMENDATION_EVIDENCE_TOOL = "susi27_recommend_candidates"


def _kst_today() -> str:
    return datetime.now(_KST).date().isoformat()


def _render_html(content: dict[str, Any]) -> str:
    """Render the fixed shell template with the given content dict."""
    template_src = _TEMPLATE_PATH.read_text(encoding="utf-8")
    env = jinja2.Environment(
        loader=jinja2.BaseLoader(),
        autoescape=jinja2.select_autoescape(["html"]),
        # 스키마가 필수 필드를 보장하고, 선택 필드(avg_grade 등)는 비어도 렌더돼야 한다 —
        # StrictUndefined는 스키마 통과 후 렌더 단계에서 터져 에이전트를 막다른 길로 몰았다
        # (2026-06-12 실사고: 6회 반려 끝에 terminal 손제작 PDF로 도주).
        undefined=jinja2.ChainableUndefined,
    )
    template = env.from_string(template_src)
    return template.render(
        font_css=report_font_css(),
        logo_src=academy_brand_logo_src() or "",
        brand_text=_BRAND_TEXT,
        report_date=_kst_today(),
        data=content,
    )


def _chromium_print_to_pdf(html_path: Path, pdf_path: Path) -> None:
    """Render html_path to A4 PDF via Chromium headless --print-to-pdf."""
    browser = find_browser_executable()
    if browser is None:
        raise RuntimeError(
            "PDF 생성에 필요한 브라우저를 찾지 못했다. Chrome 또는 Edge 설치가 필요하다."
        )
    import sys

    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        html_path.as_uri(),
    ]
    if sys.platform.startswith("linux"):
        command.insert(1, "--no-sandbox")

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"PDF 생성이 시간 안에 끝나지 않았다: {exc}") from exc

    if result.returncode != 0 or not pdf_path.exists():
        detail = (result.stderr or result.stdout or "").strip()
        suffix = f" ({detail[:200]})" if detail else ""
        raise RuntimeError(f"Chromium PDF 생성 실패.{suffix}")


def _validate_pdf_physical(
    pdf_path: Path,
    *,
    content: dict[str, Any] | None = None,
    student_name: str,
    errors: list[str],
) -> None:
    """Physical PDF checks: portrait, brand text, student name."""
    # 디스코드 첨부 한도(10MB) 가드 — 사장님 지시(2026-06-12): 한도를 넘는 PDF는
    # 만들어도 전달이 안 되므로(413 Payload Too Large 실사고) 승격 자체를 거부한다.
    size_mb = pdf_path.stat().st_size / 1_048_576
    if size_mb > 9.0:
        errors.append(
            f"PDF가 {size_mb:.1f}MB로 디스코드 첨부 한도(약 10MB)를 넘는다 — "
            "섹션/문단 분량을 줄여 9MB 아래로 다시 만들어라."
        )
    info = _contract._pdf_info(pdf_path)
    if info.get("error"):
        errors.append(f"PDF 정보를 읽을 수 없다: {info['error']}")
        return

    width = float(info.get("width") or 0)
    height = float(info.get("height") or 0)
    if width <= 0 or height <= 0:
        errors.append("PDF 페이지 크기를 파싱할 수 없다.")
    elif width > height:
        errors.append("PDF가 가로 방향이다. A4 세로여야 한다.")

    text_result = _contract._pdf_text(pdf_path)
    if text_result.get("error"):
        # pdftotext not available — skip text checks (only a warning)
        return
    body = str(text_result.get("text") or "")
    if content is not None:
        _contract.truncation_errors(content, body, errors)
    if _BRAND_TEXT not in body:
        errors.append(f"PDF 본문에 브랜드 텍스트가 없다: {_BRAND_TEXT}")
    if student_name and student_name not in body:
        errors.append(f"PDF 본문에 학생명이 없다: {student_name}")


def _check_evidence_warnings(evidence_tools: list[str]) -> list[str]:
    """Return warnings when the single recommendation pipeline is absent."""
    warnings: list[str] = []
    if _RECOMMENDATION_EVIDENCE_TOOL not in evidence_tools:
        warnings.append(
            "수시 추천 단일 파이프라인(susi27_recommend_candidates)이 evidence_tools에 없다. "
            "환산점수·전년도 수치는 반드시 susi27_recommend_candidates 후보 결과에서 가져와야 한다."
        )
    return warnings


def _practical_reco_package_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    student_name = str(payload.get("student_name") or "").strip()
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

    # Step 0: 텍스트 길이 상한으로 페이지 잘림 자동 방지. comparison.rows/schools는
    # 환산점수 핵심 데이터라 빈칸 행을 제거하지 않는다(빈칸=반려 유지). 학교 카드
    # 본문 등 긴 서술만 절단된다.
    content = _autocorrect(content, table_specs=[], char_limit=_contract.MAX_VISIBLE_TEXT_SEGMENT_CHARS)

    # Step 1: schema + quality validation
    ok, schema_errors = validate_content(content, evidence_tools=evidence_tools)
    if not ok:
        return json.dumps(
            {
                "ok": False,
                "message": "실기전형 추천 리포트 내용 검증 실패. 아래 항목을 수정한 뒤 이 도구를 다시 호출하라. "
                "terminal/execute_code로 PDF를 직접 만드는 것은 금지 — 브랜드 템플릿과 검증을 우회하게 된다.",
                "errors": schema_errors,
                "warnings": [],
                "checks": {},
            },
            ensure_ascii=False,
        )

    recalc_ok, recalc_errors, recalc_checks = validate_recalculated_scores(student_name, content)
    if not recalc_ok:
        return json.dumps(
            {
                "ok": False,
                "message": "실기전형 추천 리포트 공식 산식 재검산 실패. PDF 숫자는 susi27 산출값과 일치해야 한다.",
                "errors": recalc_errors,
                "warnings": [],
                "checks": recalc_checks,
            },
            ensure_ascii=False,
        )

    warnings = _check_evidence_warnings(evidence_tools)

    # Step 2: render HTML
    try:
        html = _render_html(content)
    except jinja2.UndefinedError as exc:
        return json.dumps(
            {"ok": False, "errors": [f"템플릿 렌더링 실패 — 필드 누락: {exc}"], "warnings": warnings, "checks": {}},
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {"ok": False, "errors": [f"템플릿 렌더링 오류: {exc}"], "warnings": warnings, "checks": {}},
            ensure_ascii=False,
        )

    # Step 3: Chromium PDF generation
    out_dir = get_miho_home() / "media_cache" / "susi_student_record" / "validated"
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = _safe_stem(student_name, "실기전형추천")
    packaged_html = out_dir / f"{stem}.html"
    packaged_pdf = out_dir / f"{stem}.pdf"
    packaged_html, packaged_pdf = _unique_pair(packaged_html, packaged_pdf)

    packaged_html.write_text(html, encoding="utf-8")

    try:
        _chromium_print_to_pdf(packaged_html, packaged_pdf)
    except RuntimeError as exc:
        packaged_html.unlink(missing_ok=True)
        return json.dumps(
            {"ok": False, "errors": [str(exc)], "warnings": warnings, "checks": {}},
            ensure_ascii=False,
        )

    # Step 4: physical PDF validation
    pdf_errors: list[str] = []
    _validate_pdf_physical(packaged_pdf, content=content, student_name=student_name, errors=pdf_errors)
    if pdf_errors:
        packaged_html.unlink(missing_ok=True)
        packaged_pdf.unlink(missing_ok=True)
        return json.dumps(
            {
                "ok": False,
                "message": "PDF 물리 검증 실패.",
                "errors": pdf_errors,
                "warnings": warnings,
                "checks": {},
            },
            ensure_ascii=False,
        )

    # Step 5: write manifest
    school_names = [r.get("school", "") for r in ((content.get("comparison") or {}).get("rows") or []) if isinstance(r, dict)]
    manifest_path = packaged_pdf.with_suffix(".practical_reco_validation.json")
    manifest_path.write_text(
        json.dumps(
            {
                "ok": True,
                "pdf_path": str(packaged_pdf),
                "html_path": str(packaged_html),
                "student_name": student_name,
                "school_names": school_names,
                "evidence_tools": evidence_tools,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    media_tag = f"MEDIA:{packaged_pdf}"
    return json.dumps(
        {
            "ok": True,
            "message": f"실기전형 추천 PDF 생성·검증 통과. {media_tag}",
            "file_path": str(packaged_pdf),
            "html_path": str(packaged_html),
            "manifest_path": str(manifest_path),
            "media_tag": media_tag,
            "warnings": warnings,
            "checks": {
                "student_name": student_name,
                "school_names": school_names,
            },
        },
        ensure_ascii=False,
    )


def register_practical_reco_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_practical_reco_package",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "description": "학생명. PDF 표지와 본문에 삽입된다.",
                },
                "evidence_tools": {
                    "type": "array",
                    "description": (
                        "실제 근거 조회에 사용한 도구/소스 이름. "
                        "수시 추천이면 susi27_recommend_candidates가 반드시 포함되어야 한다 "
                        "(룰/계산 도구를 따로 조립한 결과는 경고)."
                    ),
                    "items": {"type": "string"},
                },
                "content": {
                    "type": "object",
                    "description": (
                        "리포트 내용 JSON. 최종 선택한 추천 학교 최대 8개를 한 부(comparison.rows 단일 표)에 담는다. "
                        "필수 키: student{name, avg_grade, basis_label} · title_lines[] · "
                        "badge{line1, line2} · "
                        "cover{pills[], key_judgment{headline, body}, metrics[{label,value}]x3} · "
                        "comparison{note, rows[{school, department, track, converted, max_total, "
                        "first_cut, final_cut, verdict(상향|적정)}]} — 선택 추천 학교를 rows에 넣고 "
                        "각 행에 내신환산(converted)·실기만점합산(max_total)·전년도 최초/최종합(first_cut/final_cut)을 반드시 채운다 · "
                        "final{cards[{title,body}], callout{title, paragraphs[]}, tags[]} · "
                        "footnote. "
                        "학교별 상세 페이지는 없다 — 전체를 comparison.rows 한 표로 보여주므로 schools 키는 불필요. "
                        "환산점수·전년도 수치는 susi27_recommend_candidates 후보 결과값만 사용. "
                        "로고·푸터·브랜딩은 템플릿이 보장하므로 여기에 넣지 않는다."
                    ),
                },
            },
            "required": ["student_name", "evidence_tools", "content"],
            "additionalProperties": False,
        },
        handler=_practical_reco_package_tool_handler,
        description=(
            "수시 실기전형 추천 결과를 고정 템플릿 PDF로 만든다. "
            "사용자가 개수를 지정하지 않고 지역 전체 후보를 원하면 academy_practical_reco_all_candidates를 쓴다. "
            "추천 후보와 환산점수·전년도 수치는 susi27_recommend_candidates 단일 파이프라인 결과값만 사용. "
            "susi27_rule_lookup/susi27_score_calculate를 손으로 조립해 추천 목록을 만들지 않는다. "
            "상향은 (내신환산+실기만점) ≥ 전년도 최종합 학교만 — 만점으로도 못 닿는 학교는 절대 싣지 않는다. "
            "단, 이 선별 과정은 리포트에 쓰지 않는다: 제외한 학교 이름, 검토 학교 수, '제외했다/걸렀다' 류 "
            "과정 설명은 전부 금지 — 리포트는 추천하는 학교 이야기만 한다. "
            "전년도 대비 전형 구조(만점·종목·비중)가 바뀐 학교는 해당 학교 카드의 caution에 "
            "'작년에는 어떻게 반영됐는지'(작년 비중/만점/종목 — susi26_rule_lookup 수치)와 "
            "'올해는 어떻게 바뀌었는지'를 대조해서 학부모가 이해할 수 있게 적는다 "
            "(예: '작년엔 내신30:실기70(만점700)이었지만 올해는 20:80(만점800)이라 작년 점수와 직접 비교는 어렵습니다'). "
            "각 학교의 지역(광역)을 비교표 전형 칸이나 학교 카드 track 문구에 함께 표기한다 (예: '실기우수자 · 충남'). "
            "1단계 선발이 있는 전형은 1단계(등급) 통과 가능성을 카드에 명시하고, "
            "전공실기/선택 종목(구기 등)이 있는 학교는 어느 종목 트랙 기준 추천인지 적고 학생이 가능한 종목인지 상기시킨다. "
            "톤은 선생님이 학생·학부모에게 설명하듯 자연스럽게. "
            "검증 통과한 PDF만 ~/.miho/media_cache/susi_student_record/validated 로 승격하고 "
            "media_tag를 반환한다."
        ),
    )


def _safe_stem(*parts: str) -> str:
    raw = "_".join(part.strip() for part in parts if part and part.strip())
    clean = re.sub(r"[^\w가-힣.-]+", "_", raw, flags=re.UNICODE).strip("_.")
    return clean[:120] or "practical_reco_report"


def _unique_pair(html_path: Path, pdf_path: Path) -> tuple[Path, Path]:
    """Return collision-free (html_path, pdf_path) pair."""
    stem = html_path.stem
    parent = html_path.parent
    counter = 2
    candidate_html = html_path
    candidate_pdf = pdf_path
    while candidate_html.exists() or candidate_pdf.exists():
        candidate_html = parent / f"{stem}_{counter}.html"
        candidate_pdf = parent / f"{stem}_{counter}.pdf"
        counter += 1
    return candidate_html, candidate_pdf
