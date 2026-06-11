"""Academy tool for packaging validated hakjong PDFs for delivery.

T3: New flow — LLM supplies content JSON; this tool renders the fixed
shell template, generates the PDF via Chromium, validates it, and
promotes the result. No html_path/pdf_path/page_image_paths/contact_sheet
inputs.
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
from .hakjong_report_contract import BRAND_TEXT
from .hakjong_report_schema import validate_content
from .report_fonts import report_font_css
from .student_card_capture import find_browser_executable


_KST = ZoneInfo("Asia/Seoul")
_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "hakjong_report_shell.html"
_BRAND_TEXT = BRAND_TEXT


def _kst_today() -> str:
    return datetime.now(_KST).date().isoformat()


def _render_html(content: dict[str, Any]) -> str:
    """Render the fixed shell template with the given content dict."""
    template_src = _TEMPLATE_PATH.read_text(encoding="utf-8")
    env = jinja2.Environment(
        loader=jinja2.BaseLoader(),
        autoescape=jinja2.select_autoescape(["html"]),
        undefined=jinja2.StrictUndefined,
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
    student_name: str,
    university_names: list[str],
    errors: list[str],
) -> None:
    """Physical PDF checks: portrait, brand text, student name, university names."""
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
    if _BRAND_TEXT not in body:
        errors.append(f"PDF 본문에 브랜드 텍스트가 없다: {_BRAND_TEXT}")
    if student_name and student_name not in body:
        errors.append(f"PDF 본문에 학생명이 없다: {student_name}")
    for uni in university_names:
        if uni and uni not in body:
            errors.append(f"PDF 본문에 대학명이 없다: {uni}")


def _university_names_from_content(content: dict[str, Any]) -> list[str]:
    """Extract university name(s) from content dict.

    The new template structure is one university per report (`university.name`).
    """
    university = content.get("university")
    if isinstance(university, dict):
        name = str(university.get("name") or "").strip()
        if name:
            return [name]
    return []


def _hakjong_report_package_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    student_name = str(payload.get("student_name") or "").strip()
    student_stage = str(payload.get("student_stage") or "").strip()
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

    # T3 step 1: schema + quality validation
    ok, schema_errors = validate_content(
        content,
        student_stage=student_stage,
        evidence_tools=evidence_tools,
    )
    if not ok:
        return json.dumps(
            {
                "ok": False,
                "message": "학종 리포트 내용 검증 실패. 아래 항목을 수정한 뒤 다시 호출하라.",
                "errors": schema_errors,
                "warnings": [],
                "checks": {},
            },
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

    packaged_html.write_text(html, encoding="utf-8")

    try:
        _chromium_print_to_pdf(packaged_html, packaged_pdf)
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
    manifest_path.write_text(
        json.dumps(
            {
                "ok": True,
                "pdf_path": str(packaged_pdf),
                "html_path": str(packaged_html),
                "student_name": student_name,
                "university_names": university_names,
                "student_stage": student_stage,
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
            "message": f"학종 PDF 생성·검증 통과. {media_tag}",
            "file_path": str(packaged_pdf),
            "html_path": str(packaged_html),
            "manifest_path": str(manifest_path),
            "media_tag": media_tag,
            "checks": {
                "student_name": student_name,
                "university_names": university_names,
                "student_stage": student_stage,
            },
        },
        ensure_ascii=False,
    )


def register_hakjong_report_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_hakjong_report_package",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "description": "학생명. PDF 표지와 본문에 삽입된다.",
                },
                "student_stage": {
                    "type": "string",
                    "description": (
                        "학생 상태. grade1/grade2/grade3/graduate 또는 고1/고2/고3/N수생. "
                        "단계별 섹션 필수 여부와 근거 도구 요건을 결정한다."
                    ),
                },
                "evidence_tools": {
                    "type": "array",
                    "description": (
                        "실제 근거 조회에 사용한 도구/소스 이름. "
                        "3학년/N수생은 life_record_* 계열이 필수다."
                    ),
                    "items": {"type": "string"},
                },
                "content": {
                    "type": "object",
                    "description": (
                        "리포트 내용 JSON. 리포트 1부 = (학생, 대학, 전형) 1조합 — 여러 학교 추천이면 학교마다 따로 호출한다. "
                        "필수 키: student{name} · university{name, department, college, track} · "
                        "badge{grade(예: '평가등급 C'), action(예: '보완 후 검토')} · title_lines[](표지 제목 1~2줄) · "
                        "cover{pills[](전형 요점 칩), key_judgment{headline, body}, metrics[{label,value}]x3(전년도 평균/최저등급, 학생 평균등급)} · "
                        "track_section{heading, info_cards[{label,value,sub}]x3, rows[{label,official,judgment}], "
                        "strong_points{title,bullets[]}, caution_points{title,bullets[]}, footnote} · "
                        "diagnosis_section{heading, strength{headline,body}, risk{headline,body}, "
                        "rows[{area,record,interpretation,check}], gauges[{label,level,note,tone(orange|blue|red),percent}]x3, footnote} · "
                        "strategy_section{heading, actions[{title,body}]x4, interview_rows[{question,point}], "
                        "final_judgment{body}, checklist{title,bullets[],tags[]}, footnote}. "
                        "수치(전년도 컷·등급)는 susi27_rule_lookup의 admission_meta/admission_result_26과 생기부 성적에서 가져온 실제 값만 쓴다. "
                        "로고·푸터·브랜딩은 템플릿이 보장하므로 여기에 넣지 않는다."
                    ),
                },
            },
            "required": ["student_name", "student_stage", "evidence_tools", "content"],
            "additionalProperties": False,
        },
        handler=_hakjong_report_package_tool_handler,
        description=(
            "내용 JSON만 주면 껍데기(로고/푸터/브랜딩)는 고정 템플릿이 보장한다. "
            "학교별 학종 패키지(susi27_rule_lookup)와 생기부(life_record_lookup/search/summary)를 "
            "근거로 섹션 내용을 작성하라. "
            "글쓰기 톤: 학원 선생님이 학생과 학부모 앞에서 상담하며 설명하는 따뜻하고 자연스러운 말투로 — "
            "딱딱한 보고서체 나열 금지, 학생 이름을 부르며 말을 거는 문장으로. "
            "내부 판단 과정이나 배제 설명('OO 분야는 제외하고' 류)은 리포트에 쓰지 말고, "
            "요청받은 학교·학과에 대한 내용만 직접적으로 쓴다. "
            "검증 통과한 PDF만 ~/.miho/media_cache/susi_student_record/validated 로 승격하고 "
            "media_tag를 반환한다."
        ),
    )


def _safe_stem(*parts: str) -> str:
    raw = "_".join(part.strip() for part in parts if part and part.strip())
    clean = re.sub(r"[^\w가-힣.-]+", "_", raw, flags=re.UNICODE).strip("_.")
    return clean[:120] or "hakjong_report"


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
