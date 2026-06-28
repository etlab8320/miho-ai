"""Tool-isolated local paper references for sports performance evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home

from .catalog import normalize_exercise

LOCAL_REFERENCE_SOURCE = "sports_local_reference"
LOCAL_REF_PREFIX = "sports_ref:"
MANIFEST_NAME = "manifest.json"


def reference_root() -> Path:
    return get_miho_home() / "sports_performance" / "reference_papers"


def manifest_path() -> Path:
    return reference_root() / MANIFEST_NAME


def load_local_reference_papers() -> list[dict[str, Any]]:
    try:
        payload = json.loads(manifest_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    papers = payload.get("papers") if isinstance(payload, dict) else None
    return [item for item in papers or [] if isinstance(item, dict)]


def ingest_reference_directory(source_dir: str | Path, *, target_root: Path | None = None) -> dict[str, Any]:
    source = Path(source_dir).expanduser()
    target = target_root or reference_root()
    pdfs = list(_iter_reference_pdfs(source))
    target.mkdir(parents=True, exist_ok=True)
    papers: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for pdf in pdfs:
        exercise = _exercise_from_path(pdf, source)
        if exercise is None:
            skipped.append({"path": str(pdf), "reason": "지원 종목 폴더를 찾지 못했다."})
            continue
        digest = _sha256_file(pdf)
        dest = _copy_reference_pdf(pdf, target=target, exercise_key=exercise["key"], digest=digest)
        papers.append(_paper_entry(pdf, dest=dest, exercise=exercise, digest=digest))
    payload = {
        "schema_version": 1,
        "source_dir": str(source),
        "target_root": str(target),
        "ingested_at": int(time.time()),
        "papers": sorted(papers, key=lambda item: (item["exercise_key"], item["title"])),
        "skipped": skipped,
    }
    _write_manifest(target / MANIFEST_NAME, payload)
    return {
        "ok": True,
        "source_dir": str(source),
        "manifest_path": str(target / MANIFEST_NAME),
        "stored_count": len(papers),
        "skipped_count": len(skipped),
        "papers": payload["papers"],
        "skipped": skipped,
    }


def _iter_reference_pdfs(source: Path) -> list[Path]:
    if not source.exists():
        return []
    return sorted(path for path in source.rglob("*.pdf") if path.is_file())


def _exercise_from_path(path: Path, root: Path) -> dict[str, Any] | None:
    candidates = [path.parent.name, *path.relative_to(root).parts[:-1]]
    for candidate in candidates:
        exercise = normalize_exercise(_clean_text(candidate))
        if exercise is not None:
            return exercise
    return None


def _paper_entry(
    original_path: Path,
    *,
    dest: Path,
    exercise: dict[str, Any],
    digest: str,
) -> dict[str, Any]:
    title = _clean_title(original_path.stem)
    paper_id = digest[:16]
    return {
        "id": paper_id,
        "source": LOCAL_REFERENCE_SOURCE,
        "title": title,
        "category": "physical",
        "status": "completed",
        "chunk_count": 1,
        "summary": _summary(title, exercise),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "exercise_key": exercise["key"],
        "local_pdf_path": str(dest),
        "original_path": str(original_path),
        "sha256": digest,
    }


def _summary(title: str, exercise: dict[str, Any]) -> str:
    return (
        f"{exercise['name_ko']} ({exercise['key']}) 운동역학, athlete training, "
        f"sports performance 참고 PDF다. 제목: {title}. "
        "세부 코칭 주장에는 로컬 원문 PDF 확인이 필요하다."
    )


def _copy_reference_pdf(source: Path, *, target: Path, exercise_key: str, digest: str) -> Path:
    dest_dir = target / "pdfs" / exercise_key
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{digest[:12]}-{_safe_filename(_clean_text(source.name))}"
    dest = dest_dir / filename
    shutil.copy2(source, dest)
    return dest


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_title(value: str) -> str:
    return _clean_text(value).replace(" (2)", "").strip()


def _clean_text(value: str) -> str:
    return unicodedata.normalize("NFC", str(value or "")).strip()


def _safe_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in " ._-()" else "_" for ch in value)
    return cleaned.strip(" .") or "paper.pdf"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest local sports paper PDFs into Miho's isolated store.")
    parser.add_argument("source_dir")
    args = parser.parse_args(argv)
    result = ingest_reference_directory(args.source_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
