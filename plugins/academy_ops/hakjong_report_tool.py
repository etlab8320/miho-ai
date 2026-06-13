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
from .pdf_autocorrect import autocorrect as _autocorrect
from .hakjong_report_contract import BRAND_TEXT
from .hakjong_report_schema import validate_content
from .hakjong_stage_contract import normalize_student_stage
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
    content: dict[str, Any] | None = None,
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
    if content is not None:
        _contract.truncation_errors(content, body, errors)
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

_STAGE_KO = {"grade1": "고1", "grade2": "고2", "grade3": "고3", "graduate": "N수생/졸업"}

# 교과 분야 — 생기부엔 학생이 앞으로 무슨 과목을 들을지 안 나온다(사장님 2026-06-13).
# 그래서 세특 조언은 세부 과목이 아니라 분야 단위로 한다. 학생이 이미 기록을 가진
# 세부 과목만 그 과목에서 디벨롭한다.
_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    # 영어를 국어보다 먼저 본다 — '영어 독해와 작문'이 '작문'(국어 키워드)으로 새지 않게.
    "영어": ("영어", "영독", "영어권"),
    "국어": ("국어", "문학", "독서", "화법", "작문", "언어"),
    "수학": ("수학", "미적", "확률", "통계", "기하", "대수"),
    "과학": ("과학", "물리", "화학", "생명", "지구", "융합"),
    "사회": ("사회", "지리", "역사", "한국사", "세계사", "정치", "법", "경제", "윤리", "사상", "문화", "탐구"),
    "체육": ("체육", "운동", "스포츠"),
    "예술": ("음악", "미술", "연주", "창작", "감상", "디자인", "연극"),
    "기타": ("기술", "가정", "정보", "한문", "중국어", "일본어", "외국어", "교양", "진로", "보건"),
}


def _field_of(subject: str) -> str:
    """세부 과목명을 교과 분야로 묶는다 (예: 생활과 과학 → 과학, 운동과 건강 → 체육)."""
    s = str(subject or "")
    for field, kws in _FIELD_KEYWORDS.items():
        if any(k in s for k in kws):
            return field
    return "기타"


def _student_record_brief(student_name: str) -> dict[str, list[str]]:
    """학생 생기부 세특을 분야별로 묶어 {분야: ["N학년 과목: 요지", ...]}로 반환한다.

    gap_plan·강점의 일반론을 막는 상담 재료다 — 미호는 이 실제 기록을 출발점으로
    삼아야 한다(사장님 2026-06-13: "상담사처럼 학생을 분석하고 학교에 맞춰라").
    학생을 못 찾으면 빈 dict."""
    if not _CENTRAL_LIFE_DB.exists():
        return {}
    import sqlite3

    by_field: dict[str, list[str]] = {}
    with sqlite3.connect(_CENTRAL_LIFE_DB) as db:
        row = db.execute(
            "SELECT id FROM students WHERE name = ? OR name LIKE ? LIMIT 1",
            (student_name, f"%{student_name}%"),
        ).fetchone()
        if not row:
            return {}
        for g, subj, txt in db.execute(
            "SELECT grade, subject, note_text FROM central_notes WHERE student_id = ? ORDER BY grade",
            (row[0],),
        ):
            if not txt or not str(txt).strip():
                continue
            snippet = " ".join(str(txt).split())[:48]
            by_field.setdefault(_field_of(subj), []).append(f"{g}학년 {subj}: {snippet}")
    return by_field


def _record_brief_text(brief: dict[str, list[str]], *, per_field: int = 2) -> str:
    """학생 세특 brief를 반려 메시지에 넣을 한 줄 요약으로 압축한다."""
    chunks: list[str] = []
    for field, items in brief.items():
        sample = "; ".join(items[:per_field])
        chunks.append(f"[{field}] {sample}")
    return " / ".join(chunks)


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
    # normalize_student_stage가 '3학년'·'고3'·'grade3' 등 정형 표기를 grade3로 모은다 —
    # 직접 문자열 비교(과거 버그: '3학년'→None)를 대체한다.
    norm = normalize_student_stage(student_stage)
    grade = {"grade1": 1, "grade2": 2, "grade3": 3}.get(norm)
    if grade or norm == "graduate":
        return grade  # graduate는 None (재학 학년 없음)
    # 자유표기 폴백: '고등학교 3학년' 등 alias에 없는 표현.
    m = re.search(r"([1-3])\s*학년", student_stage)
    return int(m.group(1)) if m else None


def _infer_stage_from_birth(student_name: str) -> str | None:
    """생기부 students.birth_masked(YYMMDD)와 현재 학년도로 학생 단계를 판정한다.

    미호의 자기신고 stage는 추측이라 재학생을 N수로(또는 그 반대로) 오판할 수 있다
    (사장님 2026-06-13: 서연을 graduate로 본 건 우연). 생년이 있으면 그게 단일
    진실원이다 — 고3의 출생 코호트연도 = 현재 학년도 - 18. 빠른생일(1·2월생)은
    한 해 위 코호트로 보정한다. 학생을 못 찾으면 None(미호 자기신고로 폴백)."""
    if not _CENTRAL_LIFE_DB.exists():
        return None
    import sqlite3

    with sqlite3.connect(_CENTRAL_LIFE_DB) as db:
        row = db.execute(
            "SELECT birth_masked FROM students WHERE name = ? OR name LIKE ? LIMIT 1",
            (student_name, f"%{student_name}%"),
        ).fetchone()
    if not row or not row[0]:
        return None
    digits = "".join(ch for ch in str(row[0]) if ch.isdigit())
    if len(digits) < 4:
        return None
    birth_year = 2000 + int(digits[:2])
    month = int(digits[2:4])

    now = datetime.now(_KST)
    # 학년도는 3월 시작 — 1·2월은 아직 직전 학년도다.
    school_year = now.year if now.month >= 3 else now.year - 1
    # 빠른생일: 1·2월생은 한 해 빠른 입학 코호트에 속한다.
    cohort_year = birth_year if month >= 3 else birth_year - 1
    delta = (school_year - 18) - cohort_year  # 0=고3, -1=고2, -2=고1, ≥1=졸업
    if delta >= 1:
        return "graduate"
    return {0: "grade3", -1: "grade2", -2: "grade1"}.get(delta)


def _grounding_errors(
    student_name: str,
    student_stage: str,
    content: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    text = _content_text(content)
    # 상담 재료 — 학생 실제 세특을 분야별로 읽어 두고, gap_plan·강점이 일반론이면
    # 이 기록을 출발점으로 제시하며 반려한다(사장님 2026-06-13: "상담사처럼").
    brief = _student_record_brief(student_name)
    brief_text = _record_brief_text(brief) if brief else ""

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

        # B. 단계-데이터 교차 검증 — 미호의 자기신고 stage가 생기부 데이터와
        # 모순되면 리포트 모드 전체가 어긋난다 (사장님 단계별 설계 2026-06-12:
        # 완성형 고3/N수=판단·등급, 세특공백 고3=1·2학년 기준 디벨롭,
        # 고1·2=방향성, 생기부 없음=상담 기반 시작 설계).
        grade = _stage_grade(student_stage)
        data_max_grade = max(note_grades) if note_grades else None
        if grade is not None and data_max_grade is not None and data_max_grade > grade:
            errors.append(
                f"student_stage가 {grade}학년인데 생기부에 {data_max_grade}학년 기록이 있다 — "
                f"단계를 다시 확인해라 (데이터상 {data_max_grade}학년 이상)."
            )

        # 재학생(고1~3)은 세특 설계가 리포트의 핵심 — 세특을 더 채우거나(공백) 기존
        # 세특을 학교 평가 방향으로 보강·재서술할 학기가 남아 있다(사장님 2026-06-13:
        # "세특 더 채울 학기 있으면 설계가 메인"). N수생/졸업만 재해석 모드(gap_plan 제외).
        has_current = grade in note_grades  # 당해 세특 일부라도 있나
        if grade is not None and grade <= 3:
            gap = (content.get("strategy_section") or {}).get("gap_plan")
            gap_subjects = (gap or {}).get("subjects") if isinstance(gap, dict) else None
            ok_gap = (
                isinstance(gap, dict)
                and _nonempty(gap.get("title"))
                and isinstance(gap_subjects, list)
                and len(gap_subjects) >= 3
                and all(
                    isinstance(r, dict)
                    and _nonempty(r.get("subject"))
                    and _is_specific_direction(r.get("direction"))
                    for r in gap_subjects
                )
            )
            if not ok_gap:
                _gap_lead = (
                    f"이 학생은 {grade}학년 세특이 일부 입력돼 있다 — 남은 학기에 기존 세특을 학교 평가 방향으로 "
                    "보강·재서술하고 추가 탐구를 얹는 '세특 설계'가 리포트의 핵심이다."
                    if has_current else
                    f"이 학생은 {grade}학년 세특이 아직 입력되지 않았다 — 공백을 채울 설계가 리포트의 핵심이다."
                )
                errors.append(
                    f"{_gap_lead} "
                    "이건 일반 조언이 아니라 이 학생만의 맞춤 상담이어야 한다 — 학생마다 답이 같으면 의미가 없다. "
                    "gap_plan.subjects(3개 이상)는 ①국어·영어·수학·과학·사회·체육 등 '분야' 단위로 잡되"
                    "(생기부엔 학생이 앞으로 들을 세부 과목이 없으니 세부 과목명을 못박지 마라), "
                    "②학생이 이미 기록을 가진 과목은 그 과목에서 디벨롭한다. "
                    "각 direction은 그 학과(hakjong_qualitative_profile)가 원하는 방향과 학생의 실제 세특을 연결해 "
                    "'무엇을 어떤 방법으로'까지 40자 이상 구체적으로 써라(측정·분석·통계·그래프·탐구·설계 등 실행 방법어 포함). "
                    "학과가 원하는 방향에 학생 기록이 닿아 있으면 디벨롭, 닿은 게 없으면 그 분야에서 새로 설계한다. "
                    "'탐구 연결'·'출결 정리' 같은 추상 한 줄은 반려된다. "
                    + (f"이 학생의 실제 세특이다 — 반드시 출발점으로 써라: {brief_text}. " if brief_text else "")
                    + "예: "
                    '{"gap_plan": {"title": "3학년 1학기 세특 설계", "subjects": ['
                    '{"subject": "과학", "direction": "생활과 과학에서 보인 운동 역학 관심을 살려, 운동 후 회복 심박수를 측정·기록하고 '
                    '그래프로 분석해 근골격계·에너지대사와 연결한 운동손상 탐구로 디벨롭한다"}, '
                    '{"subject": "체육", "direction": "운동과 건강의 체력측정 우수 기록을 출발점으로 종목별 약점을 분석해 '
                    '손상 예방 트레이닝을 설계한 보고서로 발전시킨다"}, '
                    '{"subject": "사회", "direction": "지역 생활체육 시설 접근성을 조사·비교해 개선안을 보고서로 정리하고 '
                    '공동체역량과 연결한다"}]}}'
                )
            if grade == 3 and not has_current:
                prior = [str(g) + "학년" for g in sorted(note_grades)]
                if prior and not all(p_ in text for p_ in prior):
                    errors.append(
                        "3학년 세특 미입력 학생의 판단 근거는 이전 학년 생기부다 — "
                        f"본문에 {'·'.join(prior)} 기록을 미뤄봤을 때 이 학교가 가능한지를 명시하고, "
                        "그 위에서 디벨롭 방향을 제시해라."
                    )

    # B-2. N수생/졸업생: 세특 설계 금지 (사장님 2026-06-13). 생기부가 완성돼 세특을
    # 더 못 바꾸므로 gap_plan(세특 설계)과 '세특을 ~로 채워라' 류 미래 지시는 반려한다.
    # 이 단계의 리포트는 ①이 학교 지원 가능성 판단 ②면접 방어, 이 둘만이다.
    if normalize_student_stage(student_stage) == "graduate":
        strat = content.get("strategy_section") or {}
        gap = strat.get("gap_plan")
        if isinstance(gap, dict) and gap:
            errors.append(
                "N수생/졸업생은 생기부가 완성돼 세특을 더 바꿀 수 없다 — "
                "strategy_section.gap_plan(세특 설계)을 빼라. 대신 기존 세특·창체를 이 학교 평가 "
                "언어로 재해석하고, 면접이 있으면 면접 방어 전략을 리포트의 중심에 둬라."
            )
        # 끝난 생기부를 미래에 바꾸라는 설계 언어만 잡는다(과거 기록 재해석은 허용).
        m = re.search(
            r"세특[을를]?\s*[^.。\n]{0,40}?(정리하|재구성|재정렬|채워|채우|설계|디벨롭|보강|발전시키|만들)",
            _content_text(strat),
        )
        if m:
            errors.append(
                f"N수생 리포트에 세특을 바꾸라는 설계 언어가 있다(\"…{m.group(0)[:30]}…\") — "
                "끝난 생기부는 못 고친다. '세특을 어떻게 채울지'가 아니라 '이미 있는 기록이 이 학교 "
                "평가축에 어떻게 먹히는지'와 면접 답변으로 다시 써라."
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

            # E. 강점-평가축 연결 (사장님 2026-06-13 ★최우선) — 강점 분석(강점 박스 +
            # 전형 강점)이 이 대학 평가요소에 1:1로 걸려야 한다. 학생의 실제 세특·창체가
            # 어느 역량(학업·진로·공동체·발전가능성)의 근거인지 짚지 않으면 추상 일반론이다.
            # N수생·재학생 공통 (N수생도 '기존 강점이 이 학교에 어떻게 먹히는지'가 핵심).
            axes = _evaluation_axes(prof.get("evaluation_elements"))
            if axes:
                diag = content.get("diagnosis_section") or {}
                track = content.get("track_section") or {}
                strength_text = (
                    _content_text(diag.get("strength"))
                    + " "
                    + _content_text(track.get("strong_points"))
                )
                if not any(a in strength_text for a in axes):
                    sample = ", ".join(sorted(axes))
                    errors.append(
                        f"강점 분석이 {uni_name}의 평가축에 연결돼 있지 않다 — "
                        "diagnosis_section.strength와 track_section.strong_points에서 학생의 구체적 "
                        "세특·창체 기록이 어느 평가요소의 근거가 되는지 1:1로 짚어라 "
                        "(예: '2학년 운동과 건강 세특의 마그누스 효과 탐구가 진로역량 근거가 된다'). "
                        f"이 대학 평가축: {sample}"
                        + (f". 이 학생 실제 세특(이 중에서 골라 평가축에 연결하라): {brief_text}" if brief_text else "")
                    )

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


# 세특 설계 direction이 "무엇을 어떻게"까지 구체적인지. 추상 한 줄("탐구 연결",
# "출결 정리") 반려용. 충분한 길이 + 실행 방법어가 있어야 통과 (사장님 2026-06-13:
# "통계 내서 그래프로 결과를 어떻게 한다" 수준의 구체성 요구).
_METHOD_WORDS = (
    "측정", "분석", "조사", "실험", "통계", "그래프", "데이터", "탐구",
    "설계", "비교", "기록", "관찰", "정리", "수집", "발표", "보고서",
)


def _is_specific_direction(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    return len(text) >= 40 and any(w in text for w in _METHOD_WORDS)


def _evaluation_axes(elements: Any) -> set[str]:
    """정성 프로필 evaluation_elements에서 평가요소 용어(○○역량·발전가능성)를 뽑는다."""
    axes: set[str] = set()
    if not isinstance(elements, list):
        return axes
    for el in elements:
        ax = el.get("평가축") if isinstance(el, dict) else None
        if not isinstance(ax, str):
            continue
        for word in re.findall(r"[가-힣]{2,}역량", ax):
            axes.add(word)
        if "발전가능성" in ax:
            axes.add("발전가능성")
    return axes


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
            ("strategy_section.gap_plan.subjects", ("subject", "direction")),
        ],
        char_limit=_contract.MAX_VISIBLE_TEXT_SEGMENT_CHARS,
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
                        "리포트의 목적이 단계마다 다르다 — "
                        "①고3(세특 채워짐)·N수생: 완성 생기부로 이 학교 방향성이 맞는지 판단하고 등급(badge)을 매기는 평가형. "
                        "②고3(당해 세특 미입력): 1·2학년 생기부를 미뤄봤을 때 가능한 학교인지 + 어떤 방향으로 디벨롭할지(gap_plan)가 중점. "
                        "③고1 2학기·고2: 생기부를 보고 방향성을 잡아주는 설계형. "
                        "④고1 1학기(생기부 없음): 상담 내용(관심사·장점·목표학교)을 근거로 생기부 시작 설계 — 상담 근거 없이 쓰지 마라. "
                        "세특 유무는 도구가 DB로 검증하니 단계를 추측하지 말 것."
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
            "너는 입시 상담사다. 이 리포트는 일반 조언 출력기가 아니라 이 학생 한 명을 위한 맞춤 상담이다 — "
            "학생마다 답이 같으면 있으나 마나다. 작성 순서: "
            "①학생 분석(life_record_lookup/search/summary로 실제 세특·창체·성적·적성을 분야별로 읽는다) → "
            "②학교/학과 분석(hakjong_qualitative_profile로 평가축·그 학과가 원하는 세특 방향) → "
            "③강점 살리기(학생의 어느 실제 기록이 학과 어느 평가요소에 먹히는지 1:1로 짚는다) → "
            "④약점 보완(학과가 원하는 방향에 학생 기록이 이미 닿아 있으면 그걸 디벨롭하고, 닿은 게 없으면 그 분야에서 새 세특을 설계한다) → "
            "⑤학교에 맞춘다. "
            "세특 조언은 세부 과목명이 아니라 국어·영어·수학·과학·사회·체육 등 분야 단위로 하되"
            "(생기부엔 학생이 앞으로 들을 과목이 없으니 안 들을 수도 있는 과목을 못박지 마라), "
            "이미 기록을 가진 과목만 그 과목에서 디벨롭한다. "
            "내용 JSON만 주면 껍데기(로고/푸터/브랜딩)는 고정 템플릿이 보장한다. "
            "학교별 학종 패키지(susi27_rule_lookup)와 생기부(life_record_lookup/search/summary)를 "
            "근거로 섹션 내용을 작성하라. "
            "글쓰기 톤: 학원 선생님이 학생과 학부모 앞에서 상담하며 설명하는 따뜻하고 자연스러운 말투로 — "
            "딱딱한 보고서체 나열 금지, 학생 이름을 부르며 말을 거는 문장으로. "
            "내부 판단 과정이나 배제 설명('OO 분야는 제외하고' 류)은 리포트에 쓰지 말고, "
            "요청받은 학교·학과에 대한 내용만 직접적으로 쓴다. "
            "★내용 깊이(가장 중요): 추상적 조언('출결 정리', '동기 재구성', '탐구 연결')은 금지다. "
            "hakjong_qualitative_profile의 subject_specific_notes(그 대학이 과목별로 원하는 방향)와 "
            "학생의 실제 과목·성적·기록을 연결해, 보완 전략과 세특 설계를 '무엇을 어떤 방법으로'까지 "
            "구체적으로 써라 — 예: '운동 후 회복 심박수를 측정·기록해 확률과통계로 그래프화하고 "
            "생명과학 염증·회복 단원과 연결'. 통계·측정·실험·조사·탐구 같은 실행 방법을 명시한다. "
            "학년별로 내용이 달라야 한다: ①세특 채울 학기가 남은 학생(고1·고2·고3 1학기 전)은 "
            "이전 세특을 토대로 '남은 학기에 무엇을 어떻게 채울지'(strategy_section.gap_plan)가 리포트의 중심이다. "
            "②고3 완성·N수생/졸업생은 채울 세특이 없으니 gap_plan(세특 설계)을 절대 넣지 말고 "
            "'세특을 ~로 채워라/정리해라' 류 미래 지시도 쓰지 마라 — 기존 세특·창체를 학교 평가 언어로 "
            "재해석하고, 이 학교 지원 가능성 판단 + 면접 방어 전략을 리포트의 중심에 둔다. "
            "③고1 1학기(생기부 없음)는 상담 내용 기반 시작 설계. "
            "★강점 분석(diagnosis_section.strength·track_section.strong_points)은 추상 칭찬이 아니라 "
            "학생의 실제 세특·창체 기록을 인용해 그것이 이 대학 평가요소(학업역량·진로역량·공동체역량 등)의 "
            "어느 근거가 되는지 1:1로 연결하고, 면접에서 그 활동을 어떻게 설명하면 강점이 되는지까지 짚어라. "
            "단계(student_stage)는 추측하지 마라 — 도구가 생기부 생년으로 자동 판정해 덮어쓴다. "
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
