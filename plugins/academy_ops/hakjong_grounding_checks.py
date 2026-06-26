"""Grounding checks for hakjong report content."""

from __future__ import annotations

import json
import re
from typing import Any

from .hakjong_grounding import validate_gap_plan_grounding
from .hakjong_record_context import (
    CENTRAL_LIFE_DB,
    completed_record_rewrite_phrase,
    content_text,
    record_brief_text,
    stage_grade,
    student_record_brief,
)
from .hakjong_stage_contract import normalize_student_stage


def grounding_errors(
    student_name: str,
    student_stage: str,
    content: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    text = content_text(content)
    brief = student_record_brief(student_name)
    brief_text = record_brief_text(brief) if brief else ""

    subjects: set[str] = set()
    note_grades: set[int] = set()
    if CENTRAL_LIFE_DB.exists():
        import sqlite3

        with sqlite3.connect(CENTRAL_LIFE_DB) as db:
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
                for (grade,) in db.execute(
                    "SELECT DISTINCT grade FROM central_notes WHERE student_id = ?", (sid,)
                ):
                    if grade is not None:
                        note_grades.add(int(grade))

    if subjects:
        cited = sorted(subject for subject in subjects if subject in text)
        need = min(3, len(subjects))
        if len(cited) < need:
            sample = ", ".join(sorted(subjects)[:8])
            errors.append(
                f"생기부 구체 근거가 부족하다 — 학생의 실제 과목·세특 과목을 {need}개 이상 본문에 "
                f"인용해 일반론이 아닌 이 학생 이야기로 써라 (현재 {len(cited)}개 인용). "
                f"학생 과목 예: {sample}"
            )

        grade = stage_grade(student_stage)
        data_max_grade = max(note_grades) if note_grades else None
        if grade is not None and data_max_grade is not None and data_max_grade > grade:
            errors.append(
                f"student_stage가 {grade}학년인데 생기부에 {data_max_grade}학년 기록이 있다 — "
                f"단계를 다시 확인해라 (데이터상 {data_max_grade}학년 이상)."
            )

        has_current = grade in note_grades
        if grade is not None and grade <= 3:
            gap = (content.get("strategy_section") or {}).get("gap_plan")
            gap_subjects = (gap or {}).get("subjects") if isinstance(gap, dict) else None
            ok_gap = (
                isinstance(gap, dict)
                and _nonempty(gap.get("title"))
                and isinstance(gap_subjects, list)
                and len(gap_subjects) >= 3
                and all(
                    isinstance(row, dict)
                    and _nonempty(row.get("field"))
                    and isinstance(row.get("steps"), list)
                    and len(row.get("steps")) >= 3
                    and all(_nonempty(step) and len(str(step).strip()) >= 30 for step in row.get("steps"))
                    and (
                        len(str(row.get("current_record") or "").strip())
                        + len(str(row.get("school_direction") or "").strip())
                        + len(str(row.get("expected_effect") or "").strip())
                        + sum(len(str(step).strip()) for step in row.get("steps"))
                    )
                    >= 500
                    for row in gap_subjects
                )
            )
            if not ok_gap:
                lead = (
                    f"이 학생은 {grade}학년 세특이 일부 입력돼 있다 — 남은 학기에 기존 세특을 학교 평가 방향으로 "
                    "보강·재서술하고 추가 탐구를 얹는 '세특 설계'가 리포트의 핵심이다."
                    if has_current
                    else f"이 학생은 {grade}학년 세특이 아직 입력되지 않았지만, 공백 자체는 반려 사유가 아니다 — "
                    "남은 3학년 1학기에 채울 구체 프로젝트와 과세특 설계가 리포트의 핵심이다."
                )
                errors.append(
                    f"{lead} "
                    "반려 사유는 세특 공백이 아니라 gap_plan의 개수·깊이·근거가 부족한 것이다. "
                    "이건 일반 조언이 아니라 이 학생만의 맞춤 상담 — 학생마다 답이 같으면 의미가 없다. "
                    "strategy_section.gap_plan.subjects는 분야별 1페이지 상세 세특 설계다. 분야는 이 학생의 "
                    "세특에 그 과목의 전공 관련 탐구·활동이 실제로 있는 과목만 잡아라 — 수업 성실·어휘 노력·감상문 "
                    "같은 일반 기록만 있고 전공과 약하게 끼워맞춰야 하는 과목(예: 영어 어휘 노력, 국어 수업태도)은 "
                    "분야로 만들지 마라. 분야가 적어도 세특 근거가 분명한 게 낫다. 단 학년에 따라 창체를 다르게 다룬다: "
                    "고1·2 학생은 창체(동아리·자율·진로) 활동도 어느 정도 독립 분야로 제시하라 — 아직 신규 설계가 가능한 시기다 / "
                    "고3·N수는 창체를 교과 세특에 녹이거나 기존활동 활용 전략으로 다뤄도 된다(굳이 독립 분야로 안 만들어도 됨). "
                    "과세특·활동 프로젝트는 최소 3개 이상 제시하라 — 기존 생기부 연계 프로젝트와 "
                    "학과/교수논문/최신뉴스 기반 신규 프로젝트를 섞어야 한다. "
                    "이건 유료 프리미엄 컨설팅 문서다 — 한 과목 디벨롭이 100자대로 휑하면 반려된다. 한 분야 본문은 "
                    "500자 이상의 깊이로 채워라. 각 분야는 다음을 갖춘다: "
                    "field(분야명) · current_record(이 학생이 지금까지 해온 활동을 실제 기록에서 구체 인용, 40자+) · "
                    "school_direction(이 학과가 원하는 방향, hakjong_qualitative_profile 근거, 25자+) · "
                    "steps(탐구 단계 3개 이상, 각 단계는 서로 다른 내용으로 120~180자로 깊이 있게). "
                    "★문체: 본문은 학생에게 주는 설계 제안이다 — '~해보자/~하면 좋다/~할 수 있다' 또는 학생 행동 서술로 "
                    "자연스럽게 써라. '~했다고 쓰게 만든다 / ~라고 쓴다 / 생기부에 남긴다고 쓴다 / ~라고 말할 수 있게 만든다' "
                    "같은 컨설턴트→학생 메타 지시·생기부 조작 톤은 본문에 절대 노출 금지다(학생·학부모가 읽으면 '이게 뭔 소리지' 한다). "
                    "★과세특의 핵심은 학종 평가관이 보는 행동특성이다 — 어느 학과나 중요하다. 다음이 그 분야에서 "
                    "자연스러운 만큼 드러나면 좋다(전부 욱여넣는 체크리스트가 아니다): 탐구 동기·과정·문제해결(막힌 점 개선)·"
                    "성찰·학습. '측정한다/분석한다'로만 끝내지 말고 동기·개선·성찰이 자연스럽게 이어지는 서사로 써라. "
                    "공동체(협업)는 실제로 협업이 자연스러운 탐구일 때만 짚어라 — '친구와 교차측정' 같은 작위적 협업을 "
                    "억지로 모든 분야에 끼워넣지 마라. 학생이 실제 하지 않은 일은 이상하고, 진짜 그 학생만의 맞춤이 아니다. "
                    "학과 방향에 학생 기록이 닿아 있으면 디벨롭, 닿은 게 없으면 그 분야에서 새로 설계한다. "
                    + (f"이 학생의 실제 세특·창체다 — 반드시 이 기록을 바탕으로 써라: {brief_text}. " if brief_text else "")
                    + "예: "
                    '{"gap_plan": {"title": "3학년 1학기 분야별 세특·활동 설계", "subjects": ['
                    '{"field": "체육", '
                    '"current_record": "1학년 동아리 필라테스반에서 모던리포머·레더바 등 재활 기구를 다뤘고 운동과 건강에서 척주질환 예방을 발표함", '
                    '"school_direction": "스포츠의학과는 재활·운동처방·기능평가를 본다", '
                    '"steps": ['
                    '"1학년 필라테스반에서 다룬 모던리포머·레더바 동작을 척주 안정화 관점에서 분류하고, 동작별 가동범위와 통증 지표를 주차별로 측정·기록한다", '
                    '"측정 데이터를 그래프로 시각화해 척주질환 예방에 효과적인 동작을 통계로 가려내고, 강도·빈도를 담은 개인 운동처방 보고서로 완성한다", '
                    '"운동과 건강의 척주질환 예방 발표와 연결해, 재활 운동의 원리를 근골격계 해부 지식으로 설명한 심화 탐구로 발전시킨다"], '
                    '"eval_axis": "진로역량", '
                    '"expected_effect": "측정·분석·처방으로 이어지는 기능평가 구조가 스포츠의학과 진로역량 25점 항목에 직접 닿고, 면접에서 재활 관심을 데이터로 설명할 근거가 된다"}]}}'
                )
            if grade == 3 and isinstance(gap_subjects, list):
                for row in gap_subjects:
                    if not isinstance(row, dict):
                        continue
                    if not any(key in str(row.get("field") or "") for key in ("창체", "동아리", "자율", "자치", "진로", "봉사", "활동")):
                        continue
                    steps_txt = " ".join(str(step) for step in (row.get("steps") or []))
                    blocked_words = ("제작", "만든다", "만들어", "만들기", "산출물", "새로", "체크리스트")
                    if any(word in steps_txt for word in blocked_words):
                        errors.append(
                            f"고3 창체 분야('{row.get('field')}')에 새 활동을 제작·실행하라는 설계가 있다 — 고3 1학기는 창체를 새로 못 만든다. "
                            "steps를 '기존 활동(자율스포츠·경기운영단 등)이 이 학과 평가요소에 왜 유리한지 분석'과 "
                            "'면접·서류에서 그 활동을 어떻게 설명·부각할지'로만 써라(제작·산출물·신규 활동 금지)."
                        )
                        break

            if grade == 3 and not has_current:
                prior = [str(grade_num) + "학년" for grade_num in sorted(note_grades)]
                if prior and not all(prior_label in text for prior_label in prior):
                    errors.append(
                        "3학년 세특 미입력 학생의 판단 근거는 이전 학년 생기부다 — "
                        f"본문에 {'·'.join(prior)} 기록을 미뤄봤을 때 이 학교가 가능한지를 명시하고, "
                        "그 위에서 디벨롭 방향을 제시해라."
                    )

    if normalize_student_stage(student_stage) == "graduate":
        strategy = content.get("strategy_section") or {}
        gap = strategy.get("gap_plan")
        if isinstance(gap, dict) and gap:
            errors.append(
                "N수생/졸업생은 생기부가 완성돼 세특을 더 바꿀 수 없다 — "
                "strategy_section.gap_plan(세특 설계)을 빼라. 대신 기존 세특·창체를 이 학교 평가 "
                "언어로 재해석하고, 면접이 있으면 면접 방어 전략을 리포트의 중심에 둬라."
            )
        bad_phrase = completed_record_rewrite_phrase(content_text(strategy))
        if bad_phrase:
            errors.append(
                f"N수생 리포트에 세특을 바꾸라는 설계 언어가 있다(\"…{bad_phrase[:30]}…\") — "
                "끝난 생기부는 못 고친다. '세특을 어떻게 채울지'가 아니라 '이미 있는 기록이 이 학교 "
                "평가축에 어떻게 먹히는지'와 면접 답변으로 다시 써라."
            )

    university = content.get("university") or {}
    uni_name = str(university.get("name") or "").strip()
    if uni_name:
        _append_admission_rule_errors(content, uni_name, university, text, errors)
        _append_qualitative_profile_errors(content, uni_name, university, text, brief_text, student_stage, errors)
    return errors


def _append_admission_rule_errors(
    content: dict[str, Any],
    uni_name: str,
    university: dict[str, Any],
    text: str,
    errors: list[str],
) -> None:
    try:
        from plugins.susi_ops.service import lookup_rules

        track = str(university.get("track") or "").strip() or None
        dept = str(university.get("department") or "").strip() or None
        rows = lookup_rules(university=uni_name, department=dept, admission_track=track, limit=1).get("rows") or []
        if not rows and dept:
            rows = lookup_rules(university=uni_name, admission_track=track, limit=1).get("rows") or []
    except Exception:
        rows = []
    if not rows:
        return
    quota = str(rows[0].get("quota") or "").strip()
    quota_num = "".join(char for char in quota if char.isdigit())
    if quota_num and f"{quota_num}명" not in text:
        errors.append(
            f"전형 DB 수치가 본문에 없다 — {uni_name} 해당 전형 모집인원 '{quota_num}명'을 "
            "리포트에 인용해라 (susi27_rule_lookup의 admission_meta·quota가 근거다)."
        )
    _append_admission_meta_errors(content, rows[0], errors)


def _append_admission_meta_errors(
    content: dict[str, Any],
    row: dict[str, Any],
    errors: list[str],
) -> None:
    meta = row.get("admission_meta") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (TypeError, ValueError):
            meta = {}
    track_rows = (content.get("track_section") or {}).get("rows") or []
    officials = " ".join(
        f"{item.get('label') or ''} {item.get('official') or ''}"
        for item in track_rows
        if isinstance(item, dict)
    )
    official_facts: list[str] = []
    stage1 = meta.get("stage1") if isinstance(meta.get("stage1"), dict) else {}
    stage2 = meta.get("stage2") if isinstance(meta.get("stage2"), dict) else {}
    multiple = "".join(char for char in str(stage1.get("multiple") or "") if char.isdigit())
    if multiple:
        rec1 = "".join(char for char in str(stage1.get("student_record") or "") if char.isdigit())
        official_facts.append(f"1단계: 서류(학생부) {rec1 or '?'}% · {multiple}배수 선발")
        if f"{multiple}배수" not in officials:
            errors.append(f"전형핵심 표에 1단계 선발 배수가 없다 — '{multiple}배수'를 official 값에 그대로 써라.")
    interview = "".join(char for char in str(stage2.get("interview") or "") if char.isdigit())
    if interview and int(interview) > 0:
        carry = "".join(char for char in str(stage2.get("other") or "") if char.isdigit())
        official_facts.append(f"2단계: 1단계 성적 {carry or '?'} + 면접 {interview}")
        if interview not in officials or "면접" not in officials:
            errors.append(f"전형핵심 표에 2단계 면접 반영비율이 없다 — '면접 {interview}'을 official 값에 그대로 써라.")
    csat = meta.get("minimum_csat") if isinstance(meta.get("minimum_csat"), dict) else {}
    has_min = str(csat.get("has_minimum") or "").strip().lower()
    if has_min in ("", "0", "false", "no", "없음", "n"):
        official_facts.append("수능최저: 없음")
    elif str(csat.get("detail") or "").strip():
        official_facts.append(f"수능최저: {csat['detail']}")
    if errors and official_facts:
        errors.append("DB 공식 전형 구조 (이대로 인용하라): " + " / ".join(official_facts))


def _append_qualitative_profile_errors(
    content: dict[str, Any],
    uni_name: str,
    university: dict[str, Any],
    text: str,
    brief_text: str,
    student_stage: str,
    errors: list[str],
) -> None:
    try:
        from .hakjong_qualitative_tool import lookup_profiles

        dept_name = str(university.get("department") or "").strip() or None
        track_name = str(university.get("track") or "").strip() or None
        prof_rows = lookup_profiles(university=uni_name, department=dept_name, admission_track=track_name, limit=1).get("profiles") or []
        if not prof_rows and track_name:
            prof_rows = lookup_profiles(university=uni_name, admission_track=track_name, limit=1).get("profiles") or []
    except Exception:
        prof_rows = []
    if not prof_rows:
        return
    profile = prof_rows[0]
    axes = _evaluation_axes(profile.get("evaluation_elements"))
    if axes:
        diagnosis = content.get("diagnosis_section") or {}
        track = content.get("track_section") or {}
        strength_text = content_text(diagnosis.get("strength")) + " " + content_text(track.get("strong_points"))
        if not any(axis in strength_text for axis in axes):
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
        str(keyword).strip()
        for keyword in (profile.get("desired_record_keywords") or [])
        if isinstance(keyword, str)
        and 1 < len(keyword.strip()) <= 20
        and not any(part and part in keyword for part in ident)
    ]
    if keywords:
        cited = [keyword for keyword in keywords if keyword in text]
        if len(cited) < 2:
            sample = ", ".join(keywords[:10])
            errors.append(
                f"{uni_name} {profile.get('admission_track')}의 학종 정성 프로필"
                "(hakjong_qualitative_profile)이 있는데 본문이 그 평가 기준에 발 딛고 있지 않다 — "
                f"이 대학이 생기부에서 찾는 키워드를 2개 이상 진단·전략에 녹여라. 키워드: {sample}"
            )
    errors.extend(validate_gap_plan_grounding(content, profile, student_stage=student_stage))


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _evaluation_axes(elements: Any) -> set[str]:
    axes: set[str] = set()
    if not isinstance(elements, list):
        return axes
    for element in elements:
        axis = element.get("평가축") if isinstance(element, dict) else None
        if not isinstance(axis, str):
            continue
        for word in re.findall(r"[가-힣]{2,}역량", axis):
            axes.add(word)
        if "발전가능성" in axis:
            axes.add("발전가능성")
    return axes
