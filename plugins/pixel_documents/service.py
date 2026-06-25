"""Pixel document evidence service used by Miho and ET Dev OS."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .ocr import ocr_capabilities, ocr_pages
from .rendering import capabilities as render_capabilities
from .rendering import render_source
from .storage import SCHEMA_VERSION, load_manifest, save_manifest


def status_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "operation": "pixel_document.status",
        "capabilities": {**render_capabilities(), **ocr_capabilities()},
        "storage": "MIHO_HOME/pixel_documents",
    }


def ingest_document(
    source: str,
    *,
    max_pages: int = 30,
    ocr_backend: str = "auto",
    languages: list[str] | tuple[str, ...] | None = None,
    page_range: str | None = None,
) -> dict[str, Any]:
    rendered = render_source(source, max_pages=max_pages, page_range=page_range)
    pages = rendered["pages"]
    ocr = ocr_pages(pages, backend=ocr_backend, languages=languages)
    has_text = any(str(page.get("text") or "").strip() for page in pages)
    ingest_status = "ready" if has_text else "provisional"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "document_id": rendered["document_id"],
        "source": {
            "id": rendered["source_id"],
            "label": rendered["source_label"],
            "path": rendered["source_path"],
            "kind": rendered["source_kind"],
            "sha256": rendered["source_sha256"],
        },
        "render": rendered["render"],
        "ocr": ocr,
        "ingest_status": ingest_status,
        "pages": pages,
        "privacy": {
            "storage": "profile_scoped_miho_home",
            "long_term_memory": "disabled",
            "source_text_memory": "disabled",
        },
    }
    path = save_manifest(manifest)
    return {
        "ok": True,
        "operation": "pixel_document.ingest",
        "document_id": rendered["document_id"],
        "manifest_path": str(path),
        "source": manifest["source"],
        "render": rendered["render"],
        "ocr": ocr,
        "ingest_status": ingest_status,
        "pages": pages,
        "reviewer": _ingest_reviewer(ingest_status),
        "retry_tools": [] if ingest_status == "ready" else ["pixel_document_evidence"],
        "message_ko": _ingest_message(ingest_status),
    }


def search_document(document_id_or_path: str, query: str, *, limit: int = 5) -> dict[str, Any]:
    if not str(query or "").strip():
        return _soft_error("검색어가 필요합니다.")
    manifest = load_manifest(document_id_or_path)
    results = _rank_pages(manifest, query, limit=max(1, min(int(limit or 5), 20)))
    status = "ready" if results else "provisional"
    return {
        "ok": True,
        "operation": "pixel_document.search",
        "document_id": manifest["document_id"],
        "query": query,
        "search_status": status,
        "count": len(results),
        "results": results,
        "reviewer": {
            "name": "pixel_document_reviewer",
            "status": "pass" if results else "retry_needed",
            "checked": ["manifest", "page_image_path", "source_sha256", "excerpt"],
        },
        "message_ko": "페이지 이미지 근거와 함께 검색 결과를 찾았습니다." if results else "직접 일치 페이지는 아직 대기 상태입니다. OCR 또는 검색어를 바꿔 재검색할 수 있습니다.",
    }


def review_evidence(evidence: Any, *, answer: str = "") -> dict[str, Any]:
    payload = evidence if isinstance(evidence, dict) else _loads(evidence)
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not results:
        return _soft_error("검토할 문서 근거가 필요합니다.", operation="pixel_document.review")
    missing = [
        str(item.get("page_number"))
        for item in results
        if not item.get("page_image_path") or not item.get("excerpt")
    ]
    status = "pass" if not missing else "retry_needed"
    return {
        "ok": True,
        "operation": "pixel_document.review",
        "review_status": status,
        "answer_preview": str(answer or "")[:500],
        "reviewer": {
            "name": "pixel_document_reviewer",
            "status": status,
            "checked": ["page evidence", "excerpt", "crop evidence"],
            "missing_pages": missing,
        },
        "message_ko": "문서 근거가 답변 검토에 사용할 수 있는 형태입니다." if status == "pass" else "일부 페이지 근거가 부족해 같은 검색을 다시 실행해 주세요.",
    }


def _rank_pages(manifest: dict[str, Any], query: str, *, limit: int) -> list[dict[str, Any]]:
    tokens = _tokens(query)
    scored: list[tuple[int, dict[str, Any]]] = []
    for page in manifest.get("pages") or []:
        text = str(page.get("text") or "")
        score = _score(text, tokens)
        if score <= 0:
            continue
        hit = {
            "page_number": page.get("page_number"),
            "score": score,
            "excerpt": _excerpt(text, tokens),
            "page_image_path": page.get("page_image_path"),
            "source_sha256": manifest.get("source", {}).get("sha256"),
            "text_source": page.get("text_source"),
            "render_mode": page.get("render_mode"),
            "reviewer": {
                "name": "pixel_document_reviewer",
                "status": "pass",
                "checked": ["page_number", "page_image_path", "excerpt"],
            },
        }
        crop = _crop_for_tokens(page, tokens, manifest["document_id"])
        hit.update(crop)
        scored.append((score, hit))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:limit]]


def _crop_for_tokens(page: dict[str, Any], tokens: list[str], document_id: str) -> dict[str, Any]:
    spans = [
        span for span in page.get("ocr_spans") or []
        if isinstance(span, dict) and _score(str(span.get("text") or ""), tokens) > 0
    ]
    if not spans:
        return {"bbox": None, "crop_path": ""}
    bbox = _union_bbox([span.get("bbox") for span in spans if isinstance(span.get("bbox"), dict)])
    if not bbox:
        return {"bbox": None, "crop_path": ""}
    crop_path = _make_crop(Path(str(page["page_image_path"])), bbox, document_id, int(page.get("page_number") or 1))
    return {"bbox": bbox, "crop_path": str(crop_path) if crop_path else ""}


def _make_crop(image_path: Path, bbox: dict[str, float], document_id: str, page_number: int) -> Path | None:
    try:
        from PIL import Image
    except Exception:
        return None
    out_dir = image_path.parent / "crops"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{document_id}_p{page_number:04d}_crop.png"
    with Image.open(image_path) as image:
        width, height = image.size
        pad = 12
        left = max(0, int(bbox["x"] * width) - pad)
        top = max(0, int(bbox["y"] * height) - pad)
        right = min(width, int((bbox["x"] + bbox["w"]) * width) + pad)
        bottom = min(height, int((bbox["y"] + bbox["h"]) * height) + pad)
        image.crop((left, top, right, bottom)).save(out, format="PNG")
    return out


def _union_bbox(boxes: list[dict[str, Any]]) -> dict[str, float] | None:
    if not boxes:
        return None
    xs = [float(box.get("x") or 0) for box in boxes]
    ys = [float(box.get("y") or 0) for box in boxes]
    rights = [float(box.get("x") or 0) + float(box.get("w") or 0) for box in boxes]
    bottoms = [float(box.get("y") or 0) + float(box.get("h") or 0) for box in boxes]
    x = max(0.0, min(xs))
    y = max(0.0, min(ys))
    return {"x": x, "y": y, "w": min(1.0, max(rights)) - x, "h": min(1.0, max(bottoms)) - y}


def _score(text: str, tokens: list[str]) -> int:
    lowered = text.lower()
    return sum(lowered.count(token.lower()) for token in tokens if token)


def _tokens(query: str) -> list[str]:
    return [token for token in re.split(r"\s+", str(query or "").strip()) if token]


def _excerpt(text: str, tokens: list[str], *, window: int = 220) -> str:
    if not text:
        return ""
    lowered = text.lower()
    positions = [lowered.find(token.lower()) for token in tokens if lowered.find(token.lower()) >= 0]
    start = max(0, min(positions) - 70) if positions else 0
    return re.sub(r"\s+", " ", text[start : start + window]).strip()


def _ingest_reviewer(status: str) -> dict[str, Any]:
    return {
        "name": "pixel_document_reviewer",
        "status": "pass" if status == "ready" else "retry_needed",
        "checked": ["source hash", "page images", "ocr/text evidence", "privacy scope"],
    }


def _ingest_message(status: str) -> str:
    if status == "ready":
        return "문서 화면 근거와 검색 가능한 텍스트를 저장했습니다."
    return "문서 화면 근거는 저장됐고 OCR 텍스트는 대기 상태입니다. Apple Vision OCR을 연결하면 같은 문서를 다시 읽을 수 있습니다."


def _soft_error(message: str, *, operation: str = "pixel_document.search") -> dict[str, Any]:
    return {"ok": False, "operation": operation, "message_ko": message, "errors": [message]}


def _loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        loaded = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}
