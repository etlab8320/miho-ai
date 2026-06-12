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



# ── 내용 grounding 검증 ──────────────────────────────────────────────
# 스키마는 구조만 본다. "템플릿만 띡 채운" 일반론 리포트(2026-06-12 실사고:
# 인천대 DB 미인용, 3학년 1학기 세특 공백 무대응)를 막으려면 도구가 직접
# 생기부·전형 DB를 읽고 본문이 실제 데이터에 발 딛고 있는지 확인해야 한다.
_CENTRAL_LIFE_DB = Path("~/.miho/life_records/central.sqlite3").expanduser()


def _content_text(content: dict[str, Any]) -> str:
    parts: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, str):
            parts.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(content)
    return " ".join(parts)


def _stage_grade(student_stage: str) -> int | None:
    stage = student_stage.strip().lower()
    for n in (1, 2, 3):
        if stage in (f"grade{n}", f"고{n}"):
            return n
    return None


def _grounding_errors(
    student_name: str,
    student_stage: str,
    content: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    text = _content_text(content)

    # A. 생기부 실제 과목 인용 — 학생을 못 찾으면 검증 불가이므로 건너뛴다.
    subjects: set[str] = set()
    note_grades: set[int] = set()
    if _CENTRAL_LIFE_DB.exists():
        import sqlite3

        with sqlite3.connect(_CENTRAL_LIFE_DB) as db:
            row = db.execute(
                "SELECT id FROM students WHERE name = ? OR name LIKE ? LIMIT 1",
                (student_name, f"%{student_name}%"),
            ).fetchone()
            if row:
                sid = row[0]
                for (subj,) in db.execute(
                    "SELECT DISTINCT subject FROM central_grades WHERE student_id = ?"
                    " UNION SELECT DISTINCT subject FROM central_notes WHERE student_id = ?",
                    (sid, sid),
                ):
                    if subj and len(str(subj).strip()) >= 2:
                        subjects.add(str(subj).strip())
                for (g,) in db.execute(
                    "SELECT DISTINCT grade FROM central_notes WHERE student_id = ?", (sid,)
                ):
                    if g is not None:
                        note_grades.add(int(g))

    if subjects:
        cited = sorted(s for s in subjects if s in text)
        need = min(3, len(subjects))
        if len(cited) < need:
            sample = ", ".join(sorted(subjects)[:8])
            errors.append(
                f"생기부 구체 근거가 부족하다 — 학생의 실제 과목·세특 과목을 {need}개 이상 본문에 "
                f"인용해 일반론이 아닌 이 학생 이야기로 써라 (현재 {len(cited)}개 인용). "
                f"학생 과목 예: {sample}"
            )

        # B. 당해 학년 세특 공백 — 미입력이면 채움 설계(gap_plan)가 리포트의 핵심이어야 한다.
        grade = _stage_grade(student_stage)
        if grade is not None and grade not in note_grades:
            gap = (content.get("strategy_section") or {}).get("gap_plan")
            gap_subjects = (gap or {}).get("subjects") if isinstance(gap, dict) else None
            ok_gap = (
                isinstance(gap, dict)
                and _nonempty(gap.get("title"))
                and isinstance(gap_subjects, list)
                and len(gap_subjects) >= 3
                and all(
                    isinstance(r, dict) and _nonempty(r.get("subject")) and _nonempty(r.get("direction"))
                    for r in gap_subjects
                )
            )
            if not ok_gap:
                errors.append(
                    f"이 학생은 {grade}학년 세특이 아직 입력되지 않았다 — 공백을 채울 설계가 리포트의 핵심이다. "
                    "strategy_section.gap_plan{title, subjects[{subject, direction}] 3개 이상}을 채워라: "
                    "과목마다 어떤 탐구·활동 방향으로 세특을 만들어갈지, 지원 학과와 연결해 구체적으로."
                )

    # C. 대학 전형 DB 수치 인용 — 모집인원이 DB에 있으면 본문에 반드시 등장해야 한다.
    university = content.get("university") or {}
    uni_name = str(university.get("name") or "").strip()
    if uni_name:
        try:
            from plugins.susi_ops.service import lookup_rules

            track = str(university.get("track") or "").strip() or None
            dept = str(university.get("department") or "").strip() or None
            rows = lookup_rules(
                university=uni_name, department=dept, admission_track=track, limit=1
            ).get("rows") or []
            if not rows and dept:
                # 학과명 변경(예: 운동건강학부→스포츠의학부)으로 빗나가면 전형만으로 재조회
                rows = lookup_rules(university=uni_name, admission_track=track, limit=1).get("rows") or []
        except Exception:
            rows = []
        if rows:
            quota = str(rows[0].get("quota") or "").strip()
            quota_num = "".join(ch for ch in quota if ch.isdigit())
            # "4" 같은 숫자 단독은 아무 데나 있다 — "4명"으로 인용됐는지 본다.
            if quota_num and f"{quota_num}명" not in text:
                errors.append(
                    f"전형 DB 수치가 본문에 없다 — {uni_name} 해당 전형 모집인원 '{quota_num}명'을 "
                    "리포트에 인용해라 (susi27_rule_lookup의 admission_meta·quota가 근거다)."
                )
            # 전형 구조(단계 배수·반영비율·수능최저)는 학종 DB의 공식 수치 그대로
            # 전형핵심 표(track_section.rows의 official)에 박혀야 한다 — "서류와
            # 면접 중심" 같은 뭉뚱그림 금지 (2026-06-12 실사고: 인천대 4배수,
            # 70+30 구조가 리포트에 없었다).
            meta = rows[0].get("admission_meta") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (TypeError, ValueError):
                    meta = {}
            track_rows = (content.get("track_section") or {}).get("rows") or []
            officials = " ".join(
                f"{r.get('label') or ''} {r.get('official') or ''}"
                for r in track_rows
                if isinstance(r, dict)
            )
            official_facts: list[str] = []
            stage1 = meta.get("stage1") if isinstance(meta.get("stage1"), dict) else {}
            stage2 = meta.get("stage2") if isinstance(meta.get("stage2"), dict) else {}
            multiple = "".join(ch for ch in str(stage1.get("multiple") or "") if ch.isdigit())
            if multiple:
                rec1 = "".join(ch for ch in str(stage1.get("student_record") or "") if ch.isdigit())
                official_facts.append(
                    f"1단계: 서류(학생부) {rec1 or '?'}% · {multiple}배수 선발"
                )
                if f"{multiple}배수" not in officials:
                    errors.append(
                        f"전형핵심 표에 1단계 선발 배수가 없다 — '{multiple}배수'를 official 값에 그대로 써라."
                    )
            interview = "".join(ch for ch in str(stage2.get("interview") or "") if ch.isdigit())
            if interview and int(interview) > 0:
                carry = "".join(ch for ch in str(stage2.get("other") or "") if ch.isdigit())
                official_facts.append(f"2단계: 1단계 성적 {carry or '?'} + 면접 {interview}")
                if interview not in officials or "면접" not in officials:
                    errors.append(
                        f"전형핵심 표에 2단계 면접 반영비율이 없다 — '면접 {interview}'을 official 값에 그대로 써라."
                    )
            csat = meta.get("minimum_csat") if isinstance(meta.get("minimum_csat"), dict) else {}
            has_min = str(csat.get("has_minimum") or "").strip().lower()
            if has_min in ("", "0", "false", "no", "없음", "n"):
                official_facts.append("수능최저: 없음")
            elif str(csat.get("detail") or "").strip():
                official_facts.append(f"수능최저: {csat['detail']}")
            if errors and official_facts:
                errors.append("DB 공식 전형 구조 (이대로 인용하라): " + " / ".join(official_facts))

        # D. 학종 정성 프로필 — 대학이 서류에서 중점적으로 보는 것. final_ready
        # 프로필이 있는 전형은 그 대학이 원하는 생기부 키워드로 진단해야 한다.
        try:
            from .hakjong_qualitative_tool import lookup_profiles

            prof_rows = lookup_profiles(
                university=uni_name,
                admission_track=str(university.get("track") or "").strip() or None,
                limit=1,
            ).get("profiles") or []
        except Exception:
            prof_rows = []
        if prof_rows:
            prof = prof_rows[0]
            ident = (uni_name, str(university.get("department") or ""), str(university.get("track") or ""))
            keywords = [
                str(k).strip()
                for k in (prof.get("desired_record_keywords") or [])
                if isinstance(k, str) and 1 < len(k.strip()) <= 20
                and not any(part and part in k for part in ident)
            ]
            if keywords:
                cited = [k for k in keywords if k in text]
                if len(cited) < 2:
                    sample = ", ".join(keywords[:10])
                    errors.append(
                        f"{uni_name} {prof.get('admission_track')}의 학종 정성 프로필"
                        "(hakjong_qualitative_profile)이 있는데 본문이 그 평가 기준에 발 딛고 있지 않다 — "
                        f"이 대학이 생기부에서 찾는 키워드를 2개 이상 진단·전략에 녹여라. 키워드: {sample}"
                    )
    return errors


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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

    grounding = _grounding_errors(student_name, student_stage, content)
    if grounding:
        return json.dumps(
            {
                "ok": False,
                "message": "학종 리포트 내용이 데이터에 발 딛고 있지 않다. 아래를 보강해 다시 호출하라. "
                "terminal/execute_code로 PDF를 직접 만드는 것은 금지다.",
                "errors": grounding,
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
                        "final_judgment{body}, checklist{title,bullets[],tags[]}, footnote, "
                        "gap_plan{title, subjects[{subject,direction}]x≥3}(당해 학년 세특 미입력 학생 필수 — "
                        "과목별로 어떤 탐구 방향으로 세특을 채울지 학과와 연결해 설계; 있으면 checklist 대신 렌더된다)}. "
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
