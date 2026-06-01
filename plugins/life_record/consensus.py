"""Self-consistency reconciliation across multiple vision extractions.

A field/row is ``confirmed`` only when independent runs agree (majority). What
disagrees stays ``needs_review`` for a human. Bounded by ``max_rounds`` — never an
unbounded loop. PoC showed a single vision pass mis-reads ~1 char (주민번호 / 학교명);
agreement across runs is what removes that risk.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

CONFIRMED = "confirmed"
NEEDS_REVIEW = "needs_review"

IDENTITY_FIELDS = ("name", "school_name", "birth6", "class_no", "student_no")
ROW_KEYS = {
    "attendance": ("grade",),
    "grades": ("grade", "semester", "subject"),
    "notes": ("grade", "semester", "subject"),
    "awards": ("title", "awarded_at"),
}


def _norm_scalar(value: Any) -> str:
    """Whitespace / width / case / Roman-numeral-insensitive scalar key so trivial
    OCR formatting differences don't block agreement:
    '83/75.0 (18.1)' vs '83/75.0(18.1)', and '물리학Ⅰ' vs '물리학 I'
    (NFKC folds the Unicode Roman numeral Ⅰ→I, Ⅱ→II, and full-width→ASCII)."""
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    return re.sub(r"\s+", "", normalized).lower()


def _norm_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _norm_obj(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, list):
        return [_norm_obj(x) for x in obj]
    return _norm_scalar(obj)


def _key(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(_norm_obj(value), ensure_ascii=False, sort_keys=True)
    return _norm_scalar(value)


def _majority_threshold(n: int) -> int:
    return 1 if n <= 1 else (n // 2) + 1


def _vote(values: list[str], n: int) -> dict[str, Any]:
    clean = [v for v in values if v and v.lower() != "none"]
    if not clean:
        return {"value": None, "agreed": False, "status": NEEDS_REVIEW, "confidence": 0.0}
    counts: dict[str, int] = {}
    for v in clean:
        counts[v] = counts.get(v, 0) + 1
    best, cnt = max(counts.items(), key=lambda kv: kv[1])
    agreed = cnt >= _majority_threshold(n)
    return {
        "value": best,
        "agreed": agreed,
        "status": CONFIRMED if agreed else NEEDS_REVIEW,
        "confidence": round(cnt / max(1, n), 2),
    }


def reconcile_identity(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    n = len(results)
    out: dict[str, dict[str, Any]] = {}
    for field in IDENTITY_FIELDS:
        values = [_key((r.get("identity") or {}).get(field)) for r in results]
        out[field] = _vote(values, n)
    return out


def reconcile_rows(results: list[dict[str, Any]], section: str) -> list[dict[str, Any]]:
    """Reconcile list sections by row key. A row is confirmed only when a majority
    of runs produced an identical full row."""
    n = len(results)
    key_fields = ROW_KEYS[section]
    buckets: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        for row in result.get(section) or []:
            if not isinstance(row, dict):
                continue
            row_key = "|".join(_key(row.get(kf)) for kf in key_fields)
            buckets.setdefault(row_key, []).append(row)
    out: list[dict[str, Any]] = []
    for rows in buckets.values():
        seen = len(rows)
        identical = len({_key(r) for r in rows}) == 1
        agreed = seen >= _majority_threshold(n) and identical
        merged = dict(rows[0])
        merged["_status"] = CONFIRMED if agreed else NEEDS_REVIEW
        merged["_confidence"] = round(seen / max(1, n), 2)
        out.append(merged)
    return out


def reconcile(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Full reconciliation of N extraction results into one consensus structure."""
    return {
        "identity": reconcile_identity(results),
        "attendance": reconcile_rows(results, "attendance"),
        "grades": reconcile_rows(results, "grades"),
        "notes": reconcile_rows(results, "notes"),
        "awards": reconcile_rows(results, "awards"),
    }


def needs_recheck_fields(reconciled_identity: dict[str, dict[str, Any]]) -> list[str]:
    return [field for field, info in reconciled_identity.items() if not info.get("agreed")]


def all_confirmed(consensus: dict[str, Any]) -> bool:
    """True only when every identity field and every row reached agreement."""
    identity = consensus.get("identity") or {}
    if any(not info.get("agreed") for info in identity.values() if info.get("value") is not None):
        return False
    for section in ("attendance", "grades", "notes", "awards"):
        for row in consensus.get(section) or []:
            if row.get("_status") != CONFIRMED:
                return False
    return True
