"""Previous-year result comparison and 26susi lookup helpers."""

from __future__ import annotations

import re as _re
import shlex as _shlex
import sqlite3
import subprocess as _subprocess
from typing import Any

from .db import _json_loads
from .grade_engine import _score_from_grade_table
from .utils import _first_number


_PREV_YEAR_DB = "26susi"
_SAFE_TERM_RE = _re.compile(r"[^\w가-힣%·()\s.-]")
_PREV_PRACTICAL_MAX_CACHE: dict[str, float | None] = {}


def _vs_prev_year(conn: sqlite3.Connection, university_id: str, record_score: float, record_only: bool = False) -> dict[str, Any] | None:
    """추측 금지 원칙의 코드판: (내신환산 + 실기만점)이 전년도 최종합 총점에
    닿는지 판정해 숫자와 함께 돌려준다. 설명문 룰은 도구를 안 부르는 턴에는
    보이지 않으므로(2026-06-12 강원대 상향 오추천 실사고), 판정을 데이터에 박는다."""
    try:
        row = conn.execute(
            "SELECT c.admission_result_26_json, c.calculation_test_json, c.score_logic_json, "
            "c.admission_meta_json, d.raw_json "
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
    ct = _json_loads(row["calculation_test_json"], {}) or {}
    practical_max = _first_number(raw.get("실기만점"))
    if practical_max is None and isinstance(ct, dict):
        # raw.실기만점 결손 시 검증 산식의 실기 만점 사용.
        practical_max = _first_number(ct.get("plugin_practical_full_score"))
    if record_only and (practical_max is None or practical_max <= 0):
        # 실기 없는 교과전형 — 내신 환산점수가 곧 총점이다. 실기 0으로 두고
        # record가 작년 교과 합격선에 닿는지 직접 비교한다 (2026-06-17 교과전형 포함).
        practical_max = 0.0
    # 올해 총점 만점 — 작년 합격컷과 만점 스케일이 같은지 판정하는 기준.
    full_total = _first_number(ct.get("plugin_full_practical_total")) if isinstance(ct, dict) else None
    r26 = _json_loads(row["admission_result_26_json"], {}) or {}
    if not isinstance(r26, dict):
        return None
    score_logic = _json_loads(row["score_logic_json"], {}) or {}
    grade_points = score_logic.get("grade_points") if isinstance(score_logic, dict) else None

    def _rescaled_cut(cut: Any) -> tuple[float | None, float | None, float | None]:
        # 작년 합격컷을 올해 산식 스케일로 재환산한다. 작년 점수 만점이 학교마다
        # 제각각(안양대 100점 vs 강원대 1600점)이라 직접 비교가 틀린다(2026-06-15 실사고).
        # 작년 합격자 평균등급을 올해 grade_points로 환산해 내신 재환산점을 얻고,
        # (재환산점 / 작년내신점) 비율(scale)을 작년 총점에 곱해 올해 스케일 총점을 만든다.
        cut = cut if isinstance(cut, dict) else {}
        total_raw = _first_number(cut.get("total_score"))
        record_raw = _first_number(cut.get("record_score"))
        practical_raw = _first_number(cut.get("practical_score"))
        grade = _first_number(cut.get("grade"))
        rec_olscale = None
        if grade is not None and grade_points:
            rec_olscale = _score_from_grade_table(grade, grade_points)
        if total_raw is not None:
            practical_scale_mismatch = (
                practical_raw is not None
                and practical_max is not None
                and practical_max > 0
                and practical_raw > practical_max + 0.01
            )
            if practical_scale_mismatch:
                practical_rescaled = _rescaled_practical_score(university_id, practical_raw, practical_max)
                if practical_rescaled is not None and rec_olscale is not None:
                    return round(rec_olscale + practical_rescaled, 2), rec_olscale, None
            # 비율(만점 스케일) 판정: 작년 총점이 올해 총점 만점과 같은 스케일이면(비율 유사)
            # 재환산하지 않고 작년 총점을 그대로 쓴다 (사장님 룰 2026-06-16: 무조건 재환산 금지).
            # 명백히 다를 때만(안양대 작년 100점 vs 올해 1000점) grade 기반 재환산.
            if full_total and full_total > 0 and 0.5 <= total_raw / full_total <= 1.2:
                return total_raw, rec_olscale, 1.0
            if rec_olscale is not None and record_raw and record_raw > 0:
                scale = rec_olscale / record_raw
                return round(total_raw * scale, 2), rec_olscale, scale
        return total_raw, rec_olscale, None  # 등급/산식 없으면 원본 총점(스케일 일치 학교) 사용

    final_cut, prev_final_rec, prev_scale = _rescaled_cut(r26.get("final_pass_cutoff"))
    first_cut, prev_first_rec, _ = _rescaled_cut(r26.get("first_pass_cutoff"))
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
        "prev_scale": prev_scale,
        "reachable_at_full_practical": reachable,
    }
    # 1단계(배수 선발) 통과 가능성 (사장님 룰 2026-06-16).
    # 1단계 판정 기준은 '배수(multiple)가 명시된 전형'뿐이다 — first_pass_cutoff 데이터 존재만으로
    # 판정하면 일괄전형(인천대 스포츠과학·관동대 등)을 1단계로 오인해 잘못 거른다(실사고).
    # 배수 선발이면 학생 내신환산이 작년 1단계 통과자 내신환산 이상이어야 1단계 통과 가능.
    meta = _json_loads(row["admission_meta_json"], {}) or {}
    stage1_meta = meta.get("stage1") if isinstance(meta.get("stage1"), dict) else {}
    stage1_multiple = _first_number((stage1_meta or {}).get("multiple"))
    stage1_record_weight = _first_number((stage1_meta or {}).get("student_record"))
    info["stage1_uses_record"] = (
        bool(stage1_multiple and stage1_multiple > 0)
        and bool(stage1_record_weight and stage1_record_weight > 0)
        and (prev_first_rec is not None)
    )
    if info["stage1_uses_record"]:
        info["stage1_record_reachable"] = record_score >= prev_first_rec
    if not reachable:
        info["warning"] = (
            f"실기 만점({practical_max:g})을 받아도 합산 {max_total:g}점이 전년도 최종합 "
            f"{final_cut:g}점(올해 산식 환산)에 미달 — 이 학교는 상향으로도 추천 금지."
        )
    return info


def _rescaled_practical_score(
    university_id: str,
    practical_score: float | None,
    current_practical_max: float | None,
) -> float | None:
    if practical_score is None or current_practical_max is None or current_practical_max <= 0:
        return None
    prev_max = _previous_practical_max(university_id)
    if prev_max is None or prev_max <= 0:
        return None
    if abs(prev_max - current_practical_max) < 0.01:
        return practical_score
    return practical_score / prev_max * current_practical_max


def _previous_practical_max(university_id: str) -> float | None:
    key = str(university_id or "").strip()
    if not key or not key.isdigit():
        return None
    if key in _PREV_PRACTICAL_MAX_CACHE:
        return _PREV_PRACTICAL_MAX_CACHE[key]
    try:
        rows = _vultr_mysql(
            f"SELECT 실기만점 FROM `{_PREV_YEAR_DB}`.`대학정보` WHERE 대학ID = '{key}' LIMIT 1",
            timeout=8,
        )
    except Exception:
        _PREV_PRACTICAL_MAX_CACHE[key] = None
        return None
    value = _first_number(rows[0][0]) if rows and rows[0] else None
    _PREV_PRACTICAL_MAX_CACHE[key] = value
    return value


# ---------------------------------------------------------------------------
# 전년도(26susi) 원본 조회 — Vultr DB read-only
# ---------------------------------------------------------------------------
# 추천 크로스체크용: 작년 전형 구조(내신:실기 비중, 실기만점, 정원, 실기 종목)를
# 원본에서 직접 확인한다. 사장님 승인(2026-06-12) — ssh vultr 경유 read-only SELECT.


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
