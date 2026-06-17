"""Nationwide content builder for practical recommendation PDFs."""

from __future__ import annotations

from typing import Any

from .practical_reco_schema import _first_number


_REGION_ORDER = ["수도권", "충청", "강원", "영남", "호남", "제주"]
_TIER_RANK = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "E": 5}


def build_nationwide_content(student_name: str) -> dict[str, Any]:
    """Build nationwide practical recommendation content directly from susi output."""
    from ..susi_ops.service import recommend_candidates

    res = recommend_candidates(student_name, region="전국", max_candidates=400)
    cands = res.get("candidates") or []
    by_region: dict[str, list[dict[str, Any]]] = {r: [] for r in _REGION_ORDER}
    for c in cands:
        reg = _sido_to_region(c.get("region"))
        if reg is not None:
            by_region[reg].append(c)
    regions: list[dict[str, Any]] = []
    tier_cnt: dict[str, int] = {}
    for reg in _REGION_ORDER:
        raw = by_region[reg]
        if not raw:
            continue
        raw.sort(key=lambda c: (_TIER_RANK.get(c.get("tier"), 9), _first_number(c.get("needed_practical_rate_pct")) or 999.0))
        rows: list[dict[str, Any]] = []
        for c in raw:
            tier = c.get("tier") or "C"
            tier_cnt[tier] = tier_cnt.get(tier, 0) + 1
            ev = c.get("practical_events")
            ev_str = ", ".join(str(e) for e in ev) if isinstance(ev, list) else (str(ev) if ev else "-")
            rows.append({
                "tier": tier,
                "school": c.get("university") or "",
                "department": c.get("department") or "",
                "track": c.get("admission_track") or "",
                "events": (ev_str[:38] or "-"),
                "converted": _num_or_dash(c.get("student_record_score")),
                "max_total": _num_or_dash(c.get("max_possible_total")),
                "first_cut": _num_or_dash(c.get("prev_first_total")),
                "final_cut": _num_or_dash(c.get("prev_final_total")),
                "verdict": c.get("suggested_verdict") or "상향",
            })
        regions.append({"name": reg, "rows": rows})
    total = sum(len(r["rows"]) for r in regions)
    tier_counts = [{"tier": t, "count": tier_cnt[t]} for t in ["S", "A", "B", "C", "D", "E"] if tier_cnt.get(t)]
    region_counts = [{"name": r["name"], "count": len(r["rows"])} for r in regions]
    return {
        "student": {
            "name": student_name,
            "avg_grade": "",
            "basis_label": "생기부 내신 기준",
        },
        "summary": {
            "total": total,
            "reachable_note": "실기 만점을 기준으로 전년도 최종합격선에 도달 가능한 전국 실기전형을 권역별로 정리했습니다.",
            "tier_counts": tier_counts,
            "region_counts": region_counts,
        },
        "regions": regions,
        "footnote": "산출 근거: 맥스 수시엔진 검증 룰 · 전년도 입시결과",
    }


def _num_or_dash(value: Any) -> str:
    n = _first_number(value)
    return f"{n:g}" if n is not None else "-"


def _sido_to_region(sido: Any) -> str | None:
    from ..susi_ops.service import _REGION_GROUPS

    s = str(sido or "").strip()
    for region in _REGION_ORDER:
        if s in _REGION_GROUPS.get(region, []):
            return region
    return None
