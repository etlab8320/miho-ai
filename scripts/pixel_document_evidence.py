#!/usr/bin/env python3
"""ET Dev OS CLI wrapper for pixel document evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if sys.version_info < (3, 11):
    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render/search page-grounded document evidence.")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    ingest = sub.add_parser("ingest")
    ingest.add_argument("source")
    ingest.add_argument("--max-pages", type=int, default=30)
    ingest.add_argument("--page-range")
    ingest.add_argument("--ocr-backend", default="auto")
    ingest.add_argument("--language", action="append", dest="languages")
    search = sub.add_parser("search")
    search.add_argument("document_id")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    review = sub.add_parser("review")
    review.add_argument("evidence_json")
    review.add_argument("--answer", default="")
    args = parser.parse_args(argv)
    payload = _safe_dispatch(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def _safe_dispatch(args: argparse.Namespace) -> dict[str, Any]:
    try:
        return _dispatch(args)
    except ValueError as exc:
        return _error_payload(str(exc))
    except Exception:
        return _error_payload("문서 근거 처리 중 문제가 발생했습니다. 입력 경로와 manifest를 확인한 뒤 다시 실행해 주세요.")


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.action == "status":
        from plugins.pixel_documents.service import status_payload

        return status_payload()
    if args.action == "ingest":
        from plugins.pixel_documents.service import ingest_document

        return ingest_document(
            args.source,
            max_pages=args.max_pages,
            page_range=args.page_range,
            ocr_backend=args.ocr_backend,
            languages=args.languages,
        )
    if args.action == "search":
        from plugins.pixel_documents.service import search_document

        return search_document(args.document_id, args.query, limit=args.limit)
    if args.action == "review":
        from plugins.pixel_documents.service import review_evidence

        return review_evidence(args.evidence_json, answer=args.answer)
    return {"ok": False, "message_ko": "알 수 없는 작업입니다."}


def _error_payload(message_ko: str) -> dict[str, Any]:
    return {"ok": False, "message_ko": message_ko, "errors": [message_ko]}


if __name__ == "__main__":
    raise SystemExit(main())
