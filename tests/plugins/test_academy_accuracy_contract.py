"""Academy accuracy contract coverage tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plugins.academy_ops.accuracy_contract import (
    ACADEMY_ACCURACY_SCHEMA,
    academy_accuracy_matrix,
    build_accuracy_receipt,
    validate_accuracy_matrix,
    validate_accuracy_receipt,
)
from plugins.academy_ops.practical_reco_all_candidates import (
    _all_candidates_tool_handler,
    build_all_candidates_content,
)


def _candidate(index: int, *, region: str = "강원") -> dict[str, Any]:
    return {
        "university_id": str(index),
        "university": f"검증대{index}",
        "department": "스포츠학과",
        "admission_track": "실기일반",
        "region": region,
        "practical_events": ["제자리멀리뛰기", "10m왕복달리기"],
        "student_record_score": 310.0 + index,
        "max_possible_total": 850.0 + index,
        "prev_first_total": 810.0,
        "prev_final_total": 830.0,
        "suggested_verdict": "상향",
        "reachable_at_full_practical": True,
    }


def _fake_recommend(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    candidates = [_candidate(1, region="강원"), _candidate(2, region="충남")]
    return {
        "student": "김서연",
        "region_filter": ["강원", "충남", "충북"],
        "total_feasible": len(candidates),
        "returned": len(candidates),
        "candidates": candidates,
    }


def test_academy_accuracy_matrix_covers_current_and_extensible_engines() -> None:
    matrix = academy_accuracy_matrix()
    by_key = {entry["key"]: entry for entry in matrix}

    assert set(by_key) >= {
        "hakjong_report",
        "susi_practical_all_candidates",
        "susi_score_engine",
        "jungsi_score_engine",
    }
    assert by_key["hakjong_report"]["canonical_tool"] == "academy_hakjong_report_package"
    assert "life_record_evidence" in by_key["hakjong_report"]["required_axes"]
    assert "full_practical_reachability" in by_key["susi_practical_all_candidates"]["required_axes"]
    assert by_key["susi_score_engine"]["canonical_tool"] == "susi27_score_calculate"
    assert by_key["jungsi_score_engine"]["canonical_tool"] == "jungsi_student_university_score"
    assert validate_accuracy_matrix(matrix) == []


def test_build_accuracy_receipt_requires_all_axes() -> None:
    receipt = build_accuracy_receipt(
        engine_key="susi_practical_all_candidates",
        source_tools=["susi27_recommend_candidates"],
        gates={
            "student_identity": True,
            "region_scope": True,
            "single_pipeline": True,
            "practical_only": True,
            "full_practical_reachability": True,
            "no_truncated_candidates": True,
            "pdf_physical_validation": True,
        },
    )

    assert receipt["schema_version"] == ACADEMY_ACCURACY_SCHEMA
    assert receipt["status"] == "pass"
    assert receipt["canonical_tool"] == "academy_practical_reco_all_candidates"
    assert validate_accuracy_receipt(receipt) == []


def test_build_accuracy_receipt_rejects_missing_axis() -> None:
    receipt = build_accuracy_receipt(
        engine_key="susi_practical_all_candidates",
        source_tools=["susi27_recommend_candidates"],
        gates={
            "student_identity": True,
            "region_scope": True,
            "single_pipeline": True,
            "practical_only": True,
            "full_practical_reachability": True,
            "no_truncated_candidates": True,
        },
    )

    assert receipt["status"] == "fail"
    assert any("pdf_physical_validation" in error for error in validate_accuracy_receipt(receipt))


def test_practical_all_candidates_content_contains_accuracy_receipt(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_all_candidates.recommend_candidates",
        _fake_recommend,
    )

    content = build_all_candidates_content("김서연", "강원, 충청")
    receipt = content["accuracy_receipt"]

    assert receipt["status"] == "pass"
    assert receipt["engine_key"] == "susi_practical_all_candidates"
    assert receipt["source_tools"] == ["susi27_recommend_candidates"]
    assert validate_accuracy_receipt(receipt) == []


def test_practical_all_candidates_manifest_contains_accuracy_receipt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_all_candidates.recommend_candidates",
        _fake_recommend,
    )
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_all_candidates._chromium_print_to_pdf",
        lambda _html_path, pdf_path: pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n"),
    )
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_all_candidates._validate_pdf_physical",
        lambda *_args, **_kwargs: None,
    )

    result = json.loads(
        _all_candidates_tool_handler({"student_name": "김서연", "region": "강원, 충청"})
    )

    assert result["ok"] is True
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["accuracy_receipt"]["status"] == "pass"
    assert validate_accuracy_receipt(manifest["accuracy_receipt"]) == []
