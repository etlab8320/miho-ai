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
    # 한국사: 산식에 '한국사' 플래그가 따로 없으면 사회 교과로 판정 (사장님 룰 2026-06-15).
    if area == "한국사" and "한국사" not in subject_flags:
        area = "사회"
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



# confidence 라벨은 검증 파이프라인이 진화하며 15종으로 늘었다 (verified,
# official_verified, official_pdf_codex_verified, ...). "verified"를 포함하되
# 계산 불가 표식(non_calc/non_auto/absent/not_in_guide)이 붙은 건 제외한다.
_NON_CALC_MARKERS = ("non_calc", "non_auto", "absent", "not_in_guide")


def _is_calculable_confidence(confidence: str | None) -> bool:
    text = str(confidence or "").lower()
    if "verified" not in text:
        return False
    return not any(marker in text for marker in _NON_CALC_MARKERS)


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

    if not _is_calculable_confidence(confidence) or not isinstance(score_logic, dict):
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

    result = {
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
    vs_prev = _vs_prev_year(conn, university_id, record_score)
    if vs_prev:
        result["vs_prev_year"] = vs_prev
    return result


def _first_number(value: Any) -> float | None:
    import re

    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    try:
        return float(match.group()) if match else None
    except ValueError:
        return None


def _vs_prev_year(conn: sqlite3.Connection, university_id: str, record_score: float) -> dict[str, Any] | None:
    """추측 금지 원칙의 코드판: (내신환산 + 실기만점)이 전년도 최종합 총점에
    닿는지 판정해 숫자와 함께 돌려준다. 설명문 룰은 도구를 안 부르는 턴에는
    보이지 않으므로(2026-06-12 강원대 상향 오추천 실사고), 판정을 데이터에 박는다."""
    try:
        row = conn.execute(
            "SELECT c.admission_result_26_json, c.calculation_test_json, c.score_logic_json, d.raw_json "
            "FROM susi_calculation_rules c "
            "LEFT JOIN db_university_rows d ON d.university_id = c.university_id "
            "WHERE c.university_id = ?",
            (university_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    raw = _json_loads(row["raw_json"], {})
    practical_max = _first_number(raw.get("실기만점"))
    if practical_max is None:
        # raw.실기만점은 223/376 결손이지만 실기만점은 검증된 산식
        # (calculation_test_json.plugin_practical_full_score)에 박혀 있다.
        # 학생 record_score가 같은 산식으로 계산되므로 스케일이 일치한다.
        ct = _json_loads(row["calculation_test_json"], {}) or {}
        if isinstance(ct, dict):
            practical_max = _first_number(ct.get("plugin_practical_full_score"))
    r26 = _json_loads(row["admission_result_26_json"], {}) or {}
    if not isinstance(r26, dict):
        return None
    score_logic = _json_loads(row["score_logic_json"], {}) or {}
    grade_points = score_logic.get("grade_points") if isinstance(score_logic, dict) else None

    def _rescaled_cut(cut: Any) -> tuple[float | None, float | None]:
        # 작년 합격컷을 올해 산식 스케일로 재환산한다. 작년 점수 만점이 학교마다
        # 제각각(안양대 100점 vs 강원대 1600점)이라 직접 비교가 틀린다(2026-06-15 실사고).
        # 작년 합격자 평균등급을 올해 grade_points로 환산해 내신 재환산점을 얻고,
        # (재환산점 / 작년내신점) 비율을 작년 총점에 곱해 올해 스케일 총점을 만든다.
        cut = cut if isinstance(cut, dict) else {}
        total_raw = _first_number(cut.get("total_score"))
        record_raw = _first_number(cut.get("record_score"))
        grade = _first_number(cut.get("grade"))
        rec_olscale = None
        if grade is not None and grade_points:
            rec_olscale = _score_from_grade_table(grade, grade_points)
        if rec_olscale is not None and record_raw and record_raw > 0 and total_raw is not None:
            scale = rec_olscale / record_raw
            return round(total_raw * scale, 2), rec_olscale
        return total_raw, rec_olscale  # 등급/산식 없으면 원본 총점(스케일 일치 학교) 사용

    final_cut, prev_final_rec = _rescaled_cut(r26.get("final_pass_cutoff"))
    first_cut, prev_first_rec = _rescaled_cut(r26.get("first_pass_cutoff"))
    if practical_max is None or final_cut is None:
        return None
    max_total = round(record_score + practical_max, 2)
    reachable = max_total >= final_cut
    info: dict[str, Any] = {
        "practical_max": practical_max,
        "max_possible_total": max_total,
        "prev_final_total": final_cut,
        "prev_first_total": first_cut,
        "prev_final_record_rescaled": prev_final_rec,
        "prev_first_record_rescaled": prev_first_rec,
        "reachable_at_full_practical": reachable,
    }
    # 1단계(내신) 통과 가능성 — 작년 1단계 합격자 내신(올해 재환산) 기준 (사장님 룰 2026-06-15).
    # 단 1단계 내신 비중이 0/빈값인 전형(서경대형 1단계 실기100%)은 내신 무관이라 판정에서 뺀다.
    stage_weights = score_logic.get("stage_weights") if isinstance(score_logic, dict) else None
    stage1_rec_weight = _first_number((stage_weights or {}).get("stage1_student_record"))
    info["stage1_uses_record"] = bool(stage1_rec_weight and stage1_rec_weight > 0)
    if prev_first_rec is not None and info["stage1_uses_record"]:
        info["stage1_record_reachable"] = record_score >= prev_first_rec
    if not reachable:
        info["warning"] = (
            f"실기 만점({practical_max:g})을 받아도 합산 {max_total:g}점이 전년도 최종합 "
            f"{final_cut:g}점(올해 산식 환산)에 미달 — 이 학교는 상향으로도 추천 금지."
        )
    return info


# ---------------------------------------------------------------------------
# 전년도(26susi) 원본 조회 — Vultr DB read-only
# ---------------------------------------------------------------------------
# 추천 크로스체크용: 작년 전형 구조(내신:실기 비중, 실기만점, 정원, 실기 종목)를
# 원본에서 직접 확인한다. 사장님 승인(2026-06-12) — ssh vultr 경유 read-only SELECT.

import re as _re
import shlex as _shlex
import subprocess as _subprocess

_PREV_YEAR_DB = "26susi"
_SAFE_TERM_RE = _re.compile(r"[^\w가-힣%·()\s.-]")


def _safe_like_term(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return _SAFE_TERM_RE.sub("", text)[:60]


def _vultr_mysql(sql: str, timeout: int = 12) -> list[list[str]]:
    proc = _subprocess.run(
        # ssh는 원격 인자를 셸로 합치므로 SQL(백틱 포함)을 통째로 quote해야 한다
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", "vultr", f"mysql -N -B -e {_shlex.quote(sql)}"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:200] or "vultr mysql query failed")
    return [line.split("\t") for line in proc.stdout.splitlines() if line.strip()]


def lookup_prev_year(
    university: str | None = None,
    department: str | None = None,
    admission_track: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    uni = _safe_like_term(university)
    dept = _safe_like_term(department)
    track = _safe_like_term(admission_track)
    if not any((uni, dept)):
        return {"error": "university 또는 department 중 하나는 필요해."}
    conds = []
    if uni:
        conds.append(f"대학명 LIKE '%{uni}%'")
    if dept:
        conds.append(f"학과명 LIKE '%{dept}%'")
    if track:
        conds.append(f"전형명 LIKE '%{track}%'")
    limit = max(1, min(int(limit or 8), 20))
    sql = (
        "SELECT 대학ID, 실기ID, 대학명, 학과명, 전형명, 정원, "
        "`1단계배수`, `1단계학생부`, `2단계내신`, `2단계실기`, `2단계면접`, "
        "수능최저, 실기만점, 내신교과 "
        f"FROM `{_PREV_YEAR_DB}`.`대학정보` WHERE {' AND '.join(conds)} LIMIT {limit}"
    )
    try:
        rows = _vultr_mysql(sql)
    except Exception as exc:
        return {"error": f"전년도(26susi) DB 조회 실패: {exc}. (Vultr ssh 접근이 가능한 환경에서만 동작해)"}

    cols = [
        "university_id", "practical_id", "university", "department", "admission_track",
        "quota", "stage1_multiple", "stage1_record", "stage2_record", "stage2_practical",
        "stage2_interview", "minimum_csat", "practical_max", "record_subjects",
    ]
    result = [dict(zip(cols, row)) for row in rows]

    practical_ids = sorted({r["practical_id"] for r in result if r.get("practical_id") and r["practical_id"] != "NULL"})
    events_by_id: dict[str, list[str]] = {}
    if practical_ids:
        id_list = ",".join(pid for pid in practical_ids if pid.isdigit())
        if id_list:
            try:
                ev_rows = _vultr_mysql(
                    f"SELECT DISTINCT 실기ID, 종목명 FROM `{_PREV_YEAR_DB}`.`26수시실기배점` WHERE 실기ID IN ({id_list})"
                )
                for pid, name in ev_rows:
                    events_by_id.setdefault(pid, []).append(name)
            except Exception:
                pass
    for r in result:
        r["practical_events_prev"] = events_by_id.get(str(r.get("practical_id")), [])

    return {"year": "26(전년도)", "count": len(result), "rows": result}


# ---------------------------------------------------------------------------
# 원콜 추천 파이프라인 — "정확성은 코드, 판단은 LLM"
# ---------------------------------------------------------------------------
# 추천의 기계적 체인(학생 성적 조회 → verified 룰 전수 환산 → 전년도 도달성
# 판정 → 정렬)을 단일 호출로 끝낸다. 2026-06-12 실사고: 이 체인을 LLM이 매 턴
# 도구를 더듬어 조립하느라 10분+ 배회 — 오케스트레이션 자체가 기계적인 일은
# 코드가 한다. LLM은 이 결과에서 학교를 고르고 서사만 쓴다.

_CENTRAL_LIFE_DB = pathlib.Path(os.path.expanduser("~/.miho/life_records/central.sqlite3"))


def _student_grades_from_central(student_query: str) -> tuple[str | None, list[dict[str, Any]]]:
    if not _CENTRAL_LIFE_DB.exists():
        return None, []
    conn = sqlite3.connect(_CENTRAL_LIFE_DB)
    conn.row_factory = sqlite3.Row
    try:
        student = conn.execute(
            "SELECT id, name FROM students WHERE name LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%{str(student_query or '').strip()}%",),
        ).fetchone()
        if student is None:
            return None, []
        rows = conn.execute(
            "SELECT grade, semester, category, subject, credits, rank_grade, achievement FROM central_grades WHERE student_id = ?",
            (student["id"],),
        ).fetchall()
        grades = [
            {
                "교과": r["category"], "과목": r["subject"], "이수단위": r["credits"],
                "등급": r["rank_grade"], "학년": r["grade"], "학기": r["semester"],
                "성취도": r["achievement"],
            }
            for r in rows
        ]
        return student["name"], grades
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 대학별 공식 사이드카 (susi27_university_formula_plugins)
# ---------------------------------------------------------------------------
# 등급표(weighted_grade_table)가 아닌 학교(예: 순천향 T×3+U×0.3-0.3)는 파이프라인
# 워크스페이스의 대학별 공식 플러그인이 진실이다. staging DB 옆에 살아 있으므로
# 거기서 lazy-load 한다. 공식이 없는 학교는 계산하지 않는다 (추측 금지).

_FORMULA_MODULE: Any = None
_FORMULA_LOAD_FAILED = False


def _formula_module() -> Any:
    global _FORMULA_MODULE, _FORMULA_LOAD_FAILED
    if _FORMULA_MODULE is not None or _FORMULA_LOAD_FAILED:
        return _FORMULA_MODULE
    import importlib.util
    import sys

    formula_dir = db_path().parent
    entry = formula_dir / "susi27_university_formula_plugins.py"
    if not entry.exists():
        _FORMULA_LOAD_FAILED = True
        return None
    try:
        if str(formula_dir) not in sys.path:
            sys.path.insert(0, str(formula_dir))
        spec = importlib.util.spec_from_file_location("susi27_university_formula_plugins", entry)
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("susi27_university_formula_plugins", module)
        spec.loader.exec_module(module)
        _FORMULA_MODULE = module
    except Exception:
        _FORMULA_LOAD_FAILED = True
        return None
    return _FORMULA_MODULE


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _formula_calculate(university: str, merged_row: dict[str, Any], grades: list[dict[str, Any]]) -> dict[str, Any] | None:
    module = _formula_module()
    if module is None:
        return None
    fn = (getattr(module, "REGISTRY", None) or {}).get(university)
    if fn is None:
        return None
    transcript = [
        module.SubjectRecord(
            grade=_int_or_none(g.get("학년")) or 0,
            semester=_int_or_none(g.get("학기")) or 0,
            category=str(g.get("교과") or ""),
            subject=str(g.get("과목") or ""),
            credit=float(_first_number(g.get("이수단위")) or 1.0),
            rank_grade=_int_or_none(g.get("등급")),
            achievement=(str(g.get("성취도")) if g.get("성취도") else None),
        )
        for g in grades
        if isinstance(g, dict)
    ]
    try:
        result = fn(merged_row, transcript, {})
    except Exception:
        return None
    data = result.to_dict() if hasattr(result, "to_dict") else None
    if not isinstance(data, dict) or data.get("record_score") is None:
        return None
    return data



# 지역(광역) 맵 — 27susi.대학정보에서 동기화한 로컬 캐시. 없거나 미스가 나면
# ssh vultr로 1회 갱신을 시도하고, 그래도 없으면 region 없이 동작한다.
_REGION_MAP_PATH = pathlib.Path(os.path.expanduser("~/.miho/academy_ops/susi_region_map.json"))
_REGION_MAP: dict[str, str] | None = None


def _region_map() -> dict[str, str]:
    global _REGION_MAP
    if _REGION_MAP is not None:
        return _REGION_MAP
    data = _json_loads(_REGION_MAP_PATH.read_text(encoding="utf-8") if _REGION_MAP_PATH.exists() else None, None)
    if not isinstance(data, dict) or not data:
        try:
            rows = _vultr_mysql("SELECT 대학ID, 광역 FROM `27susi`.`대학정보`")
            data = {r[0]: r[1] for r in rows if len(r) == 2}
            _REGION_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
            _REGION_MAP_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            data = {}
    _REGION_MAP = data if isinstance(data, dict) else {}
    return _REGION_MAP


_REGION_GROUPS = {
    "수도권": ["서울", "경기", "인천"],
    "충청": ["대전", "세종", "충남", "충북"],
    "강원": ["강원"],
    "영남": ["부산", "대구", "울산", "경남", "경북"],
    "경상": ["부산", "대구", "울산", "경남", "경북"],
    "호남": ["광주", "전남", "전북"],
    "전라": ["광주", "전남", "전북"],
    "제주": ["제주"],
}


def _parse_regions(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = _re.split(r"[,/·\s]+", str(value or ""))
    out = [str(v).strip() for v in items if str(v).strip()]
    if any(v in ("전국", "전체") for v in out):
        return []
    # 광역권명("수도권/충청권/강원권"...)을 region_map의 시도명으로 확장한다.
    # 입력이 이미 시도명("충남" 등)이면 그대로 둔다.
    expanded: list[str] = []
    for v in out:
        grp = _REGION_GROUPS.get(v) or _REGION_GROUPS.get(v.rstrip("권"))
        expanded.extend(grp if grp else [v])
    return list(dict.fromkeys(expanded))



# 전년도 트랙별 컷 캐시 — 26 확정 합격자들의 종목 기록 슬롯 패턴으로 트랙을
# 분리해 산출한 값 (수원대 실사고 2026-06-12: 전공/기초체력 컷이 한 줄로 섞여
# 비교 왜곡). 기본 판단 트랙 = 측정이 가장 완전한(슬롯 多) 코호트, 인원 3명
# 미만 코호트는 데이터 결손 노이즈로 무시.
_TRACK_CUTS_PATH = pathlib.Path(os.path.expanduser("~/.miho/academy_ops/susi26_track_cuts.json"))
_TRACK_CUTS: dict | None = None


def _track_cuts(university_id: str) -> tuple[dict | None, list[dict]]:
    global _TRACK_CUTS
    if _TRACK_CUTS is None:
        data = _json_loads(_TRACK_CUTS_PATH.read_text(encoding="utf-8") if _TRACK_CUTS_PATH.exists() else None, None)
        _TRACK_CUTS = data if isinstance(data, dict) else {}
    tracks = [
        t for t in (_TRACK_CUTS.get(str(university_id)) or [])
        if t.get("n_students", 0) >= 3 and (t.get("final_cut_total") or t.get("first_cut_total"))
    ]
    if not tracks:
        return None, []
    default = max(tracks, key=lambda t: (t.get("slot_count", 0), t.get("n_students", 0)))
    return default, tracks


def recommend_candidates(
    student_query: str,
    university: str | None = None,
    department: str | None = None,
    admission_track: str | None = None,
    region: Any = None,
    max_candidates: int = 30,
) -> dict[str, Any]:
    if region is None or str(region).strip() == "":
        # 사장님 설계(2026-06-12): 지역은 도구가 요구한다 — 설명문 지시는 대화
        # 관성에 밀려 무시되므로(실사고 2회) 코드에서 강제한다.
        return {
            "need_region": True,
            "message": (
                "region 인자가 비었다. 두 경우로 나뉜다: "
                "(1) 사용자가 이 대화에서 이미 지역을 말했다면(직전 메시지 포함) — 그 표현을 그대로 "
                "region에 넣어 즉시 다시 호출하라 (예: region='서울, 경기, 인천, 강원, 대전'). "
                "(2) 아직 안 말했다면 — '지역은 어디로 볼까요? (예: 강원·경기·서울·인천, 또는 전국)'만 "
                "보내고 턴을 끝내라. 사용자가 말한 적 없는 지역을 네가 지어내는 것만 금지다."
            ),
        }
    student_name, grades = _student_grades_from_central(student_query)
    if not grades:
        return {
            "error": f"중앙 생기부 DB에서 '{student_query}' 학생의 확정 성적을 찾지 못했어. "
            "생기부 인제스트/검수(life_record_confirm)가 끝난 학생만 추천 계산이 가능해."
        }

    wanted_regions = _parse_regions(region)

    conn = _connect()
    conds = ["c.confidence LIKE '%verified%'", "c.admission_result_26_json IS NOT NULL", "c.admission_result_26_json != ''"]
    params: list[Any] = []
    for term, col in ((university, "c.university"), (department, "c.department"), (admission_track, "c.admission_track")):
        clean = _safe_like_term(term)
        if clean:
            conds.append(f"{col} LIKE ?")
            params.append(f"%{clean}%")
    rule_rows = conn.execute(
        f"SELECT c.university_id, c.university, c.department, c.admission_track, "
        f"c.practical_events_json, c.calculation_test_json, d.raw_json "
        f"FROM susi_calculation_rules c "
        f"LEFT JOIN db_university_rows d ON d.university_id = c.university_id "
        f"WHERE {' AND '.join(conds)}",
        params,
    ).fetchall()

    candidates = []
    skipped = {"calc_failed": 0, "unreachable": 0, "stage1_blocked": 0, "non_practical": 0}
    for row in rule_rows:
        # 실기전형만 추천 대상 — 같은 학과의 비실기 전형(교과100/농어촌·종합 서류, 실기만점 0)을
        # 후보에서 제외한다. 실기 미반영 전형은 작년 결과·실기만점이 없어 빈칸을 만든다.
        ct = _json_loads(row["calculation_test_json"], {}) or {}
        practical_full = _first_number(ct.get("plugin_practical_full_score")) if isinstance(ct, dict) else None
        if practical_full is None:
            practical_full = _first_number(_json_loads(row["raw_json"], {}).get("실기만점"))
        if not practical_full or practical_full <= 0:
            # 실기만점 데이터가 없어도 실기종목이 등록돼 있으면 실기전형으로 인정 (누락 방지).
            _ev = _json_loads(row["practical_events_json"], None)
            _events = _ev.get("events") if isinstance(_ev, dict) else _ev
            if not _events:
                skipped["non_practical"] += 1
                continue
        calc = calculate_score(row["university_id"], grades, {}, {})
        if calc.get("status") != "calculated":
            raw_for_formula = _json_loads(row["raw_json"], {})
            formula = _formula_calculate(row["university"], dict(raw_for_formula), grades)
            if formula is None:
                skipped["calc_failed"] += 1
                continue
            conn_calc = _connect()
            calc = {
                "status": "calculated",
                "student_record_score": round(float(formula["record_score"]), 4),
                "average_grade": formula.get("reflected_average_grade"),
                "formula_key": formula.get("formula_key"),
            }
            vs_f = _vs_prev_year(conn_calc, row["university_id"], float(formula["record_score"]))
            if vs_f:
                calc["vs_prev_year"] = vs_f
        vs = calc.get("vs_prev_year") or {}
        if not vs:
            skipped["calc_failed"] += 1
            continue
        # 트랙별 컷이 있으면 기본 판단 트랙(완전 측정) 컷으로 교체 — 혼합 컷 왜곡 방지
        default_track, all_tracks = _track_cuts(row["university_id"])
        track_note = None
        if default_track and (default_track.get("final_cut_total") or default_track.get("first_cut_total")):
            t_final = default_track.get("final_cut_total") or default_track.get("first_cut_total")
            vs = dict(vs)
            vs["prev_final_total"] = float(t_final)
            if default_track.get("first_cut_total"):
                vs["prev_first_total"] = float(default_track["first_cut_total"])
            pm = _first_number(vs.get("practical_max")) or 0.0
            rec_now = _first_number(calc.get("student_record_score")) or 0.0
            vs["max_possible_total"] = round(rec_now + pm, 2)
            vs["reachable_at_full_practical"] = vs["max_possible_total"] >= vs["prev_final_total"]
            if len(all_tracks) > 1:
                track_note = (
                    f"전년도 컷은 실기 트랙 {len(all_tracks)}개로 분리 산출 — 기본 판단은 "
                    f"완전 측정 트랙({', '.join(default_track.get('events', []))}, {default_track.get('n_students')}명) 기준. "
                    "다른 트랙(전공 등)은 prev_tracks를 보고 따로 설명하라."
                )
        # 1단계 내신 미달 제외 — 1단계가 내신을 반영하는 전형만 (사장님 룰 2026-06-15).
        # 서경대형(1단계 실기100%, stage1_uses_record=False)은 내신 무관이라 예외.
        if vs.get("stage1_uses_record") and vs.get("stage1_record_reachable") is False:
            skipped["stage1_blocked"] += 1
            continue
        if not vs.get("reachable_at_full_practical"):
            skipped["unreachable"] += 1
            continue
        raw = _json_loads(row["raw_json"], {})
        ev = _json_loads(row["practical_events_json"], None) or {}
        events = ev.get("events") if isinstance(ev, dict) else ev
        event_names = [e.get("name") if isinstance(e, dict) else str(e) for e in (events or [])][:6]
        record = calc["student_record_score"]
        # 적정/상향 제안: 작년 최종합격자의 내신환산보다 높으면 적정 출발선
        prev_final_record = None
        prev_winner_practical = None
        prev_winner_grade = None
        stage1 = {}
        try:
            extra = conn.execute(
                "SELECT admission_result_26_json, admission_meta_json FROM susi_calculation_rules WHERE university_id = ?",
                (row["university_id"],),
            ).fetchone()
            r26 = _json_loads(extra[0], {})
            fp = (r26.get("final_pass_cutoff") or {}) if isinstance(r26, dict) else {}
            prev_final_record = _first_number(fp.get("record_score"))
            prev_winner_practical = _first_number(fp.get("practical_score"))
            prev_winner_grade = _first_number(fp.get("grade"))
            meta = _json_loads(extra[1], {}) or {}
            stage1 = meta.get("stage1") if isinstance(meta.get("stage1"), dict) else {}
        except Exception:
            pass
        # 1단계 선발(등급 컷) 신호 — 한체대류: 총점 도달성만으로 판단하면 안 된다.
        student_grade = _first_number(calc.get("average_grade"))
        has_stage1 = bool(str((stage1 or {}).get("multiple") or "").strip())
        stage1_info = None
        if has_stage1:
            stage1_info = {
                "has_stage1": True,
                "stage1_multiple": (stage1 or {}).get("multiple"),
                "prev_winner_avg_grade": prev_winner_grade,
                "student_avg_grade": student_grade,
            }
            # 명백 미달(작년 합격자 평균 +1.0 초과)은 후보 진입 자체를 막는다 —
            # 못 가는 학교는 경고 딸고 보여주는 게 아니라 아예 입에 안 올린다
            # (사장님 2026-06-12: "얘기해봐야 학생이 아쉬워만 하는거지").
            if student_grade is not None and prev_winner_grade is not None and student_grade > prev_winner_grade + 1.0:
                skipped["stage1_blocked"] += 1
                continue
            if student_grade is not None and prev_winner_grade is not None and student_grade > prev_winner_grade + 0.5:
                stage1_info["warning"] = (
                    f"1단계 선발이 있는 전형 — 작년 최종합격자 평균등급 {prev_winner_grade:g}인데 "
                    f"학생 평균등급이 {student_grade:g}라 1단계 통과 자체가 어렵다. 추천에서 빼거나 명시 경고 필수."
                )
        suggested = "적정" if (prev_final_record is not None and record >= prev_final_record) else "상향"
        margin = round(vs["max_possible_total"] - vs["prev_final_total"], 2)
        # 핵심 지표(사장님 피드백 2026-06-12): 만점 여유가 아니라 "합격에 필요한
        # 실기 득점률"이 진짜 난이도다. 작년 합격자의 실제 실기 득점률과 나란히 본다.
        practical_max_n = _first_number(vs.get("practical_max")) or 0.0
        needed_practical_rate = None
        prev_winner_practical_rate = None
        if practical_max_n > 0:
            needed_practical_rate = round(max(0.0, (vs["prev_final_total"] - record)) / practical_max_n * 100, 1)
            if prev_winner_practical is not None:
                prev_winner_practical_rate = round(prev_winner_practical / practical_max_n * 100, 1)
        cand_region = _region_map().get(str(row["university_id"]), "")
        if wanted_regions and cand_region not in wanted_regions:
            skipped["region_filtered"] = skipped.get("region_filtered", 0) + 1
            continue
        candidates.append(
            {
                "university_id": row["university_id"],
                "region": cand_region,
                "university": row["university"],
                "department": row["department"],
                "admission_track": row["admission_track"],
                "student_record_score": record,
                "practical_max": vs.get("practical_max"),
                "max_possible_total": vs.get("max_possible_total"),
                "prev_first_total": vs.get("prev_first_total"),
                "prev_final_total": vs.get("prev_final_total"),
                "prev_final_record": prev_final_record,
                "student_avg_grade": student_grade,
                "prev_winner_avg_grade": prev_winner_grade,
                "stage1": stage1_info,
                "prev_tracks": all_tracks if len(all_tracks) > 1 else None,
                "track_note": track_note,
                "margin_at_full_practical": margin,
                "needed_practical_rate_pct": needed_practical_rate,
                "prev_winner_practical_rate_pct": prev_winner_practical_rate,
                "suggested_verdict": suggested,
                "practical_events": event_names,
                "quota": raw.get("정원"),
                "stage_record_practical": f"{raw.get('내신교과') or '?'}:{raw.get('실기만점') or '?'}",
            }
        )

    # 정렬: 필요 실기 득점률이 낮은 학교(현실적으로 쉬운 순)부터. 지표가 없으면 뒤로.
    candidates.sort(
        key=lambda c: (
            c["needed_practical_rate_pct"] if c["needed_practical_rate_pct"] is not None else 999.0,
            -c["margin_at_full_practical"],
        )
    )
    max_candidates = max(1, min(int(max_candidates or 30), 60))
    total = len(candidates)
    candidates = candidates[:max_candidates]
    result_payload_note_region = ""
    if wanted_regions and total == 0:
        result_payload_note_region = (
            f"요청 지역({', '.join(wanted_regions)})에는 도달 가능한 추천 후보가 없다 — "
            "사용자에게 알리고 전국 기준(region 없이)으로 다시 호출할지 물어라. "
        )
    return {
        "student": student_name,
        "region_filter": wanted_regions or "전국",
        "grade_rows_used": len(grades),
        "total_feasible": total,
        "returned": len(candidates),
        "skipped": skipped,
        "note": (
            result_payload_note_region
            + "정렬은 needed_practical_rate_pct(합격에 필요한 실기 득점률, 낮을수록 현실적) 오름차순. "
            "prev_winner_practical_rate_pct(작년 합격자의 실제 실기 득점률)와 비교해 난이도를 설명하라. "
            "전 후보는 verified 룰 + 전년도 결과가 있는 학교만이며, 실기 만점으로도 전년도 최종합에 "
            "못 닿는 학교는 이미 제외됐다. suggested_verdict는 제안일 뿐 — 최종 분류와 서사는 네 판단."
        ),
        "candidates": candidates,
    }
