"""Grade-selection and grade-table fallback engine."""

from __future__ import annotations

from typing import Any

from .score_adjustments import achievement_ratio_grade, uses_achievement_ratio_grade
from .semester_rules import within_semester_limit
from .utils import _optional_positive_int


def _norm_subject_area(value: Any) -> str:
    text = str(value or "").strip()
    short = {"국": "국어", "수": "수학", "영": "영어", "사": "사회", "과": "과학"}
    if text in short:
        return short[text]
    # 생기부 교과군명(긴 형식: "사회(역사/도덕 포함)", "기술・가정/제2외국어/한문/교양" 등)을
    # 산식 subject_flags 표준명(국어/수학/영어/과학/사회/한국사/체육/기타)으로 정규화.
    # startswith 위주 — "제2외국어"의 "국어" 부분매칭 오류 방지.
    if "한국사" in text:
        return "한국사"
    if text.startswith("국어"):
        return "국어"
    if text.startswith("수학"):
        return "수학"
    if text.startswith("영어"):
        return "영어"
    if text.startswith("과학"):
        return "과학"
    if text.startswith("사회") or "역사" in text or "도덕" in text:
        return "사회"
    if text.startswith("체육"):
        return "체육"
    if text.startswith("예술") or "음악" in text or "미술" in text:
        return "예술"
    if any(k in text for k in ("기술", "가정", "제2외국어", "한문", "교양", "정보", "진로")):
        return "기타"
    return text


_GENERIC_CENTRAL_AREAS = {"", "일반", "공통", "공통과목", "일반선택", "진로 선택", "진로선택", "선택"}
_SUBJECT_AREA_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("한국사", ("한국사",)),
    ("국어", ("국어", "화법", "작문", "문학", "독서", "심화 국어")),
    ("수학", ("수학", "확률", "통계", "미적분", "기하")),
    ("영어", ("영어",)),
    ("과학", ("과학", "물리", "화학", "생명과학", "지구과학")),
    (
        "사회",
        (
            "사회", "통합사회", "한국지리", "세계지리", "동아시아사", "세계사", "경제",
            "정치", "법", "윤리", "사회문제", "생활과 윤리", "윤리와 사상",
        ),
    ),
    ("체육", ("체육", "운동", "스포츠")),
    ("예술", ("음악", "미술", "창작")),
)


def _subject_area_from_row(row: dict[str, Any]) -> str:
    """Resolve subject area, falling back from central DB's generic category to subject name."""
    raw_area = row.get("area") or row.get("교과") or row.get("subject_area") or row.get("과목군")
    area = _norm_subject_area(raw_area)
    if area not in _GENERIC_CENTRAL_AREAS and area != "기타":
        return area
    subject = str(row.get("subject") or row.get("과목") or "").strip()
    for resolved, keywords in _SUBJECT_AREA_KEYWORDS:
        if any(keyword in subject for keyword in keywords):
            return resolved
    return area


def _grade_value(row: dict[str, Any]) -> float | None:
    for key in ("grade", "등급", "석차등급", "converted_grade", "avg_grade"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(str(value).strip())
        except ValueError:
            continue
    return None


def _unit_value(row: dict[str, Any]) -> float:
    for key in ("unit", "units", "이수단위", "단위수"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            unit = float(str(value).strip())
            return unit if unit > 0 else 1.0
        except ValueError:
            continue
    return 1.0


def _is_regular_subject(row: dict[str, Any]) -> bool:
    value = str(
        row.get("course_type") or row.get("과목유형") or row.get("성취도") or ""
    ).strip()
    if "진로" in value:
        return False
    return True


def _subject_allowed(row: dict[str, Any], subject_flags: dict[str, Any]) -> bool:
    area = _subject_area_from_row(row)
    if not area:
        return True
    # 한국사 처리 (사장님 룰 2026-06-15 + 2026-06-17 확장):
    #  subject_flags의 한국사 값이 추출 과정에서 'O'가 아니라 '사회에 포함', 'O(사회 교과에
    #  포함)', '포함(사회)' 같은 설명문으로 들어오는 학교가 많다(경상국립·나사렛·남서울·전주 등).
    #  이를 != 'O'로 보고 제외하면 한국사가 반영교과인데도 빠져 평균등급이 왜곡된다(세명대 실사고).
    #  → 명시적 미반영(X/제외)만 거르고, 그 외(키 없음/반영 의도 문자열)는 사회 교과로 흡수한다.
    if area == "한국사":
        hs = str(subject_flags.get("한국사") or "").strip().upper()
        if hs.startswith("X") or hs in ("미반영", "제외", "반영안함"):
            return False
        if hs != "O":
            area = "사회"
    if area in subject_flags:
        return str(subject_flags.get(area) or "").upper() == "O"
    return str(subject_flags.get("기타") or "").upper() == "O"


def _within_semester_limit(
    row: dict[str, Any],
    limit: Any,
    student_context: dict[str, Any] | None = None,
) -> bool:
    """semester_limit(예: '1학년 1학기~3학년 1학기(졸업생 포함)') 마지막 학년/학기까지만 반영."""
    return within_semester_limit(row, limit, student_context)


def _weighted_average_grade(
    grades: list[dict[str, Any]],
    score_logic: dict[str, Any],
    student_context: dict[str, Any] | None = None,
) -> tuple[float | None, int, float, list[tuple[float, float]]]:
    # score_logic 산식 요소를 모두 반영한다 (2026-06-16, 관동대 실사고로 전면 재작성):
    #  subject_groups(교과군 한정) · semester_limit(학기 제한) · 진로선택 성취도 변환 +
    #  max_career_subjects(진로 최대 개수) · top_n(석차등급 우수 N과목) · credit_weighted(이수단위 가중).
    subject_flags = score_logic.get("subject_flags") or {}
    groups = score_logic.get("subject_groups")
    groups_set = set(groups) if isinstance(groups, list) and groups else None
    top_n = score_logic.get("top_n")
    max_career = score_logic.get("max_career_subjects")
    semester_limit = score_logic.get("semester_limit")
    credit_weighted = score_logic.get("credit_weighted")
    credit_weighted = True if credit_weighted is None else bool(credit_weighted)
    career_conv = score_logic.get("career_conversion") or {"A": 1.0, "B": 2.0, "C": 4.0}
    regular_only = str(score_logic.get("regular_subjects") or "").upper() == "O"
    career_subjects = str(score_logic.get("career_subjects") or "").strip().upper()
    career_enabled = career_subjects in {"O", "Y", "YES", "TRUE", "1", "반영"}

    regular: list[tuple[float, float, str]] = []  # (석차등급, 이수단위, 교과) — 등급 있는 일반과목
    career: list[tuple[float, float, str]] = []    # 진로선택(성취도 변환)
    for row in grades:
        if not isinstance(row, dict):
            continue
        area = _subject_area_from_row(row)
        # 반영교과 필터: subject_groups가 있으면 그 교과군만, 없으면 subject_flags 규칙
        if groups_set is not None:
            if area not in groups_set:
                continue
        elif not _subject_allowed(row, subject_flags):
            continue
        if not _within_semester_limit(row, semester_limit, student_context):
            continue
        unit = _unit_value(row)
        grade = _grade_value(row)
        if grade is not None:
            regular.append((grade, unit, area))
        else:
            # 석차등급 없는 과목: 진로선택만 성취도→등급 환산해 반영한다(대학 요강 표준).
            # 과학탐구실험·사회탐구실험 등 '일반선택 성취도평가' 과목은 석차등급이 없으므로
            # 반영하지 않는다(2026-06-17 강남대 실사고 — 진로 오분류). course_type으로 구분하며,
            # 구 데이터(course_type 미지정 NULL)는 하위호환으로 기존처럼 성취도 환산한다.
            ctype = str(row.get("과목구분") or row.get("course_type") or "").strip()
            if ctype in ("일반선택", "공통", "공통과목", "일반"):
                continue
            ach = str(row.get("성취도") or row.get("achievement") or "").strip().upper()
            if uses_achievement_ratio_grade(score_logic):
                gv = achievement_ratio_grade(row, ach)
            else:
                gv = career_conv.get(ach)
            if gv is not None:
                career.append((float(gv), unit, area))
    # top_groups: 반영교과(subject_groups) 중 평균이 우수한 N개 교과만 골라 그 교과 '전 과목'을
    #  반영한다(예: 나사렛 국·수·영·사·과 중 우수 3개 교과별 전 과목). 과목 단위 top_n과 다른
    #  층위 — 교과군을 먼저 추린 뒤 그 안에서 max_career/top_n을 적용한다.
    top_groups_limit = _optional_positive_int(score_logic.get("top_groups"))
    if top_groups_limit is not None and groups_set:
        grp: dict[str, list[tuple[float, float]]] = {}
        for grade, unit, ar in regular:
            grp.setdefault(ar, []).append((grade, unit))
        group_avg: dict[str, float] = {}
        for ar, items in grp.items():
            tu = sum(u for _, u in items)
            if tu > 0:
                group_avg[ar] = sum(gr * u for gr, u in items) / tu
        best_groups = set(sorted(group_avg, key=lambda a: group_avg[a])[:top_groups_limit])
        regular = [r for r in regular if r[2] in best_groups]
        career = [c for c in career if c[2] in best_groups]
    # 진로선택: career_subjects=O가 명시되면 regular_subjects=O와 무관하게 반영한다.
    # career_subjects가 없고 regular_subjects=O인 구형 행은 기존처럼 진로를 제외한다.
    max_career_limit = _optional_positive_int(max_career)
    if career_subjects in {"X", "N", "NO", "FALSE", "0", "미반영"}:
        career = []
    elif regular_only and not career_enabled and max_career_limit is None:
        career = []
    elif max_career_limit is not None:
        career = sorted(career, key=lambda x: (x[0], -x[1]))[:max_career_limit]
    # top_n: 석차등급 우수(낮은 등급) 상위 N과목, 동점이면 이수단위 높은 과목 우선.
    #  top_n_scope="per_subject_group"이면 반영교과(subject_groups)별로 각각 상위 N과목을
    #  뽑아 합친다 — 예: 한국교통대 국·영·수·사 교과별 상위 3 = 총 12과목.
    #  기본(미지정)은 전체 풀에서 상위 N. 이 둘을 혼동하면 등급 낮은 학생도 상위 몇 과목만
    #  잡혀 과대평가된다(2026-06-16 조선대·한국교통대 실사고).
    top_n_limit = _optional_positive_int(top_n)
    top_n_scope = str(score_logic.get("top_n_scope") or "").strip().lower()
    per_group = top_n_scope in ("per_subject_group", "per_group", "교과별")
    # regular_top_n: 일반과목만 상위 N (진로선택은 위 max_career로 별도 제한). PDF가
    #  '일반 상위 15과목 + 진로선택 상위 3과목'처럼 일반/진로를 따로 세는 학교용
    #  (예: 백석대 15+3, 목원대 5+3). 통합 top_n과 구분된다.
    regular_top_n_limit = _optional_positive_int(score_logic.get("regular_top_n"))
    # group_top_n: 교과군별로 '다른' 상위 N (요강대로). 예) 경운대 국영수 상위6 + 사과한 상위3,
    #  경국대 국영수 상위7 + 사과한 상위2. {"국어,영어,수학": 6, "사회,과학,한국사": 3}.
    #  각 교과군에서 진로선택 포함 통합 상위 N을 뽑아 합친다.
    group_top_n = score_logic.get("group_top_n")
    if isinstance(group_top_n, dict) and group_top_n:
        # 각 교과군에서 상위 N을 뽑되, '_remainder'/'전체'/'모든과목' 키는 아직 안 뽑힌
        # 잔여 과목 풀에서 추가 상위 N (예: 경국대 국영수7 + 사과한2 + 모든과목3 = 12).
        pool_all = [(g, u, a) for g, u, a in regular] + [(g, u, a) for g, u, a in career]
        used = [False] * len(pool_all)
        selected_g: list[tuple[float, float]] = []
        remainder_n = None
        for grp_key, gn in group_top_n.items():
            if str(grp_key) in ("_remainder", "전체", "모든과목", "나머지"):
                remainder_n = _optional_positive_int(gn)
                continue
            gn_i = _optional_positive_int(gn)
            if gn_i is None:
                continue
            grp_areas = {a.strip() for a in str(grp_key).split(",")}
            idxs = [i for i, (g, u, a) in enumerate(pool_all) if a in grp_areas and not used[i]]
            idxs.sort(key=lambda i: (pool_all[i][0], -pool_all[i][1]))
            for i in idxs[:gn_i]:
                used[i] = True
                selected_g.append((pool_all[i][0], pool_all[i][1]))
        if remainder_n is not None:
            idxs = [i for i in range(len(pool_all)) if not used[i]]
            idxs.sort(key=lambda i: (pool_all[i][0], -pool_all[i][1]))
            for i in idxs[:remainder_n]:
                selected_g.append((pool_all[i][0], pool_all[i][1]))
        pool = selected_g
    elif regular_top_n_limit is not None:
        regular = sorted(regular, key=lambda x: (x[0], -x[1]))[:regular_top_n_limit]
        pool = [(g, u) for g, u, _ in regular] + [(g, u) for g, u, _ in career]
    elif top_n_limit is not None and per_group and groups_set:
        by_group: dict[str, list[tuple[float, float, str]]] = {}
        for item in regular:
            by_group.setdefault(item[2], []).append(item)
        selected: list[tuple[float, float, str]] = []
        for items in by_group.values():
            selected.extend(sorted(items, key=lambda x: (x[0], -x[1]))[:top_n_limit])
        pool = [(g, u) for g, u, _ in selected] + [(g, u) for g, u, _ in career]
    elif top_n_limit is not None:
        merged = [(g, u) for g, u, _ in regular] + [(g, u) for g, u, _ in career]
        pool = sorted(merged, key=lambda x: (x[0], -x[1]))[:top_n_limit]
    else:
        pool = [(g, u) for g, u, _ in regular] + [(g, u) for g, u, _ in career]
    if not pool:
        return None, 0, 0.0, []
    if credit_weighted:
        tu = sum(u for _, u in pool)
        if tu <= 0:
            return None, len(pool), 0.0, pool
        return sum(g * u for g, u in pool) / tu, len(pool), tu, pool
    return sum(g for g, _ in pool) / len(pool), len(pool), sum(u for _, u in pool), pool


def _score_from_grade_table(avg_grade: float, grade_points: dict[str, Any]) -> float | None:
    points: dict[int, float] = {}
    for grade, point in (grade_points or {}).items():
        try:
            points[int(float(str(grade)))] = float(str(point))
        except (TypeError, ValueError):
            continue

    if not points:
        return None

    if avg_grade <= min(points):
        return points[min(points)]

    if avg_grade >= max(points):
        return points[max(points)]

    lower = int(avg_grade)
    upper = lower if avg_grade == lower else lower + 1

    if lower == upper or upper not in points or lower not in points:
        nearest = min(points, key=lambda g: abs(g - avg_grade))
        return points[nearest]

    ratio = avg_grade - lower
    return points[lower] + (points[upper] - points[lower]) * ratio


def _missing_achievement_ratio_inputs(
    grades: list[dict[str, Any]],
    score_logic: dict[str, Any],
    student_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not uses_achievement_ratio_grade(score_logic):
        return []

    subject_flags = score_logic.get("subject_flags") or {}
    groups = score_logic.get("subject_groups")
    groups_set = set(groups) if isinstance(groups, list) and groups else None
    semester_limit = score_logic.get("semester_limit")
    missing: list[dict[str, Any]] = []

    for grade_row in grades:
        if not isinstance(grade_row, dict):
            continue
        area = _subject_area_from_row(grade_row)
        if groups_set is not None:
            if area not in groups_set:
                continue
        elif not _subject_allowed(grade_row, subject_flags):
            continue
        if not _within_semester_limit(grade_row, semester_limit, student_context):
            continue
        if _grade_value(grade_row) is not None:
            continue
        ctype = str(grade_row.get("과목구분") or grade_row.get("course_type") or "").strip()
        if ctype in ("일반선택", "공통", "공통과목", "일반"):
            continue
        ach = str(grade_row.get("성취도") or grade_row.get("achievement") or "").strip().upper()
        if ach not in {"B", "C"}:
            continue
        if achievement_ratio_grade(grade_row, ach) is not None:
            continue
        missing.append(
            {
                "grade": grade_row.get("학년") or grade_row.get("grade"),
                "semester": grade_row.get("학기") or grade_row.get("semester"),
                "subject": grade_row.get("과목") or grade_row.get("subject"),
                "achievement": ach,
            }
        )
    return missing
