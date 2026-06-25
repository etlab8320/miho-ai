"""Single-call 수시 recommendation pipeline."""

from __future__ import annotations

import json
import os
import pathlib
import re as _re
from typing import Any

from . import student_records as _student_records
from .calculation import calculate_score
from .db import _connect, _json_loads
from .formula_adapter import _formula_calculate
from .prev_year import _safe_like_term, _vs_prev_year, _vultr_mysql
from .recommendation_events import recommendation_event_info
from .recommendation_verdict import practical_verdict
from .targeting import (
    _is_blocked_official_row,
    _is_allowed_recommendation_target,
    _is_restricted_record_only_track,
    _is_specific_sport_practical_row,
)
from .utils import _first_number


_CENTRAL_LIFE_DB = _student_records.CENTRAL_LIFE_DB
_REGION_MAP_PATH = pathlib.Path(os.path.expanduser("~/.miho/academy_ops/susi_region_map.json"))
_REGION_MAP: dict[str, str] | None = None
MAX_RECOMMEND_CANDIDATES = 400


def _student_grades_from_central(student_query: str) -> tuple[str | None, list[dict[str, Any]]]:
    original_db = _student_records.CENTRAL_LIFE_DB
    _student_records.CENTRAL_LIFE_DB = _CENTRAL_LIFE_DB
    try:
        return _student_records.student_grades_from_central(student_query)
    finally:
        _student_records.CENTRAL_LIFE_DB = original_db


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


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


# 학교 평가 티어 (실기전형 입결 서열 + 지역·명성 종합) — 추천 정렬 1순위.
# 캡틴이 직접 평가해 채운다(susi_school_tier.json). 미평가 학교는 기본 'C'.
_SCHOOL_TIER_PATH = pathlib.Path(os.path.expanduser("~/.miho/academy_ops/susi_school_tier.json"))
_SCHOOL_TIER: dict[str, str] | None = None
_TIER_RANK = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "E": 5}

# 학과 단위 티어 규칙 (사장님 기준 2026-06-15):
#  서울 소재 = S · 가천대/동국대 = S · (비서울)체육교육과 = A · 경기권/거점국립·명문 = B · 지방 사립 = C~E.
#  개별 보정은 susi_school_tier.json (university 또는 'university::학과' 키)이 규칙보다 우선.
_S_TIER_SCHOOLS = {"가천대학교", "동국대학교"}
_B_TIER_SCHOOLS = {
    "단국대학교", "상명대학교", "울산대학교",
    "부산대학교", "경북대학교", "전남대학교", "충북대학교", "경상국립대학교",
    "부경대학교", "한국해양대학교", "강원대학교", "공주대학교", "제주대학교",
    "한국교통대학교", "영남대학교", "조선대학교", "동아대학교", "원광대학교",
}
_D_TIER_SCHOOLS = {
    "가톨릭관동대학교", "상지대학교", "백석대학교",
    "경운대학교", "인제대학교", "창원대학교", "경남대학교", "신라대학교",
    "동서대학교", "동명대학교",
}
_E_TIER_SCHOOLS = {"경국대학교", "부산외국어대학교", "영산대학교", "극동대학교"}
_DGU_WISE_ROW_IDS = {"147", "148", "149", "151", "152", "153", "154", "156"}
_KONKUK_GLOCAL_ROW_IDS = {"9", "10"}


def _school_tier_map() -> dict[str, str]:
    global _SCHOOL_TIER
    if _SCHOOL_TIER is not None:
        return _SCHOOL_TIER
    data = _json_loads(
        _SCHOOL_TIER_PATH.read_text(encoding="utf-8") if _SCHOOL_TIER_PATH.exists() else None, None
    )
    _SCHOOL_TIER = data if isinstance(data, dict) else {}
    return _SCHOOL_TIER


def _school_tier(university: str, department: str = "", region: str = "") -> str:
    u = str(university or "").strip()
    d = str(department or "").strip()
    r = str(region or "").strip()
    tmap = _school_tier_map()
    # 1) 개별 예외 (학과 키 우선, 그다음 학교 키) — 규칙보다 우선
    for key in (f"{u}::{d}", u):
        t = tmap.get(key)
        if t in _TIER_RANK:
            return t
    # 2) 규칙
    if r == "서울":
        return "S"
    if u in _S_TIER_SCHOOLS:
        return "S"
    if "특수체육교육" in d:  # 특수체육교육과는 B (사장님 2026-06-15)
        return "B"
    if "체육교육" in d:
        return "A"
    if r == "경기" or u in _B_TIER_SCHOOLS:
        return "B"
    if u in _E_TIER_SCHOOLS:
        return "E"
    if u in _D_TIER_SCHOOLS:
        return "D"
    return "C"


def _display_university_name(row: Any) -> str:
    university = str(_row_get(row, "university", "") or "")
    uid = str(_row_get(row, "university_id", "") or "")
    text = " ".join(
        str(_row_get(row, key, "") or "")
        for key in ("score_logic_json", "raw_json")
    )
    if university == "동국대학교" and (uid in _DGU_WISE_ROW_IDS or "DGU_WISE" in text or "WISE" in text):
        return "동국대학교 WISE"
    if university == "건국대학교" and (uid in _KONKUK_GLOCAL_ROW_IDS or "글로컬" in text):
        return "건국대학교(글로컬)"
    return university


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
    track_key = _re.sub(r"[\s,·/_-]+", "", str(admission_track or ""))
    generic_track_key = track_key
    for word in ("전국", "전체", "수시", "실기", "전형", "추천", "후보"):
        generic_track_key = generic_track_key.replace(word, "")
    practical_only_requested = "실기" in track_key and not generic_track_key
    sql_admission_track = None if practical_only_requested else admission_track

    conn = _connect()
    conds = ["c.confidence LIKE '%verified%'", "c.admission_result_26_json IS NOT NULL", "c.admission_result_26_json != ''"]
    params: list[Any] = []
    for term, col in ((university, "c.university"), (department, "c.department"), (sql_admission_track, "c.admission_track")):
        clean = _safe_like_term(term)
        if clean:
            conds.append(f"{col} LIKE ?")
            params.append(f"%{clean}%")
    rule_rows = conn.execute(
        f"SELECT c.university_id, c.university, c.department, c.admission_track, "
        f"c.confidence, c.score_logic_json, c.practical_events_json, c.calculation_test_json, d.raw_json "
        f"FROM susi_calculation_rules c "
        f"LEFT JOIN db_university_rows d ON d.university_id = c.university_id "
        f"WHERE {' AND '.join(conds)}",
        params,
    ).fetchall()

    candidates = []
    skipped = {"calc_failed": 0, "unreachable": 0, "stage1_blocked": 0, "non_practical": 0}
    for row in rule_rows:
        if _is_blocked_official_row(_row_get(row, "confidence", ""), _row_get(row, "score_logic_json", "{}")):
            skipped["not_in_guide"] = skipped.get("not_in_guide", 0) + 1
            continue
        _trk = str(row["admission_track"] or "")
        if not _is_allowed_recommendation_target(row["department"], _trk, admission_track):
            skipped["condition_limited"] = skipped.get("condition_limited", 0) + 1
            continue
        if _is_specific_sport_practical_row(row["practical_events_json"]):
            skipped["specific_sport"] = skipped.get("specific_sport", 0) + 1
            continue
        # 실기전형만 추천 대상 — 같은 학과의 비실기 전형(교과100/농어촌·종합 서류, 실기만점 0)을
        # 후보에서 제외한다. 실기 미반영 전형은 작년 결과·실기만점이 없어 빈칸을 만든다.
        ct = _json_loads(row["calculation_test_json"], {}) or {}
        practical_full = _first_number(ct.get("plugin_practical_full_score")) if isinstance(ct, dict) else None
        if practical_full is None:
            practical_full = _first_number(_json_loads(row["raw_json"], {}).get("실기만점"))
        record_only_track = False
        if not practical_full or practical_full <= 0:
            # 실기만점 데이터가 없어도 실기종목이 등록돼 있으면 실기전형으로 인정 (누락 방지).
            _ev = _json_loads(row["practical_events_json"], None)
            _events = _ev.get("events") if isinstance(_ev, dict) else _ev
            if not _events:
                if practical_only_requested:
                    skipped["non_practical"] += 1
                    continue
                # 실기 없는 교과전형 — record만으로 작년 교과 합격선 대비해 후보에 포함한다
                # (사장님 2026-06-17). 단 자격 제한 전형(농어촌·기회균형 등)은 일반 학생
                # 대상이 아니므로 지역인재·특기자처럼 제외한다.
                if _is_restricted_record_only_track(_trk):
                    skipped["non_practical"] += 1
                    continue
                record_only_track = True
        calc = calculate_score(row["university_id"], grades, {}, {})
        if calc.get("status") != "calculated":
            raw_for_formula = _json_loads(row["raw_json"], {})
            # 일부 사이드카 plugin(청주대 등)은 admission_track으로 산식 트랙(예체능 300/700,
            # 교과면접 700/300, 지역인재 1000 등)을 가른다. raw_json엔 한글 '전형명'만 있고
            # admission_track 키가 없으므로 룰 컬럼값을 영어 키로 주입한다.
            raw_for_formula["admission_track"] = row["admission_track"]
            raw_for_formula["department"] = row["department"]
            formula = _formula_calculate(row["university"], dict(raw_for_formula), grades, {})
            if formula is None or formula.get("status") != "ready" or formula.get("record_score") is None:
                skipped["calc_failed"] += 1
                continue
            conn_calc = _connect()
            calc = {
                "status": "calculated",
                "student_record_score": round(float(formula["record_score"]), 4),
                "average_grade": formula.get("reflected_average_grade"),
                "formula_key": formula.get("formula_key"),
            }
            vs_f = _vs_prev_year(conn_calc, row["university_id"], float(formula["record_score"]), record_only=record_only_track)
            if vs_f:
                calc["vs_prev_year"] = vs_f
        vs = calc.get("vs_prev_year") or {}
        if not vs and record_only_track:
            # 교과전형은 calculate_score 내부 _vs_prev_year가 실기 가정으로 None을 반환하므로
            # record_only 모드로 작년 교과 합격선 대비를 다시 구한다.
            vs = _vs_prev_year(conn, row["university_id"], _first_number(calc.get("student_record_score")) or 0.0, record_only=True) or {}
        if not vs:
            skipped["calc_failed"] += 1
            continue
        # 트랙별 컷이 있으면 기본 판단 트랙(완전 측정) 컷으로 교체 — 혼합 컷 왜곡 방지
        default_track, all_tracks = _track_cuts(row["university_id"])
        track_note = None
        if default_track and (default_track.get("final_cut_total") or default_track.get("first_cut_total")):
            # _track_cuts의 컷도 작년 raw 스케일이므로 _vs_prev_year가 구한 prev_scale로
            # 올해 산식 스케일에 맞춘다 (안 그러면 안양대 등에서 스케일 불일치로 오판).
            t_scale = vs.get("prev_scale") or 1.0
            t_final = (default_track.get("final_cut_total") or default_track.get("first_cut_total")) * t_scale
            vs = dict(vs)
            vs["prev_final_total"] = round(float(t_final), 2)
            if default_track.get("first_cut_total"):
                vs["prev_first_total"] = round(float(default_track["first_cut_total"]) * t_scale, 2)
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
        event_info = recommendation_event_info(ev)
        record = calc["student_record_score"]
        # 적정/상향 제안: 작년 최종합격자의 내신환산보다 높으면 적정 출발선
        prev_final_record = None
        prev_winner_practical = None
        prev_winner_grade = None
        stage1 = {}
        # 수능최저학력기준 — 실기/내신이 충분해도 수능최저를 못 맞추면 불합격이므로
        # 반드시 후보에 노출한다(2026-06-17 서원대 체교 실사고: 수능최저 미표시로 도달 오판).
        min_csat_info = None
        try:
            extra = conn.execute(
                "SELECT admission_result_26_json, admission_meta_json FROM susi_calculation_rules WHERE university_id = ?",
                (row["university_id"],),
            ).fetchone()
            _meta = _json_loads(extra[1], {}) or {}
            _mc = _meta.get("minimum_csat") or {}
            if isinstance(_mc, dict):
                _has = _mc.get("has_minimum")
                _has_minimum = _has is True or str(_has or "").strip().upper() in {"O", "Y", "YES", "TRUE", "1", "있음", "적용"}
                if _has_minimum:
                    min_csat_info = _mc.get("detail") or "있음(세부기준 요강 확인)"
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
        suggested = practical_verdict(
            needed_practical_rate,
            margin_at_full_practical=margin,
            practical_max=practical_max_n,
        )
        cand_region = _region_map().get(str(row["university_id"]), "")
        if wanted_regions and cand_region not in wanted_regions:
            skipped["region_filtered"] = skipped.get("region_filtered", 0) + 1
            continue
        display_university = _display_university_name(row)
        candidates.append(
            {
                "university_id": row["university_id"],
                "region": cand_region,
                "tier": _school_tier(display_university, row["department"], cand_region),
                "university": display_university,
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
                "record_only_track": record_only_track or None,
                "minimum_csat": min_csat_info,
                "practical_events": event_info["display_events"],
                "practical_event_note": event_info["event_note"],
                "quota": raw.get("정원"),
                "stage_record_practical": f"{raw.get('내신교과') or '?'}:{raw.get('실기만점') or '?'}",
            }
        )

    # 정렬: 학교 평가 티어(S>A>B>C>D) 1순위 — 도달 가능한 학교 중 평가 좋은 순.
    # 동일 티어 안에서는 필요 실기 득점률이 낮은(현실적으로 쉬운) 순, 그다음 여유점수.
    candidates.sort(
        key=lambda c: (
            _TIER_RANK.get(c.get("tier", "C"), 3),
            c["needed_practical_rate_pct"] if c["needed_practical_rate_pct"] is not None else 999.0,
            -c["margin_at_full_practical"],
        )
    )
    # 같은 대학·학과·전형이 여러 university_id로 중복되면 정렬상 최선 1개만 남긴다.
    _seen: set = set()
    _deduped = []
    for c in candidates:
        k = (c["university"], c["department"], c.get("admission_track"))
        if k in _seen:
            continue
        _seen.add(k)
        _deduped.append(c)
    candidates = _deduped
    max_candidates = max(1, min(int(max_candidates or 30), MAX_RECOMMEND_CANDIDATES))
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
