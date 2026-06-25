#!/usr/bin/env python3
"""Pixel-OCR audit of Susi 2027 formula rows against rendered PDF pages."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from audit_susi27_pdf_formulas import (
    AuditPaths,
    _collect_numbers,
    _compact,
    _default_runtime,
    _json,
    _load_rows,
    _nonzero_unique,
    _number_found,
    _resolve_path,
    _sha256,
)
from miho_constants import get_miho_home
from plugins.pixel_documents.ocr import ocr_pages


DEFAULT_OUT_DIR = Path("docs/susi27_pixel_formula_audit")
DEFAULT_MAX_PAGES_PER_ROW = 8


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit formula rows with Apple Vision OCR over rendered PDF pages.")
    parser.add_argument("--runtime", default=_default_runtime())
    parser.add_argument("--db", default=os.environ.get("MIHO_SUSI27_STAGING_DB"))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--ocr-backend", default="apple_vision")
    parser.add_argument("--max-pages-per-row", type=int, default=DEFAULT_MAX_PAGES_PER_ROW)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--university-id", action="append", default=[])
    parser.add_argument("--refresh-cache", action="store_true")
    args = parser.parse_args(argv)
    if not args.runtime:
        parser.error("--runtime is required unless MIHO_SUSI27_RUNTIME or MIHO_SUSI27_REFERENCE_ROOT is set")
    runtime = Path(args.runtime).expanduser().resolve()
    db = Path(args.db).expanduser().resolve() if args.db else runtime / "susi27_staging.sqlite3"
    rows = _select_rows(_load_rows(db), args.university_id, args.limit)
    result = run_pixel_audit(
        AuditPaths(runtime=runtime, db=db),
        rows=rows,
        ocr_backend=args.ocr_backend,
        max_pages_per_row=max(1, args.max_pages_per_row),
        refresh_cache=args.refresh_cache,
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "susi27_pixel_formula_audit.json"
    csv_path = out_dir / "susi27_pixel_formula_audit.csv"
    md_path = out_dir / "susi27_pixel_formula_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, result["rows"])
    md_path.write_text(render_markdown(result, json_path, csv_path), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if result["summary"]["hard_fail_rows"] == 0 else 1


def run_pixel_audit(
    paths: AuditPaths,
    *,
    rows: list[Any] | None = None,
    ocr_backend: str = "apple_vision",
    max_pages_per_row: int = DEFAULT_MAX_PAGES_PER_ROW,
    refresh_cache: bool = False,
) -> dict[str, Any]:
    manifest = _manifest_hashes(paths.runtime)
    source_cache: dict[str, dict[int, str]] = {}
    audits = [
        audit_row(row, paths.runtime, manifest, source_cache, ocr_backend, max_pages_per_row, refresh_cache)
        for row in (rows if rows is not None else _load_rows(paths.db))
    ]
    return {
        "schema_version": "susi27_pixel_formula_audit.v1",
        "runtime": str(paths.runtime),
        "db": str(paths.db),
        "summary": _summary(audits),
        "rows": audits,
    }


def audit_row(
    row: Any,
    runtime: Path,
    manifest: dict[str, str],
    source_cache: dict[str, dict[int, str]],
    ocr_backend: str,
    max_pages: int,
    refresh_cache: bool,
) -> dict[str, Any]:
    score, events, meta = _json(row["score_logic_json"]), _json(row["practical_events_json"]), _json(row["admission_meta_json"])
    school = _json(row["school_info_json"])
    pdf_path = _resolve_path(runtime, row["pdf_rel_path"])
    expectations = _expectations(row, score, events, meta)
    hard, review, passed = _source_checks(row, score, school, pdf_path, manifest)
    page_numbers: list[int] = []
    ocr_text = ""
    if not hard and pdf_path:
        pages = source_cache.setdefault(str(pdf_path), _pdf_text_pages(pdf_path))
        page_numbers = _candidate_pages(row, expectations, pages, max_pages)
        if not page_numbers:
            ocr_page_numbers = _bounded_page_numbers(pages.keys(), max_pages)
            ocr_pages_text = source_cache.setdefault(
                f"{pdf_path}#pixel:{ocr_backend}:max{max_pages}",
                _ocr_document_text_pages(pdf_path, ocr_page_numbers, ocr_backend, refresh_cache),
            )
            page_numbers = _candidate_pages(row, expectations, ocr_pages_text, max_pages)
            ocr_text = "\n".join(ocr_pages_text[number] for number in page_numbers)
        else:
            ocr_text = "\n".join(_ocr_page(pdf_path, number, ocr_backend, refresh_cache) for number in page_numbers)
        _compare(expectations, ocr_text, passed, review)
    status = "hard_fail" if hard else ("pixel_pass" if not review else "pixel_needs_review")
    return {
        "university_id": row["university_id"],
        "university": row["university"],
        "department": row["department"],
        "admission_track": row["admission_track"],
        "quota": row["quota"],
        "status": status,
        "pdf_rel_path": row["pdf_rel_path"],
        "candidate_pages": page_numbers,
        "expectation_count": sum(len(item["values"]) for item in expectations),
        "passed_checks": passed,
        "needs_review": review,
        "hard_failures": hard,
    }


def _expectations(row: Any, score: dict[str, Any], events: dict[str, Any], meta: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [
        {"key": "department", "mode": "text", "values": [str(row["department"] or "")]},
    ]
    track = str(row["admission_track"] or "").strip()
    if len(track) >= 2 and track not in {"실기", "일반", "교과", "종합", "예체능"}:
        checks.append({"key": "admission_track", "mode": "text", "values": [track]})
    quota = str(row["quota"] or "").strip()
    if quota and quota != "0":
        checks.append({"key": "quota_near_department", "mode": "near", "values": [str(row["department"] or ""), quota]})
    stage_weights = _nonzero_unique(_collect_numbers(score.get("stage_weights")) + _collect_numbers(meta.get("stage2")))
    if stage_weights:
        checks.append({"key": "stage_weights", "mode": "numbers", "values": stage_weights})
    stage_scores = _stage_scores(score, events)
    if stage_scores:
        checks.append({"key": "stage_scores", "mode": "numbers", "values": stage_scores})
    grade_points = _nonzero_unique(_collect_numbers(score.get("grade_points")))
    if grade_points:
        checks.append({"key": "grade_points", "mode": "numbers", "values": grade_points})
    event_names = [str(item.get("name") or "").strip() for item in events.get("events") or [] if isinstance(item, dict)]
    event_names = [name for name in event_names if name]
    if event_names:
        checks.append({"key": "practical_events", "mode": "text", "values": event_names})
    return checks


def _stage_scores(score: dict[str, Any], events: dict[str, Any]) -> list[str]:
    values = _collect_numbers(score.get("stage_scores"))
    for key in ("record_full_score", "practical_full_score"):
        if key in score:
            values.extend(_collect_numbers(score.get(key)))
    values.extend(_collect_numbers(events.get("practical_full_score")))
    return _nonzero_unique(values)


def _source_checks(row: Any, score: dict[str, Any], school: dict[str, Any], pdf_path: Path | None, manifest: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    hard: list[str] = []
    review: list[str] = []
    passed: list[str] = []
    pdf_rel = str(row["pdf_rel_path"] or "")
    if "시행계획" in pdf_rel or "수시모집요강" not in pdf_rel:
        hard.append("source PDF is not 수시모집요강")
    if pdf_path is None or not pdf_path.exists():
        hard.append("official PDF path missing")
        return hard, review, passed
    expected_hash = score.get("official_pdf_sha256") or school.get("official_pdf_sha256") or manifest.get(_manifest_key(pdf_rel))
    if not expected_hash:
        review.append("official_pdf_sha256 missing")
    elif _sha256(pdf_path) == expected_hash:
        passed.append("official_pdf_sha256_matches")
    else:
        hard.append("official_pdf_sha256 mismatch")
    return hard, review, passed


def _pdf_text_pages(path: Path) -> dict[int, str]:
    import fitz

    with fitz.open(str(path)) as doc:
        return {index + 1: doc.load_page(index).get_text("text") or "" for index in range(len(doc))}


def _candidate_pages(row: Any, expectations: list[dict[str, Any]], pages: dict[int, str], limit: int) -> list[int]:
    tokens = _candidate_tokens(row, expectations)
    page_scores: Counter[int] = Counter()
    for number, text in pages.items():
        compact = _compact(text)
        score = sum(weight for token, weight in tokens if _text_has(compact, token))
        if score:
            page_scores[number] += score
    for item in expectations:
        group_scores = [
            (_score_expectation_page(item, text), number)
            for number, text in pages.items()
        ]
        for score, number in sorted(group_scores, key=lambda pair: (-pair[0], pair[1]))[:2]:
            if score:
                page_scores[number] += score * 3
    if not page_scores:
        for number, text in pages.items():
            if re.search(r"체육|스포츠|실기|학생부|등급|환산", text):
                page_scores[number] += 1
    return [number for number, _ in page_scores.most_common(limit)]


def _score_expectation_page(item: dict[str, Any], text: str) -> int:
    compact = _compact(text)
    key, mode, values = item["key"], item["mode"], item["values"]
    if mode == "text":
        return sum(4 for value in values if _text_has(compact, value))
    if mode == "near":
        return 8 if _near_text(compact, values[0], values[1], 250) else 0
    hits = sum(1 for value in values if _pixel_number_found(text, value))
    if not hits:
        return 0
    keyword_bonus = 0
    if key == "grade_points" and re.search(r"등급|환산|점수", text):
        keyword_bonus = 5
    if key in {"stage_weights", "stage_scores"} and re.search(r"전형요소|반영|실기고사|학생부|만점|총점", text):
        keyword_bonus = 5
    return hits + keyword_bonus


def _candidate_tokens(row: Any, expectations: list[dict[str, Any]]) -> list[tuple[str, int]]:
    weighted = [(str(row["department"] or ""), 8), (str(row["admission_track"] or ""), 5), ("실기", 3), ("학생부", 2), ("전형방법", 2)]
    for item in expectations:
        weight = 5 if item["key"] == "practical_events" else 1
        weighted.extend((str(value), weight) for value in item["values"] if str(value).strip())
    return [(token, weight) for token, weight in weighted if token.strip()]


def _ocr_page(pdf_path: Path, page_number: int, backend: str, refresh: bool) -> str:
    cache_dir = get_miho_home() / "pixel_documents" / "susi27_formula_audit" / _sha256(pdf_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"page_{page_number:04d}.json"
    if cache_path.exists() and not refresh:
        return str(json.loads(cache_path.read_text(encoding="utf-8")).get("text") or "")
    image_path, width, height = _render_page(pdf_path, page_number, cache_dir)
    page = {"page_number": page_number, "page_image_path": str(image_path), "width": width, "height": height, "text": "", "ocr_spans": []}
    result = ocr_pages([page], backend=backend, languages=("ko-KR", "en-US"))
    payload = {"text": page.get("text") or "", "ocr": result, "image_path": str(image_path), "page_number": page_number}
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(payload["text"])


def _ocr_document_text_pages(pdf_path: Path, page_numbers: Any, backend: str, refresh: bool) -> dict[int, str]:
    return {int(number): _ocr_page(pdf_path, int(number), backend, refresh) for number in page_numbers}


def _bounded_page_numbers(page_numbers: Any, limit: int) -> list[int]:
    return sorted(int(number) for number in page_numbers)[: max(1, int(limit or 1))]


def _render_page(pdf_path: Path, page_number: int, out_dir: Path) -> tuple[Path, int, int]:
    import fitz

    image_path = out_dir / f"page_{page_number:04d}.png"
    if image_path.exists():
        return image_path, 0, 0
    with fitz.open(str(pdf_path)) as doc:
        page = doc.load_page(page_number - 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        pix.save(str(image_path))
        return image_path, pix.width, pix.height


def _compare(expectations: list[dict[str, Any]], text: str, passed: list[str], review: list[str]) -> None:
    compact = _compact(text)
    for item in expectations:
        key, values, mode = item["key"], item["values"], item["mode"]
        if mode == "text":
            hits = [value for value in values if _text_has(compact, value)]
        elif mode == "numbers":
            hits = [value for value in values if _pixel_number_found(text, value)]
        else:
            hits = values if _near_text(compact, values[0], values[1], 250) else []
        if len(hits) == len(values):
            passed.append(f"pixel_{key}:pass")
        elif hits:
            review.append(f"pixel_{key}:partial:{len(hits)}/{len(values)}")
        else:
            review.append(f"pixel_{key}:missing")


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    issues = Counter(issue for row in rows for issue in row["needs_review"] + row["hard_failures"])
    return {
        "total_rows": len(rows),
        "pixel_pass_rows": counts["pixel_pass"],
        "pixel_needs_review_rows": counts["pixel_needs_review"],
        "hard_fail_rows": counts["hard_fail"],
        "top_issues": issues.most_common(30),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["university_id", "university", "department", "admission_track", "status", "candidate_pages", "needs_review", "hard_failures"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json.dumps(row[field], ensure_ascii=False) if isinstance(row[field], list) else row[field] for field in fields})


def render_markdown(result: dict[str, Any], json_path: Path, csv_path: Path) -> str:
    summary = result["summary"]
    lines = ["# 2027 수시 체대 픽셀 OCR 산식 전수조사", "", "## 요약"]
    for key in ("total_rows", "pixel_pass_rows", "pixel_needs_review_rows", "hard_fail_rows"):
        lines.append(f"- {key}: {summary[key]}")
    lines.extend([f"- JSON: `{json_path}`", f"- CSV: `{csv_path}`", "", "## 상위 이슈"])
    lines.extend(f"- {count}: {issue}" for issue, count in summary["top_issues"])
    lines.extend(["", "## 재검토 필요 샘플"])
    for row in [item for item in result["rows"] if item["status"] != "pixel_pass"][:80]:
        lines.append(f"- {row['university_id']} {row['university']} / {row['department']}: {row['needs_review'][:5]} {row['hard_failures'][:3]}")
    return "\n".join(lines) + "\n"


def _manifest_hashes(runtime: Path) -> dict[str, str]:
    manifest = runtime.parents[1] / "manifest.jsonl"
    hashes: dict[str, str] = {}
    if not manifest.exists():
        return hashes
    for line in manifest.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        hashes[_manifest_key(str(item.get("path") or ""))] = str(item.get("sha256") or "")
    return hashes


def _manifest_key(path: str) -> str:
    return path.replace("source_files/", "").strip()


def _text_has(compact_text: str, token: Any) -> bool:
    return bool(_loose(token) and _loose(token) in _loose(compact_text))


def _near_text(compact_text: str, left: Any, right: Any, distance: int) -> bool:
    left_token = _loose(left)
    right_token = _loose(right)
    haystack = _loose(compact_text)
    start = haystack.find(left_token)
    while start >= 0:
        if right_token in haystack[start : start + len(left_token) + distance]:
            return True
        start = haystack.find(left_token, start + 1)
    return False


def _loose(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", str(value or "").lower())


def _pixel_number_found(text: str, value: Any) -> bool:
    return _number_found(str(text or "").replace(",", ""), value)


def _select_rows(rows: list[Any], ids: list[str], limit: int) -> list[Any]:
    selected = [row for row in rows if not ids or str(row["university_id"]) in set(ids)]
    return selected[:limit] if limit else selected


if __name__ == "__main__":
    raise SystemExit(main())
