"""Compact delivery payloads for sports report package results."""

from __future__ import annotations

from typing import Any


def compact_payloads(payloads: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in payloads.items():
        if not value:
            continue
        if key == "max_analysis" and isinstance(value, dict):
            compact[key] = compact_max_analysis(value)
        elif key == "cohort_model" and isinstance(value, dict):
            compact[key] = compact_cohort_model(value)
        elif key == "feedback" and isinstance(value, dict):
            compact[key] = compact_feedback(value)
        elif key == "html" and isinstance(value, dict):
            compact[key] = compact_html(value)
        elif key == "pdf" and isinstance(value, dict):
            compact[key] = compact_pdf(value)
        else:
            compact[key] = value
    return compact


def compact_max_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    latest = payload.get("latest_record") if isinstance(payload.get("latest_record"), dict) else {}
    return {
        "ok": bool(payload.get("ok")),
        "source": payload.get("source"),
        "record_count": int(payload.get("record_count") or 0),
        "latest_record": {
            "student_name": latest.get("student_name"),
            "academy_name": latest.get("academy_name"),
            "measured_at": latest.get("measured_at"),
            "record_value": latest.get("record_value"),
            "record_unit": latest.get("record_unit"),
        },
        "reviewer": payload.get("reviewer") if isinstance(payload.get("reviewer"), dict) else {},
    }


def compact_cohort_model(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(model.get("ok")),
        "basis": model.get("basis"),
        "gender": model.get("gender"),
        "cohort_session_count": int(model.get("cohort_session_count") or 0),
        "elite_session_count": int(model.get("elite_session_count") or 0),
        "elite_5pct_session_count": int(model.get("elite_5pct_session_count") or 0),
        "variable_keys": sorted((model.get("variables") or {}).keys())[:24],
    }


def compact_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    output = payload.get("coach_output") if isinstance(payload.get("coach_output"), dict) else {}
    return {
        "ok": bool(payload.get("ok")),
        "evidence_status": payload.get("evidence_status"),
        "summary": output.get("summary"),
        "bottlenecks": list(output.get("bottlenecks") or [])[:5],
        "reviewer": payload.get("reviewer") if isinstance(payload.get("reviewer"), dict) else {},
    }


def compact_html(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(payload.get("ok")),
        "template_key": payload.get("template_key"),
        "html_path": payload.get("html_path"),
    }


def compact_pdf(payload: dict[str, Any]) -> dict[str, Any]:
    quality = payload.get("pdf_quality_gate") if isinstance(payload.get("pdf_quality_gate"), dict) else {}
    return {
        "success": bool(payload.get("success")),
        "artifact_path": payload.get("artifact_path") or payload.get("pdf_path"),
        "pdf_path": payload.get("pdf_path") or payload.get("artifact_path"),
        "pdf_quality_gate": {
            "ok": bool(quality.get("ok")),
            "page_count": quality.get("page_count"),
            "layout_errors": list(quality.get("layout_errors") or []),
            "forbidden_text_hits": list(quality.get("forbidden_text_hits") or []),
        },
        "reviewer": payload.get("reviewer") if isinstance(payload.get("reviewer"), dict) else {},
    }
