"""Optional OCR backends for pixel document evidence."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


DEFAULT_LANGUAGES = ("ko-KR", "en-US")


def ocr_capabilities() -> dict[str, Any]:
    return {
        "apple_vision_ocr": apple_vision_available(),
        "apple_vision_install_hint": "pyobjc-framework-Vision==11.1 pyobjc-framework-Quartz==11.1",
    }


def apple_vision_available() -> bool:
    return bool(importlib.util.find_spec("Vision") and importlib.util.find_spec("Quartz"))


def ocr_pages(
    pages: list[dict[str, Any]],
    *,
    backend: str = "auto",
    languages: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    selected = (backend or "auto").strip().lower()
    if selected in {"none", "off", "skip"}:
        return {"backend": "none", "available": False, "status": "skipped", "page_count": len(pages)}
    if selected not in {"auto", "apple_vision"}:
        return {"backend": selected, "available": False, "status": "unsupported", "page_count": len(pages)}
    should_install = selected == "apple_vision"
    modules = _load_apple_vision(install=should_install)
    if modules is None:
        return {
            "backend": "apple_vision",
            "available": False,
            "status": "needs_backend",
            "page_count": len(pages),
            "retry_instruction_ko": "Apple Vision OCR 바인딩을 설치한 뒤 같은 문서를 다시 인제스트하면 됩니다.",
        }
    processed = 0
    errors: list[str] = []
    force_pixel_ocr = selected == "apple_vision"
    for page in pages:
        existing_text = str(page.get("text") or "").strip()
        if existing_text and not force_pixel_ocr:
            continue
        try:
            text, spans = _recognize_text(Path(str(page["page_image_path"])), modules, tuple(languages or DEFAULT_LANGUAGES))
        except Exception as exc:  # noqa: BLE001 - backend failure should not kill ingest
            errors.append(f"{page.get('page_number')}: {type(exc).__name__}: {exc}")
            continue
        if existing_text:
            page["embedded_text"] = existing_text
        page["text"] = text
        page["text_source"] = "apple_vision_ocr"
        page["ocr_spans"] = spans
        processed += 1
    return {
        "backend": "apple_vision",
        "available": True,
        "status": "ready" if processed or not errors else "error",
        "page_count": len(pages),
        "processed_pages": processed,
        "errors": errors,
    }


def _load_apple_vision(*, install: bool) -> tuple[Any, Any, Any] | None:
    if install:
        try:
            from tools.lazy_deps import ensure

            ensure("tool.pixel_documents_apple_vision", prompt=False)
        except Exception:
            pass
    try:
        import Foundation  # type: ignore[import-not-found]
        import Quartz  # type: ignore[import-not-found]
        import Vision  # type: ignore[import-not-found]
    except ImportError:
        return None
    return Foundation, Quartz, Vision


def _recognize_text(image_path: Path, modules: tuple[Any, Any, Any], languages: tuple[str, ...]) -> tuple[str, list[dict[str, Any]]]:
    Foundation, Quartz, Vision = modules
    url = Foundation.NSURL.fileURLWithPath_(str(image_path))
    source = Quartz.CGImageSourceCreateWithURL(url, None)
    if source is None:
        raise RuntimeError("이미지를 열 수 없습니다.")
    cg_image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
    if cg_image is None:
        raise RuntimeError("OCR용 이미지 프레임을 만들 수 없습니다.")

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    try:
        request.setRecognitionLanguages_(list(languages))
    except Exception:
        pass
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, {})
    result = handler.performRequests_error_([request], None)
    ok = result[0] if isinstance(result, tuple) else bool(result)
    if not ok:
        raise RuntimeError("Apple Vision OCR 요청이 완료되지 않았습니다.")
    spans: list[dict[str, Any]] = []
    lines: list[str] = []
    for observation in request.results() or []:
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        text = str(candidate.string() or "").strip()
        if not text:
            continue
        lines.append(text)
        spans.append({"text": text, "confidence": float(candidate.confidence()), "bbox": _bbox(observation)})
    return "\n".join(lines), spans


def _bbox(observation: Any) -> dict[str, float]:
    box = observation.boundingBox()
    x = float(box.origin.x)
    y_bottom = float(box.origin.y)
    w = float(box.size.width)
    h = float(box.size.height)
    return {"x": x, "y": max(0.0, 1.0 - y_bottom - h), "w": w, "h": h}
