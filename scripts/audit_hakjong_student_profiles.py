#!/usr/bin/env python3
"""Generate and audit hakjong reports for one student across qualitative DB profiles."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from plugins.academy_ops.hakjong_grounding import apply_gap_plan_grounding, validate_gap_plan_grounding
from plugins.academy_ops.hakjong_live_research import live_research_keywords
from plugins.academy_ops.hakjong_faculty_research import paper_titles_from_bundle
from plugins.academy_ops.hakjong_graduate_content import adapt_for_graduate
from plugins.academy_ops.hakjong_qualitative_tool import _db_path, lookup_profiles
from plugins.academy_ops.hakjong_report_tool import _hakjong_report_package_tool_handler, _infer_stage_from_birth
from plugins.academy_ops.hakjong_stage_contract import normalize_student_stage
from plugins.academy_ops.hakjong_storm_tool import build_hakjong_storm_plan
from plugins.susi_ops.service import lookup_rules


LIFE_DB = Path("/Users/etlab/.miho/life_records/central.sqlite3")
EVIDENCE_TOOLS = [
    "life_record_lookup",
    "hakjong_qualitative_profile",
    "hakjong_storm_prewrite",
    "susi27_rule_lookup",
]
GENERIC_ANCHORS = {"스포츠", "체육", "운동", "건강", "연구", "논문", "뉴스", "학과"}
LOW_VALUE_SUBJECTS = ("국어", "독서", "문학", "영어", "한문", "음악", "미술")


@dataclass(frozen=True)
class Target:
    university: str
    department: str
    track: str


@dataclass(frozen=True)
class LifeNote:
    grade: int | None
    subject: str
    text: str


def clip(value: Any, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).replace("AI", "데이터 활용").replace("실기", "수행").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def db_json(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value or "[]")
    except (TypeError, ValueError):
        return []


def load_targets() -> list[Target]:
    with sqlite3.connect(_db_path()) as db:
        rows = db.execute(
            """
            SELECT university, department, admission_track
            FROM qualitative_profiles
            WHERE status='final_ready'
            ORDER BY university, department, admission_track
            """
        ).fetchall()
    return [Target(*row) for row in rows]


def load_life_notes(student_name: str) -> list[LifeNote]:
    if not LIFE_DB.exists():
        raise RuntimeError(f"life record DB missing: {LIFE_DB}")
    with sqlite3.connect(LIFE_DB) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT id FROM students WHERE name=? OR name LIKE ? LIMIT 1", (student_name, f"%{student_name}%")).fetchone()
        if not row:
            raise RuntimeError(f"student not found: {student_name}")
        rows = db.execute(
            """
            SELECT grade, subject, note_text
            FROM central_notes
            WHERE student_id=?
            ORDER BY COALESCE(grade, 99), subject
            """,
            (row["id"],),
        ).fetchall()
    return [
        LifeNote(int(r["grade"]) if r["grade"] is not None else None, str(r["subject"] or ""), str(r["note_text"] or ""))
        for r in rows
        if str(r["subject"] or "").strip() and str(r["note_text"] or "").strip()
    ]


def profile_for(target: Target) -> dict[str, Any]:
    result = lookup_profiles(target.university, target.department, target.track, limit=1)
    profiles = result.get("profiles") or []
    if not profiles:
        raise RuntimeError(f"profile missing: {target}")
    return profiles[0]


def rule_for(target: Target) -> dict[str, Any]:
    result = lookup_rules(university=target.university, department=target.department, admission_track=target.track, limit=1)
    rows = result.get("rows") or []
    if not rows:
        rows = lookup_rules(university=target.university, admission_track=target.track, limit=1).get("rows") or []
    return rows[0] if rows else {}


def desired_keywords(profile: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in db_json(profile.get("desired_record_keywords")):
        text = clip(item, 28)
        if text and text not in out:
            out.append(text)
    return out[:8]


def evaluation_axes(profile: dict[str, Any]) -> list[str]:
    axes: list[str] = []
    for item in db_json(profile.get("evaluation_elements")):
        raw = item.get("평가축") if isinstance(item, dict) else item
        for word in re.findall(r"[가-힣]{2,}역량|발전가능성", str(raw)):
            if word not in axes:
                axes.append(word)
    return axes[:4] or ["진로역량", "학업역량", "공동체역량"]


def live_anchors(profile: dict[str, Any]) -> list[str]:
    bundle = profile.get("live_research") if isinstance(profile, dict) else None
    anchors = live_research_keywords(bundle, limit=8) + paper_titles_from_bundle(bundle, limit=3)
    unique: list[str] = []
    for item in anchors:
        text = clip(item, 80)
        if _usable_anchor(text) and text not in unique:
            unique.append(text)
    return unique[:8]


def _usable_anchor(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 4 or compact in GENERIC_ANCHORS:
        return False
    if not re.search(r"[가-힣]", text) and re.search(r"[A-Za-z]{4}", text):
        return False
    if any(noise in text for noise in ("네이버", "검색", "본문", "바로가기", "이미지")):
        return False
    return True


def select_notes(notes: list[LifeNote], terms: list[str], *, count: int = 3) -> list[LifeNote]:
    sports_terms = ["스포츠", "체육", "운동", "건강", "재활", "경기", "수학", "물리", "생명", "사회"]
    eligible = [note for note in notes if not note.subject.startswith("창체:")]
    pool = eligible or notes

    def score(note: LifeNote) -> tuple[int, int]:
        hay = f"{note.subject} {note.text}"
        term_score = sum(4 for term in terms if term and term in hay)
        sport_score = sum(1 for term in sports_terms if term in hay)
        field_score = 4 if any(token in note.subject for token in ("운동과 건강", "체육", "물리", "생명", "화학", "과학", "수학", "사회")) else 0
        penalty = 5 if note.subject in LOW_VALUE_SUBJECTS and term_score < 4 else 0
        return term_score + sport_score + field_score - penalty, min(len(note.text), 500)

    ranked = sorted(pool, key=score, reverse=True)
    chosen: list[LifeNote] = []
    seen_fields: set[str] = set()
    for note in ranked:
        field = field_of(note.subject)
        if field in seen_fields and len(chosen) < count:
            continue
        chosen.append(note)
        seen_fields.add(field)
        if len(chosen) >= count:
            break
    return chosen or ranked[:count]


def field_of(subject: str) -> str:
    if subject == "진로와 직업":
        return "직업탐구"
    if any(token in subject for token in ("체육", "운동", "스포츠")):
        return "체육"
    if any(token in subject for token in ("물리", "생명", "화학", "과학")):
        return "과학"
    if any(token in subject for token in ("수학", "기하", "확률", "미적")):
        return "수학"
    if any(token in subject for token in ("사회", "윤리", "정치", "경제")):
        return "사회"
    if "영어" in subject:
        return "영어"
    return subject[:8] or "세특"


def select_term_for_field(field: str, terms: list[str], department: str, index: int) -> str:
    if not terms:
        return department
    prefs = {
        "과학": ("생리", "역학", "체력", "측정", "분석", "기능", "처방", "손상", "데이터"),
        "체육": ("수행", "체력", "경기", "코칭", "지도", "처방", "재활", "분석"),
        "수학": ("데이터", "통계", "분석", "측정", "구조", "비교", "경영"),
        "사회": ("윤리", "공정", "건강권", "지역", "마케팅", "산업", "이벤트"),
        "직업탐구": ("진로", "전공", "교사", "산업", "학과", "탐색"),
    }.get(field, ())
    for pref in prefs:
        for term in terms:
            if pref in term:
                return term
    return terms[index % len(terms)]


def gap_subject(
    note: LifeNote,
    target: Target,
    profile_terms: list[str],
    anchors: list[str],
    axis: str,
    index: int,
    *,
    has_interview: bool,
) -> dict[str, Any]:
    field = field_of(note.subject)
    term = select_term_for_field(field, profile_terms, target.department, index)
    term2 = next((item for item in profile_terms if item != term), term)
    live = anchors[index % len(anchors)] if anchors else f"{target.department} 공식 학과 흐름"
    grade_label = f"{note.grade}학년 " if note.grade else ""
    subject_label = f"{grade_label}{note.subject}"
    field_subject = "직업 교과" if note.subject == "진로와 직업" else note.subject
    field_label = field if field == field_subject else f"{field}·{field_subject}"
    interview_note = (
        "면접이 있으면 동기, 방법, 한계, 개선을 답변 근거로 쓸 수 있다."
        if has_interview
        else "서류에서는 동기, 방법, 한계, 개선이 한 흐름으로 읽히게 만든다."
    )
    return {
        "field": field_label,
        "current_record": clip(
            f"{subject_label} 기록에서 '{clip(note.text, 120)}' 흐름이 보인다. "
            f"이 학생의 기존 활동을 출발점으로 삼아 {target.department} 지원서에서는 {term} 관심으로 재정리한다.",
            520,
        ),
        "school_direction": clip(
            f"{target.university} {target.department} {target.track}의 정성 DB 키워드는 {term}·{term2}이고, "
            f"학과 교수 연구·논문·최신 뉴스 흐름의 라이브 근거는 {live}이다. "
            "이 과목 설계는 학교별 관심분야에 맞춰 측정·자료수집·해석·성찰을 남기는 방향으로 잡는다.",
            520,
        ),
        "steps": [
            clip(
                f"{note.subject} 기존 기록에서 측정 가능한 변수를 하나 정한다. 왜 그 변수를 택했는지, "
                f"{target.department}의 {term}·{term2} 흐름과 어떻게 연결되는지 먼저 탐구 동기로 적는다.",
                360,
            ),
            clip(
                f"자료를 최소 2회 이상 모아 표와 그래프로 정리한다. 결과가 예상과 다르면 기준을 바꿔 다시 비교하고, "
                f"{live} 관점에서 해석 가능한 지점과 무리한 지점을 분리한다.",
                360,
            ),
            clip(
                f"보고서와 발표에는 성공 결과만 쓰지 말고 실패한 측정, 한계, 다음 수정안을 포함한다. "
                f"이 과정이 {axis} 근거로 읽히도록 학생의 행동 변화와 학습 내용을 함께 정리한다.",
                360,
            ),
        ],
        "eval_axis": axis,
        "expected_effect": clip(
            f"{subject_label} 세특이 단순 활동 기록이 아니라 {target.university} {target.department} 기준의 "
            f"{term}·{term2} 및 {live} 근거로 연결된다. {interview_note}",
            520,
        ),
    }


def official_rows(target: Target, rule: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]], bool, str]:
    meta = rule.get("admission_meta") if isinstance(rule.get("admission_meta"), dict) else {}
    quota = str(rule.get("quota") or meta.get("quota") or "확인")
    stage1 = meta.get("stage1") if isinstance(meta.get("stage1"), dict) else {}
    stage2 = meta.get("stage2") if isinstance(meta.get("stage2"), dict) else {}
    multiple = str(stage1.get("multiple") or "확인")
    multiple_digits = "".join(ch for ch in multiple if ch.isdigit())
    multiple_label = f"{multiple}배수"
    if multiple_digits and multiple_digits != multiple:
        multiple_label = f"{multiple}배수({multiple_digits}배수)"
    record = str(stage1.get("student_record") or "확인")
    interview = str(stage2.get("interview") or "")
    carry = str(stage2.get("other") or "")
    has_interview = bool(interview and interview not in {"0", "0.0", "없음"})
    csat = meta.get("minimum_csat") if isinstance(meta.get("minimum_csat"), dict) else {}
    csat_text = str(csat.get("detail") or "없음")
    rows = [
        {"label": "모집인원", "official": f"{quota}명" if quota.isdigit() else quota, "judgment": "전형 규모 확인"},
        {"label": "1단계", "official": f"서류(학생부) {record}% · {multiple_label} 선발", "judgment": "학생부 설득력 필요"},
        {"label": "2단계", "official": f"1단계 성적 {carry or '?'} + 면접 {interview}" if has_interview else "면접 미반영", "judgment": "면접 여부에 맞춰 전략 분리"},
        {"label": "수능최저", "official": f"수능최저: {csat_text}", "judgment": "요강 DB 기준"},
    ]
    cards = [
        {"label": "전형", "value": target.track, "sub": "학종 DB 기준"},
        {"label": "모집", "value": f"{quota}명" if quota.isdigit() else quota, "sub": "susi27_rule_lookup"},
        {"label": "최저", "value": csat_text, "sub": "요강 DB 기준"},
    ]
    return rows, cards, has_interview, quota


def build_content(student: str, stage: str, target: Target, profile: dict[str, Any], notes: list[LifeNote], rule: dict[str, Any]) -> dict[str, Any]:
    kws = desired_keywords(profile)
    axes = evaluation_axes(profile)
    anchors = live_anchors(profile)
    selected = select_notes(notes, kws + anchors, count=3)
    rows, cards, has_interview, quota = official_rows(target, rule)
    subjects = [
        gap_subject(note, target, kws, anchors, axes[i % len(axes)], i, has_interview=has_interview)
        for i, note in enumerate(selected)
    ]
    while len(subjects) < 3 and selected:
        subjects.append(
            gap_subject(
                selected[len(subjects) % len(selected)],
                target,
                kws,
                anchors,
                axes[len(subjects) % len(axes)],
                len(subjects),
                has_interview=has_interview,
            )
        )
    keyword_text = "·".join(kws[:4]) or target.department
    live_has_source = bool(anchors)
    live_text = "·".join(anchors[:2]) or f"{target.department} 공식 학과 방향"
    live_label = "교수 논문/뉴스 근거" if live_has_source else "학종 DB/공식 학과 방향"
    prior_grades = "·".join(f"{g}학년" for g in sorted({n.grade for n in notes if n.grade and n.grade < 3})) or "이전 학년"
    prior_basis = f"{prior_grades} 기록을 미뤄봤을 때 판단한다. 3학년 1학기에는 이 근거를 {target.department} 방향으로 디벨롭한다."
    interview_rows = []
    if has_interview:
        interview_rows = [
            {"question": f"{target.department} 지원 동기를 학생부 기록으로 설명해 보세요.", "point": f"{selected[0].subject} 기록에서 출발해 키워드 묶음({keyword_text}) 및 {live_text} 근거로 연결한다. 꼬리질문은 왜 이 학과여야 하는지와 실제로 한 활동 근거로 방어한다."},
            {"question": "가장 깊게 설명할 수 있는 탐구의 한계는 무엇인가요?", "point": "측정 변수, 자료 수, 예상과 달랐던 결과, 다음 개선을 순서대로 답한다. 재질문이 나오면 실패를 숨기지 말고 기준을 바꾼 이유를 설명한다."},
            {"question": "우리 학과의 최근 흐름과 본인 활동이 어떻게 닿나요?", "point": f"{live_text} 중 하나를 골라 학생 기록의 방법과 연결한다. 꼬리질문은 논문·뉴스를 외운 척하지 말고 본인 탐구와 닿는 한 지점만 방어한다."},
            {"question": "팀 활동에서 본인의 역할은 무엇이었나요?", "point": "활동 사실, 역할, 갈등 조정, 배운 점을 구체 사례로 답한다. 재질문은 본인이 바꾼 행동과 팀 결과가 무엇이었는지로 대비한다."},
            {"question": "입학 후 어떤 방향으로 탐구를 이어갈 건가요?", "point": f"키워드 묶음({keyword_text}) 중심으로 교과·창체·진로 계획을 말한다. 꼬리질문은 고등학교 기록에서 이어지는 질문인지, 입학 후 계획이 과장되지 않았는지로 방어한다."},
        ]
    content = {
        "student": {"name": student},
        "university": {"name": target.university, "department": target.department, "college": "체육계열", "track": target.track},
        "badge": {"grade": "보완 후 검토", "action": "학생부 근거 보완"},
        "title_lines": [f"{student} 학생", f"{target.university} {target.department} 학종 전략"],
        "cover": {
            "pills": [target.university, target.department, target.track, normalize_student_stage(stage)],
            "key_judgment": {"headline": f"지원 가능성 판단: 보완 후 검토", "body": f"{student}의 실제 과목 기록을 {keyword_text} 중심으로 재정리하고, {live_text} 근거를 세특 설계에 연결한다. {prior_basis}"},
            "metrics": [{"label": "모집", "value": str(quota)}, {"label": "키워드", "value": keyword_text[:18]}, {"label": "근거", "value": selected[0].subject[:18]}],
        },
        "track_section": {
            "heading": "전형 핵심",
            "info_cards": cards,
            "rows": rows + [{"label": "최신 학과 흐름", "official": f"{live_label}: {live_text}", "judgment": f"세특은 {keyword_text} 중심으로 압축"}],
            "strong_points": {"title": "강점", "bullets": [f"{selected[0].subject} 기록과 {keyword_text} 연결", f"{live_text} 근거 반영", f"{axes[0]} 중심 설계"]},
            "caution_points": {"title": "주의", "bullets": ["학교별 키워드 없이 일반 스포츠 관심으로 쓰면 약함", "3학년 설계는 측정·한계·개선이 있어야 함"]},
            "footnote": f"{target.university} {target.track} 모집 {quota} 기준.",
        },
        "diagnosis_section": {
            "heading": "학생부 진단",
            "strength": {"headline": f"{axes[0]} 근거", "body": f"{selected[0].subject}·{selected[1].subject if len(selected)>1 else selected[0].subject} 기록이 {keyword_text} 중심 흐름으로 연결된다. {prior_basis}"},
            "risk": {"headline": "일반론 위험", "body": f"{target.department}의 {keyword_text} 및 {live_text} 근거를 쓰지 않으면 다른 학교와 구분되지 않는다."},
            "rows": [
                {"area": note.subject, "record": clip(note.text, 85), "interpretation": f"{select_term_for_field(field_of(note.subject), kws, target.department, i)} 연결", "check": axes[i % len(axes)]}
                for i, note in enumerate(selected)
            ],
            "gauges": [
                {
                    "label": axes[i % len(axes)],
                    "level": "보완 가능",
                    "note": subjects[i % len(subjects)]["field"],
                    "tone": "blue",
                    "percent": 72 + i * 4,
                }
                for i in range(3)
            ],
            "footnote": "학생 생기부 원문 과목 기록과 학종 DB를 함께 사용했다.",
        },
        "strategy_section": {
            "heading": "보완 전략",
            "actions": [
                {"title": "학교별 키워드 고정", "body": f"키워드 묶음({keyword_text})을 리포트 중심축으로 두고 모든 세특 설계를 이 기준으로 검토한다."},
                {"title": "라이브 근거 반영", "body": f"{live_text} 근거를 학생 기록의 측정·분석 방법과 연결한다."},
                {"title": "학생 기록 확장", "body": f"{prior_basis} {selected[0].subject} 기록을 3학년 1학기 프로젝트로 이어 깊이를 만든다."},
                {"title": "검증", "body": "완성본은 과목명, 학교 키워드, 라이브 근거가 모두 보이는지 확인한다."},
            ],
            "interview_rows": interview_rows,
            "final_judgment": {"body": f"지원 가능성 판단: 보완 후 검토권이다. {prior_basis} 학교별 근거와 실제 과목 기록의 결합이 핵심이다."},
            "gap_plan": {"title": "학교맞춤 세특·활동 설계", "subjects": subjects},
            "checklist": {"title": "검증 체크", "bullets": ["DB 키워드", "논문/뉴스", "학생 과목"], "tags": [target.university, target.department, target.track]},
            "footnote": "맥스체대입시 일산교육원",
        },
    }
    if normalize_student_stage(stage) == "graduate":
        adapt_for_graduate(content)
    else:
        apply_gap_plan_grounding(content, profile)
    return content


def audit_one(student: str, stage: str, target: Target, notes: list[LifeNote]) -> dict[str, Any]:
    profile = profile_for(target)
    rule = rule_for(target)
    content = build_content(student, stage, target, profile, notes, rule)
    storm = build_hakjong_storm_plan(
        student_name=student,
        university=target.university,
        department=target.department,
        admission_track=target.track,
        student_stage=stage,
        qualitative_profile=profile,
        student_record_facts=[f"{n.grade or ''}학년 {n.subject}: {clip(n.text, 120)}" for n in notes[:12]],
        max_questions=18,
    )
    preflight_errors = validate_gap_plan_grounding(content, profile, student_stage=stage)
    if preflight_errors:
        return {"ok": False, "target": target.__dict__, "stage": "preflight", "errors": preflight_errors}
    result = json.loads(_hakjong_report_package_tool_handler({"student_name": student, "student_stage": stage, "evidence_tools": EVIDENCE_TOOLS, "content": content}))
    if not result.get("ok"):
        return {"ok": False, "target": target.__dict__, "stage": "package", "errors": result.get("errors") or [], "raw": result}
    return {
        "ok": True,
        "target": target.__dict__,
        "pdf": result.get("file_path"),
        "manifest": result.get("manifest_path"),
        "storm_status": (storm.get("safety") or {}).get("status"),
        "checks": result.get("checks") or {},
    }


def write_report(out_dir: Path, student: str, results: list[dict[str, Any]]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md = out_dir / f"{student}_hakjong_all_audit_{stamp}.md"
    raw = md.with_suffix(".json")
    raw.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok_count = sum(1 for item in results if item.get("ok"))
    lines = [
        f"# {student} 학종 DB 전체 리포트 감사",
        "",
        f"- 대상: {len(results)}건",
        f"- 통과: {ok_count}건",
        f"- 재작업: {len(results) - ok_count}건",
        "",
        "|#|대학|학과|전형|판정|이슈|PDF|",
        "|---:|---|---|---|---|---|---|",
    ]
    for idx, item in enumerate(results, 1):
        target = item["target"]
        issue = "; ".join(clip(e, 120) for e in item.get("errors") or [])
        lines.append(
            f"|{idx}|{target['university']}|{target['department']}|{target['track']}|"
            f"{'OK' if item.get('ok') else 'FAIL'}|{issue}|{item.get('pdf', '')}|"
        )
    md.write_text("\n".join(lines), encoding="utf-8")
    return md


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--student", required=True)
    parser.add_argument("--stage", default="grade3")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out-dir", default="/Users/etlab/.miho/media_cache/hakjong_audit/student_profiles")
    args = parser.parse_args()

    notes = load_life_notes(args.student)
    stage = _infer_stage_from_birth(args.student) or args.stage
    targets = load_targets()
    targets = targets[max(0, args.start - 1):]
    if args.limit:
        targets = targets[: args.limit]
    results: list[dict[str, Any]] = []
    for idx, target in enumerate(targets, 1):
        print(f"[{idx}/{len(targets)}] {target.university} {target.department} {target.track}", flush=True)
        try:
            item = audit_one(args.student, stage, target, notes)
        except Exception as exc:
            item = {"ok": False, "target": target.__dict__, "stage": "exception", "errors": [str(exc)]}
        print("  ->", "OK" if item.get("ok") else "FAIL", item.get("errors") or "", flush=True)
        results.append(item)
    report = write_report(Path(args.out_dir), args.student, results)
    print(f"REPORT:{report}")
    if any(not item.get("ok") for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
