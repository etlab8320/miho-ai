"""Service layer for the 2027 수시엔진 staging/calculation plugin.

The rule engine is deliberately strict: it calculates only when a row has a
verified ``score_logic_json``. Until the extraction pass fills those rules, the
plugin returns a clear unverified status rather than inventing formulas.
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
from typing import Any


DEFAULT_DB = pathlib.Path(
    "/Users/etlab/.miho/discord/guilds/1507988396235296778/channels/10___1508422955460198420/threads/thread__1513557600497565696/work/susi27_pipeline/susi27_staging.sqlite3"
)


def db_path() -> pathlib.Path:
    return pathlib.Path(os.getenv("MIHO_SUSI27_STAGING_DB", str(DEFAULT_DB))).expanduser()


def _connect() -> sqlite3.Connection:
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(f"수시27 staging DB가 아직 없어: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _like(value: str | None) -> str:
    return f"%{value or ''}%"


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def lookup_rules(
    university: str | None = None,
    department: str | None = None,
    admission_track: str | None = None,
    limit: int = 20,
    detail: bool = False,
) -> dict[str, Any]:
    # 기본은 요약 모드: 추천/리포트에 필요한 필드만 반환한다. score_logic 같은
    # 엔진 내부 룰 JSON(행당 수천 자)은 calculate_score가 university_id로 DB에서
    # 직접 읽으므로 에이전트 컨텍스트에 실을 필요가 없다 — 20행 풀 반환이
    # 컨텍스트 폭발(압축 루프)을 일으킨 실사고(2026-06-12) 재발 방지.
    conn = _connect()
    sql = """
    SELECT r.university_id, r.university, r.department, r.admission_track, r.track_normalized,
           r.source_status, r.status, r.reason,
           c.confidence, c.score_logic_json, c.attendance_logic_json, c.practical_events_json,
           c.admission_meta_json, c.eligibility_json, c.school_info_json, c.admission_result_26_json,
           d.raw_json, d.text_path
      FROM rule_extraction_queue r
      LEFT JOIN susi_calculation_rules c ON c.university_id = r.university_id
      LEFT JOIN db_university_rows d ON d.university_id = r.university_id
     WHERE (? IS NULL OR r.university LIKE ?)
       AND (? IS NULL OR r.department LIKE ?)
       AND (? IS NULL OR r.admission_track LIKE ? OR r.track_normalized LIKE ?)
     ORDER BY r.priority ASC, r.university, r.department, r.admission_track
     LIMIT ?
    """
    rows = conn.execute(
        sql,
        (
            university,
            _like(university),
            department,
            _like(department),
            admission_track,
            _like(admission_track),
            _like(admission_track),
            max(1, min(int(limit or 20), 100)),
        ),
    ).fetchall()

    result = []
    for row in rows:
        raw = _json_loads(row["raw_json"], {})
        item = {
            "university_id": row["university_id"],
            "university": row["university"],
            "department": row["department"],
            "admission_track": row["admission_track"],
            "track_normalized": row["track_normalized"],
            "confidence": row["confidence"] or "unverified",
            "quota": raw.get("정원"),
            "practical_max": raw.get("실기만점"),
            "max_expected_cut": raw.get("27맥스예상컷"),
            "admission_meta": _json_loads(row["admission_meta_json"], None),
            "admission_result_26": _json_loads(row["admission_result_26_json"], None),
            "practical_events": _json_loads(row["practical_events_json"], None),
        }
        if detail:
            item.update(
                {
                    "source_status": row["source_status"],
                    "queue_status": row["status"],
                    "reason": row["reason"],
                    "text_path": row["text_path"],
                    "db_snapshot": {
                        "quota": raw.get("정원"),
                        "student_record_subjects": raw.get("내신교과"),
                        "attendance": raw.get("내신출결"),
                        "practical_id": raw.get("실기ID"),
                        "practical_max": raw.get("실기만점"),
                        "max_expected_cut": raw.get("27맥스예상컷"),
                    },
                    "score_logic": _json_loads(row["score_logic_json"], None),
                    "attendance_logic": _json_loads(row["attendance_logic_json"], None),
                    "eligibility": _json_loads(row["eligibility_json"], None),
                    "school_info": _json_loads(row["school_info_json"], None),
                }
            )
        result.append(item)

    return {"db_path": str(db_path()), "count": len(result), "rows": result}


def _norm_subject_area(value: Any) -> str:
    text = str(value or "").strip()
    aliases = {"국": "국어", "수": "수학", "영": "영어", "사": "사회", "과": "과학"}
    return aliases.get(text, text)


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
    area = _norm_subject_area(
        row.get("area") or row.get("교과") or row.get("subject_area") or row.get("과목군")
    )
    if not area:
        return True
    if area in subject_flags:
        return str(subject_flags.get(area) or "").upper() == "O"
    return str(subject_flags.get("기타") or "").upper() == "O"


def _weighted_average_grade(
    grades: list[dict[str, Any]],
    score_logic: dict[str, Any],
) -> tuple[float | None, int, float]:
    subject_flags = score_logic.get("subject_flags") or {}
    regular_only = str(score_logic.get("regular_subjects") or "").upper() == "O"
    weighted_sum = 0.0
    total_units = 0.0
    used = 0
    for grade_row in grades:
        if not isinstance(grade_row, dict):
            continue
        if regular_only and not _is_regular_subject(grade_row):
            continue
        if not _subject_allowed(grade_row, subject_flags):
            continue
        grade = _grade_value(grade_row)
        if grade is None:
            continue
        unit = _unit_value(grade_row)
        weighted_sum += grade * unit
        total_units += unit
        used += 1
    if total_units <= 0:
        return None, used, total_units
    return weighted_sum / total_units, used, total_units


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


def calculate_score(
    university_id: str,
    grades: list[dict[str, Any]],
    attendance: dict[str, Any],
    practical_records: dict[str, Any],
) -> dict[str, Any]:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM susi_calculation_rules WHERE university_id = ?",
        (university_id,),
    ).fetchone()

    if row is None:
        return {
            "university_id": university_id,
            "status": "missing_rule",
            "message": "아직 검증된 계산 룰이 없어. 요강 추출/검수 후 계산 가능.",
        }

    confidence = row["confidence"] or "unverified"
    score_logic = _json_loads(row["score_logic_json"], None)

    if confidence != "verified" or not isinstance(score_logic, dict):
        return {
            "university_id": university_id,
            "status": "unverified_rule",
            "confidence": confidence,
            "message": "검증 완료된 산식이 아니어서 계산을 중단했어. 추측 계산은 하지 않음.",
        }

    strategy = score_logic.get("strategy") or "weighted_grade_table"

    if strategy != "weighted_grade_table":
        return {
            "university_id": university_id,
            "status": "strategy_not_implemented",
            "strategy": strategy,
            "message": "룰은 검증됐지만 이 산식 전략의 실행기가 아직 연결되지 않았어.",
            "inputs_seen": {
                "grades": len(grades),
                "attendance_keys": sorted(attendance.keys()),
                "practical_events": sorted(practical_records.keys()),
            },
        }

    average_grade, used_subjects, total_units = _weighted_average_grade(grades, score_logic)

    if average_grade is None:
        return {
            "university_id": university_id,
            "status": "missing_grade_inputs",
            "confidence": confidence,
            "strategy": strategy,
            "message": "계산 가능한 룰은 있지만, 반영 교과/등급 입력이 부족해서 점수를 산출하지 못했어.",
            "input_rows": len(grades),
        }

    record_score = _score_from_grade_table(
        average_grade,
        score_logic.get("grade_points") or {},
    )

    if record_score is None:
        return {
            "university_id": university_id,
            "status": "missing_grade_table",
            "confidence": confidence,
            "strategy": strategy,
            "message": "평균등급은 계산했지만 등급별 환산점수표가 없어 최종 환산점수를 산출하지 못했어.",
            "average_grade": round(average_grade, 4),
        }

    return {
        "university_id": university_id,
        "status": "calculated",
        "confidence": confidence,
        "strategy": strategy,
        "average_grade": round(average_grade, 4),
        "used_subjects": used_subjects,
        "total_units": round(total_units, 2),
        "student_record_score": round(record_score, 4),
        "stage_weights": score_logic.get("stage_weights") or {},
        "subject_flags": score_logic.get("subject_flags") or {},
        "semester_weights": score_logic.get("semester_weights") or {},
        "attendance_seen": bool(attendance),
        "practical_records_seen": sorted(practical_records.keys()),
    }
