"""Visual review contract helpers for HTML-first PDF artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.registry import tool_result


def base_checked() -> list[str]:
    return [
        "html_source",
        "pdf_rendered",
        "metadata_scrubbed",
        "page_previews",
        "contact_sheet",
    ]


def visual_review(value: Any) -> dict[str, Any]:
    raw = _loads_review_object(value)
    if raw is None:
        return {
            "provided": False,
            "passed": False,
            "raw": {},
            "checked": [],
            "warnings": [],
            "errors": [],
        }

    status = str(
        raw.get("status") or raw.get("verdict") or raw.get("result") or ""
    ).strip().casefold()
    errors = _string_list(raw.get("errors") or raw.get("issues") or raw.get("problems"))
    warnings = _string_list(raw.get("warnings"))
    checked = _string_list(raw.get("checked")) or ["visual_review"]
    passed = status in {"pass", "passed", "ok", "approved"} and not errors
    return {
        "provided": True,
        "passed": passed,
        "raw": raw,
        "checked": checked,
        "warnings": warnings,
        "errors": errors,
    }


def visual_review_required(
    *,
    html_path: Path,
    pdf_path: Path,
    payload: dict[str, Any],
) -> str:
    contact_sheet = str(payload.get("contact_sheet") or "")
    review_prompt = str(payload.get("review_prompt") or "")
    return tool_result(
        success=False,
        next_action="visual_review_required",
        delivery_status="provisional",
        html_path=str(html_path),
        pdf_path=str(pdf_path.resolve()),
        artifact_path=str(pdf_path.resolve()),
        contact_sheet_path=contact_sheet,
        page_images=payload.get("page_images") or [],
        pdf_quality_gate=payload,
        visual_review_required=True,
        review_prompt=review_prompt,
        reviewer={
            "name": "html_pdf_quality_review",
            "status": "retry_needed",
            "checked": base_checked(),
            "warnings": ["visual_review_missing"],
            "retry_tools": [
                "vision_analyze",
                "html_pdf_quality_gate",
                "media_delivery_contract",
            ],
            "retry_args": [
                {"image_url": contact_sheet, "question": review_prompt},
                {
                    "html_path": str(html_path),
                    "pdf_path": str(pdf_path.resolve()),
                },
                {
                    "artifact_path": str(pdf_path.resolve()),
                    "caption": "완성본이야.",
                },
            ],
            "retry_instruction_ko": (
                "contact sheet를 vision reviewer로 검수한 뒤, 통과 결과를 "
                "visual_review에 넣어 html_pdf_quality_gate를 다시 실행하고 "
                "media_delivery_contract까지 통과해야 합니다."
            ),
        },
        message_ko="PDF 렌더링은 완료됐지만 contact sheet 시각 검수가 아직 필요합니다.",
    )


def visual_review_failed(
    *,
    html_path: Path,
    pdf_path: Path,
    payload: dict[str, Any],
    visual_review: dict[str, Any],
) -> str:
    contact_sheet = str(payload.get("contact_sheet") or "")
    review_prompt = str(payload.get("review_prompt") or "")
    corrected_html = html_path.with_name(f"{html_path.stem}.autofixed{html_path.suffix}")
    return tool_result(
        success=False,
        next_action="revise_html_and_retry",
        delivery_status="blocked",
        html_path=str(html_path),
        pdf_path=str(pdf_path.resolve()),
        artifact_path=str(pdf_path.resolve()),
        contact_sheet_path=str(payload.get("contact_sheet") or ""),
        page_images=payload.get("page_images") or [],
        pdf_quality_gate=payload,
        visual_review=visual_review["raw"],
        errors=visual_review["errors"],
        reviewer={
            "name": "html_pdf_quality_review",
            "status": "retry_needed",
            "checked": base_checked() + ["visual_review"],
            "warnings": visual_review["warnings"],
            "retry_tools": [
                "html_pdf_autocorrect",
                "html_pdf_quality_gate",
                "vision_analyze",
                "html_pdf_quality_gate",
                "media_delivery_contract",
            ],
            "retry_args": [
                {
                    "html_path": str(html_path),
                    "output_html_path": str(corrected_html),
                    "pdf_path": str(pdf_path.resolve()),
                    "visual_review": visual_review["raw"],
                },
                {
                    "html_path": str(corrected_html),
                    "pdf_path": str(pdf_path.resolve()),
                },
                {
                    "image_url": contact_sheet,
                    "question": review_prompt,
                },
                {
                    "html_path": str(corrected_html),
                    "pdf_path": str(pdf_path.resolve()),
                },
                {
                    "artifact_path": str(pdf_path.resolve()),
                    "caption": "완성본이야.",
                }
            ],
            "retry_instruction_ko": (
                "visual reviewer가 지적한 레이아웃 문제를 HTML에서 수정한 뒤 "
                "PDF를 다시 렌더하고 contact sheet를 재검수한 뒤 첨부 계약까지 통과해야 합니다."
            ),
        },
        message_ko="PDF 시각 검수가 통과하지 못했습니다. HTML을 수정해 다시 렌더해야 합니다.",
    )


def _loads_review_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        nested = _loads_review_object(value.get("analysis"))
        return nested if nested is not None else value
    if not isinstance(value, str):
        return None
    parsed = _loads_json(value)
    if parsed is not None:
        return _loads_review_object(parsed.get("analysis")) or parsed
    return {"status": "", "analysis": value}


def _loads_json(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(str(value or "").strip())
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
