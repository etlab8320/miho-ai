#!/usr/bin/env python3
"""Audit Susi 2027 formula rows against official guide text evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REFERENCE_ROOT_ENV = "MIHO_SUSI27_REFERENCE_ROOT"
RUNTIME_ENV = "MIHO_SUSI27_RUNTIME"
STAGING_DB_ENV = "MIHO_SUSI27_STAGING_DB"
DEFAULT_OUT_DIR = Path("docs/susi27_pdf_formula_audit")
GENERIC_TRACKS = {"실기", "일반", "교과", "종합", "예체능"}


@dataclass(frozen=True)
class AuditPaths:
    runtime: Path
    db: Path


def main(argv: list[str] | None = None) -> int:
    default_runtime = _default_runtime()
    parser = argparse.ArgumentParser(description="Audit Susi 2027 formula DB rows against official PDF text.")
    parser.add_argument("--db", default=os.environ.get(STAGING_DB_ENV))
    parser.add_argument("--runtime", default=default_runtime)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.runtime:
        parser.error(f"--runtime is required unless {RUNTIME_ENV} or {REFERENCE_ROOT_ENV} is set")
    if not args.db:
        args.db = str(Path(args.runtime).expanduser() / "susi27_staging.sqlite3")

    paths = AuditPaths(runtime=Path(args.runtime).expanduser().resolve(), db=Path(args.db).expanduser().resolve())
    result = run_audit(paths)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "susi27_pdf_formula_audit.json"
    csv_path = out_dir / "susi27_pdf_formula_audit.csv"
    md_path = out_dir / "susi27_pdf_formula_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, result["rows"])
    if not args.json_only:
        md_path.write_text(render_markdown(result, json_path, csv_path), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if result["summary"]["hard_fail_rows"] == 0 else 1


def _default_runtime() -> str | None:
    runtime = os.environ.get(RUNTIME_ENV)
    if runtime:
        return runtime
    reference_root = os.environ.get(REFERENCE_ROOT_ENV)
    if reference_root:
        return str(Path(reference_root).expanduser() / "runtime" / "susi27_pipeline")
    return None


def run_audit(paths: AuditPaths) -> dict[str, Any]:
    rows = list(_load_rows(paths.db))
    audits = [audit_row(row, paths.runtime) for row in rows]
    summary = _summary(audits)
    return {
        "schema_version": "susi27_pdf_formula_audit.v1",
        "runtime": str(paths.runtime),
        "db": str(paths.db),
        "summary": summary,
        "rows": audits,
    }


def audit_row(row: sqlite3.Row, runtime: Path) -> dict[str, Any]:
    score = _json(row["score_logic_json"])
    events = _json(row["practical_events_json"])
    meta = _json(row["admission_meta_json"])
    school = _json(row["school_info_json"])
    pdf_path = _resolve_path(runtime, row["pdf_rel_path"])
    text_path = _resolve_path(runtime, row["text_path"]) or _resolve_path(runtime, school.get("text_path"))
    source_text_path = _resolve_path(runtime, row["source_text_path"])
    text = _read_text(text_path)
    compact = _compact(text)
    hard: list[str] = []
    review: list[str] = []
    passed: list[str] = []

    _check_source(row, pdf_path, text_path, source_text_path, text, hard, review, passed)
    _check_identity(row, compact, review, passed)
    _check_quota(row, compact, review, passed)
    _check_stage_weights(score, meta, text, review, passed)
    _check_stage_scores(score, events, text, review, passed)
    _check_grade_points(score, text, review, passed)
    _check_practical_events(events, compact, review, passed)
    _check_hashes(score, school, pdf_path, text_path, hard, review, passed)

    status = "hard_fail" if hard else ("needs_review" if review else "pass")
    return {
        "university_id": row["university_id"],
        "university": row["university"],
        "department": row["department"],
        "admission_track": row["admission_track"],
        "quota": row["quota"],
        "source_status": row["source_status"],
        "pdf_rel_path": row["pdf_rel_path"],
        "text_path": _display_path(text_path, runtime),
        "status": status,
        "hard_failures": hard,
        "needs_review": review,
        "passed_checks": passed,
        "formula_key": score.get("formula_key") or score.get("official_formula_key") or "",
    }


def _load_rows(db_path: Path) -> list[sqlite3.Row]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    query = """
        select d.*, c.score_logic_json, c.practical_events_json, c.admission_meta_json,
               c.school_info_json, c.source_text_path
          from db_university_rows d
          left join susi_calculation_rules c using(university_id)
         order by cast(d.university_id as integer)
    """
    try:
        return list(con.execute(query))
    finally:
        con.close()


def _check_source(
    row: sqlite3.Row,
    pdf_path: Path | None,
    text_path: Path | None,
    source_text_path: Path | None,
    text: str,
    hard: list[str],
    review: list[str],
    passed: list[str],
) -> None:
    pdf_rel = str(row["pdf_rel_path"] or "")
    text_ref = str(row["text_path"] or "")
    source_ref = str(row["source_text_path"] or "")
    if "시행계획" in pdf_rel or "시행계획" in text_ref or "시행계획" in source_ref:
        hard.append("source references 대학입학전형시행계획")
    if pdf_path is None or not pdf_path.exists():
        hard.append("official PDF path missing")
    elif "수시모집요강" in pdf_rel and "시행계획" not in pdf_rel:
        passed.append("pdf_path_is_susi_guide")
    else:
        review.append("PDF path is not explicitly 수시모집요강")
    if text_path is None or not text_path.exists():
        hard.append("official text path missing")
    elif "수시모집" in text and "모집요강" in text:
        passed.append("text_content_is_susi_guide")
    else:
        review.append("text content does not clearly contain 수시모집요강")
    if source_text_path and "수시모집요강" in str(source_text_path):
        passed.append("source_text_path_is_susi_guide")


def _check_identity(row: sqlite3.Row, compact: str, review: list[str], passed: list[str]) -> None:
    if _contains(compact, row["university"]):
        passed.append("university_found")
    else:
        review.append("university name not found in source text")
    if _contains(compact, row["department"]):
        passed.append("department_found")
    else:
        review.append("department name not found in source text")
    track = str(row["admission_track"] or "").strip()
    if len(track) >= 2 and track not in GENERIC_TRACKS:
        if _contains(compact, track):
            passed.append("admission_track_found")
        else:
            review.append("admission track not directly found in source text")


def _check_quota(row: sqlite3.Row, compact: str, review: list[str], passed: list[str]) -> None:
    quota = str(row["quota"] or "").strip()
    if not quota or quota == "0":
        return
    if _near(compact, row["department"], quota, 250):
        passed.append("quota_number_found_near_department")
    else:
        review.append("quota number not found near department in source text")


def _check_stage_weights(
    score: dict[str, Any],
    meta: dict[str, Any],
    source_text: str,
    review: list[str],
    passed: list[str],
) -> None:
    values = _collect_numbers(score.get("stage_weights")) + _collect_numbers(meta.get("stage2"))
    values = _nonzero_unique(values)
    if not values:
        return
    hits = [value for value in values if _number_found(source_text, value)]
    if len(hits) == len(values):
        passed.append(f"stage_weights_found:{len(hits)}/{len(values)}")
    else:
        review.append(f"stage weights not exact:{len(hits)}/{len(values)}")


def _check_stage_scores(
    score: dict[str, Any],
    events: dict[str, Any],
    source_text: str,
    review: list[str],
    passed: list[str],
) -> None:
    values = _collect_numbers(score.get("stage_scores"))
    for key in ("record_full_score", "practical_full_score"):
        if key in score:
            values.extend(_collect_numbers(score.get(key)))
    values.extend(_collect_numbers(events.get("practical_full_score")))
    values = _nonzero_unique(values)
    if not values:
        return
    hits = [value for value in values if _number_found(source_text, value)]
    if len(hits) == len(values):
        passed.append(f"stage_scores_found:{len(hits)}/{len(values)}")
    else:
        review.append(f"stage/full scores not exact:{len(hits)}/{len(values)}")


def _check_grade_points(score: dict[str, Any], source_text: str, review: list[str], passed: list[str]) -> None:
    grade_points = score.get("grade_points")
    if not isinstance(grade_points, dict) or not grade_points:
        if score.get("calculation_readiness") == "ready_for_sample_calculation":
            review.append("ready formula has no grade_points table")
        return
    values = _nonzero_unique(_collect_numbers(grade_points))
    hits = [value for value in values if _number_found(source_text, value)]
    ratio = len(hits) / max(1, len(values))
    if ratio >= 1:
        passed.append(f"grade_points_found:{len(hits)}/{len(values)}")
    elif hits:
        review.append(f"grade point table not exact:{len(hits)}/{len(values)}")
    else:
        review.append("grade point table values not found in source text")


def _check_practical_events(events: dict[str, Any], compact: str, review: list[str], passed: list[str]) -> None:
    event_names = [
        str(event.get("name") or "").strip()
        for event in events.get("events") or []
        if isinstance(event, dict) and str(event.get("name") or "").strip()
    ]
    if not event_names:
        if events.get("no_practical") is False:
            review.append("practical_applicable row has no practical event names")
        return
    hits = [name for name in event_names if _contains(compact, name)]
    if len(hits) == len(event_names):
        passed.append(f"practical_events_found:{len(hits)}/{len(event_names)}")
    elif hits:
        review.append(f"practical events partial evidence:{len(hits)}/{len(event_names)}")
    else:
        review.append("practical event names not found in source text")


def _check_hashes(
    score: dict[str, Any],
    school: dict[str, Any],
    pdf_path: Path | None,
    text_path: Path | None,
    hard: list[str],
    review: list[str],
    passed: list[str],
) -> None:
    for label, path, expected in (
        ("official_pdf_sha256", pdf_path, score.get("official_pdf_sha256") or school.get("official_pdf_sha256")),
        ("official_text_sha256", text_path, score.get("official_text_sha256") or school.get("official_text_sha256")),
    ):
        if not expected:
            review.append(f"{label} missing")
            continue
        if path is None or not path.exists():
            hard.append(f"{label} present but file missing")
            continue
        actual = _sha256(path)
        if actual == expected:
            passed.append(f"{label}_matches")
        else:
            hard.append(f"{label} mismatch")


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(row["status"] for row in rows)
    issue_counts = Counter(issue for row in rows for issue in row["needs_review"] + row["hard_failures"])
    return {
        "total_rows": len(rows),
        "pass_rows": status_counts["pass"],
        "needs_review_rows": status_counts["needs_review"],
        "hard_fail_rows": status_counts["hard_fail"],
        "final_100_confirmed_rows": 0,
        "pixel_ocr_required_rows": len(rows),
        "distinct_universities": len({row["university"] for row in rows}),
        "top_issues": issue_counts.most_common(20),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["university_id", "university", "department", "admission_track", "quota", "status", "needs_review", "hard_failures"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json.dumps(row[field], ensure_ascii=False) if isinstance(row[field], list) else row[field] for field in fields})


def render_markdown(result: dict[str, Any], json_path: Path, csv_path: Path) -> str:
    summary = result["summary"]
    lines = [
        "# 2027 수시 체대 PDF 산식 재감사",
        "",
        "## 요약",
        f"- 전체 row: {summary['total_rows']}",
        f"- 텍스트/해시 기준 1차 PASS: {summary['pass_rows']}",
        f"- 재검토 필요: {summary['needs_review_rows']}",
        f"- 하드 실패: {summary['hard_fail_rows']}",
        f"- 최종 100% 확정: {summary['final_100_confirmed_rows']}",
        f"- 픽셀 OCR 재판독 필요: {summary['pixel_ocr_required_rows']}",
        f"- 대학 수: {summary['distinct_universities']}",
        f"- JSON: `{json_path}`",
        f"- CSV: `{csv_path}`",
        "",
        "## 상위 재검토 사유",
    ]
    for issue, count in summary["top_issues"]:
        lines.append(f"- {count}: {issue}")
    lines.extend(["", "## 하드 실패 row"])
    hard_rows = [row for row in result["rows"] if row["status"] == "hard_fail"]
    if not hard_rows:
        lines.append("- 없음")
    else:
        for row in hard_rows[:50]:
            lines.append(f"- {row['university_id']} {row['university']} {row['department']} {row['hard_failures']}")
    lines.extend(["", "## 재검토 필요 샘플"])
    for row in [item for item in result["rows"] if item["status"] == "needs_review"][:80]:
        lines.append(
            f"- {row['university_id']} {row['university']} / {row['department']} / {row['admission_track']}: "
            f"{'; '.join(row['needs_review'][:4])}"
        )
    lines.append("")
    lines.append("> 판정 기준: PASS는 PDF 텍스트/해시/DB 필드가 자동 대조를 통과한 1차 판정이다. 최종 100% 확정은 렌더 페이지 이미지에 대한 픽셀 OCR 재판독까지 같은 값으로 일치한 row에만 부여한다.")
    lines.append("> 재검토 필요는 불일치 확정이 아니라 OCR/표 구조/환산식 때문에 픽셀 OCR 또는 수동 페이지 판독이 필요한 항목이다.")
    return "\n".join(lines) + "\n"


def _resolve_path(runtime: Path, value: Any) -> Path | None:
    if not value:
        return None
    text = str(value)
    path = Path(text).expanduser()
    if "susi27_pipeline/" in text:
        candidate = runtime / text.split("susi27_pipeline/", 1)[1]
        if candidate.exists():
            return candidate
    candidates = [runtime / text, runtime / "texts" / Path(text).name]
    found = next((candidate for candidate in candidates if candidate.exists()), None)
    if found:
        return found
    if path.exists() and str(path).startswith(str(runtime)):
        return path
    return None


def _read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _json(value: Any) -> dict[str, Any]:
    try:
        loaded = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _contains(compact_text: str, token: Any) -> bool:
    compact_token = _compact(token)
    return bool(compact_token and compact_token in compact_text)


def _near(compact_text: str, left: Any, right: Any, distance: int) -> bool:
    left_token = _compact(left)
    right_token = _compact(right)
    if not left_token or not right_token:
        return False
    start = compact_text.find(left_token)
    while start >= 0:
        window = compact_text[start : start + len(left_token) + distance]
        if right_token in window:
            return True
        start = compact_text.find(left_token, start + 1)
    return False


def _collect_numbers(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        numbers: list[str] = []
        for item in value.values():
            numbers.extend(_collect_numbers(item))
        return numbers
    if isinstance(value, list):
        numbers = []
        for item in value:
            numbers.extend(_collect_numbers(item))
        return numbers
    return re.findall(r"\d+(?:\.\d+)?", str(value))


def _nonzero_unique(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        norm = _normalize_number(value)
        if not norm or norm == "0" or norm in seen:
            continue
        seen.add(norm)
        normalized.append(norm)
    return normalized


def _normalize_number(value: Any) -> str:
    text = str(value).strip().replace(",", "")
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return (f"{number:.4f}").rstrip("0").rstrip(".")


def _number_found(compact_text: str, value: Any) -> bool:
    normalized = _normalize_number(value)
    if not normalized:
        return False
    candidates = {normalized, normalized + ".0"}
    if "." not in normalized:
        candidates.add(f"{normalized}.0")
    return any(_number_pattern(candidate).search(compact_text) for candidate in candidates)


def _number_pattern(value: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\d.]){re.escape(_compact(value))}(?![\d.])")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path | None, runtime: Path) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(runtime))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
