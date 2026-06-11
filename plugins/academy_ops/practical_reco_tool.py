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
from .hakjong_report_contract import BRAND_TEXT
from .practical_reco_schema import validate_content
from .report_fonts import report_font_css
from .student_card_capture import find_browser_executable


_KST = ZoneInfo("Asia/Seoul")
_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "practical_reco_shell.html"
_BRAND_TEXT = BRAND_TEXT

_SUSI_EVIDENCE_PREFIXES = ("susi27_", "jungsi_")


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
    errors: list[str],
) -> None:
    """Physical PDF checks: portrait, brand text, student name."""
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


def _check_evidence_warnings(evidence_tools: list[str]) -> list[str]:
    """Return warnings (not errors) when susi27_* or jungsi_* tools are absent."""
    warnings: list[str] = []
    has_susi = any(
        any(t.startswith(prefix) for prefix in _SUSI_EVIDENCE_PREFIXES)
        for t in evidence_tools
    )
    if not has_susi:
        warnings.append(
            "수시 산출 근거 도구(susi27_* 또는 jungsi_*)가 evidence_tools에 없다. "
            "환산점수·전년도 수치는 반드시 susi27_score_calculate/susi27_rule_lookup 산출값을 써야 한다."
        )
    return warnings


def _practical_reco_package_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    student_name = str(payload.get("student_name") or "").strip()
    content = payload.get("content")
    evidence_tools = [str(t) for t in (payload.get("evidence_tools") or [])]

    if not isinstance(content, dict):
        return json.dumps(
            {"ok": False, "errors": ["content는 dict여야 한다."], "warnings": [], "checks": {}},
            ensure_ascii=False,
        )

    # Step 1: schema + quality validation
    ok, schema_errors = validate_content(content, evidence_tools=evidence_tools)
    if not ok:
        return json.dumps(
            {
                "ok": False,
                "message": "실기전형 추천 리포트 내용 검증 실패. 아래 항목을 수정한 뒤 다시 호출하라.",
                "errors": schema_errors,
                "warnings": [],
                "checks": {},
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
    _validate_pdf_physical(packaged_pdf, student_name=student_name, errors=pdf_errors)
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
    school_names = [s.get("name", "") for s in (content.get("schools") or []) if isinstance(s, dict)]
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
                        "susi27_score_calculate / susi27_rule_lookup 등 수시 산출 도구가 "
                        "최소 하나 이상 포함되어야 한다 (없으면 경고)."
                    ),
                    "items": {"type": "string"},
                },
                "content": {
                    "type": "object",
                    "description": (
                        "리포트 내용 JSON. 추천 학교 N개를 한 부에 담는다. "
                        "필수 키: student{name, avg_grade, basis_label} · title_lines[] · "
                        "badge{line1, line2} · "
                        "cover{pills[], key_judgment{headline, body}, metrics[{label,value}]x3} · "
                        "comparison{note, rows[{school, department, track, converted, max_total, "
                        "first_cut, final_cut, verdict(상향|적정)}]} · "
                        "schools[{name, department, track, verdict, numbers[{label,value}], "
                        "events[], rationale_paragraphs[], caution}] · "
                        "final{cards[{title,body}], callout{title, paragraphs[]}, tags[]} · "
                        "footnote. "
                        "schools 길이 == comparison.rows 길이. "
                        "환산점수·전년도 수치는 susi27_score_calculate/susi27_rule_lookup 산출값만 사용. "
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
            "환산점수·전년도 수치는 susi27_score_calculate/susi27_rule_lookup 산출값만 사용. "
            "상향은 (내신환산+실기만점) ≥ 전년도 최종합 학교만 — 만점으로도 못 닿는 학교는 절대 싣지 않는다. "
            "단, 이 선별 과정은 리포트에 쓰지 않는다: 제외한 학교 이름, 검토 학교 수, '제외했다/걸렀다' 류 "
            "과정 설명은 전부 금지 — 리포트는 추천하는 학교 이야기만 한다. "
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
