from __future__ import annotations

import importlib.util
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "audit_susi27_pdf_formulas.py"
SPEC = importlib.util.spec_from_file_location("audit_susi27_pdf_formulas", SCRIPT_PATH)
assert SPEC and SPEC.loader
audit_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_module
SPEC.loader.exec_module(audit_module)


def _make_runtime(
    tmp_path: Path,
    text: str,
    *,
    pdf_name: str = "2027_테스트대학교_수시모집요강.pdf",
    runtime_rel: str = "runtime",
) -> tuple[Path, str, str]:
    runtime = tmp_path / runtime_rel
    pdf_rel = f"source_files/pdfs_official/테스트대학교/{pdf_name}"
    text_rel = "texts/pdfs_official__테스트대학교__2027_테스트대학교_수시모집요강.txt"
    pdf_path = runtime / pdf_rel
    text_path = runtime / text_rel
    pdf_path.parent.mkdir(parents=True)
    text_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4\n")
    text_path.write_text(text, encoding="utf-8")
    return runtime, pdf_rel, text_rel


def _make_db(tmp_path: Path, *, pdf_rel: str, text_rel: str, include_hashes: bool = True) -> Path:
    db_path = tmp_path / "susi27_staging.sqlite3"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        create table db_university_rows (
            university_id text primary key,
            university text,
            department text,
            admission_track text,
            quota text,
            source_status text,
            pdf_rel_path text,
            text_path text
        );
        create table susi_calculation_rules (
            university_id text primary key,
            score_logic_json text,
            practical_events_json text,
            admission_meta_json text,
            school_info_json text,
            source_text_path text
        );
        """
    )
    score = {
        "calculation_readiness": "ready_for_sample_calculation",
        "stage_weights": {"student_record": "40", "practical": "60"},
        "stage_scores": {"student_record": "400", "practical": "600"},
        "grade_points": {"1": "100", "2": "90", "3": "80"},
    }
    if include_hashes:
        runtime = tmp_path / "runtime"
        score["official_pdf_sha256"] = hashlib.sha256((runtime / pdf_rel).read_bytes()).hexdigest()
        score["official_text_sha256"] = hashlib.sha256((runtime / text_rel).read_bytes()).hexdigest()
    events = {
        "no_practical": False,
        "practical_full_score": "600",
        "events": [{"name": "제자리멀리뛰기"}, {"name": "10m왕복달리기"}],
    }
    meta = {"stage2": {"student_record": "40", "practical": "60"}}
    con.execute(
        "insert into db_university_rows values (?, ?, ?, ?, ?, ?, ?, ?)",
        ("1", "테스트대학교", "체육학과", "실기우수자", "12", "official_pdf_codex_verified", pdf_rel, text_rel),
    )
    con.execute(
        "insert into susi_calculation_rules values (?, ?, ?, ?, ?, ?)",
        ("1", json.dumps(score), json.dumps(events), json.dumps(meta), "{}", text_rel),
    )
    con.commit()
    con.close()
    return db_path


def test_audit_passes_only_when_every_formula_value_is_exact(tmp_path: Path) -> None:
    text = (
        "2027학년도 수시모집요강 테스트대학교 체육학과 12 실기우수자 "
        "학생부 40 실기 60 학생부교과 400 실기고사 600 "
        "1등급 100 2등급 90 3등급 80 제자리멀리뛰기 10m왕복달리기"
    )
    runtime, pdf_rel, text_rel = _make_runtime(tmp_path, text)
    db_path = _make_db(tmp_path, pdf_rel=pdf_rel, text_rel=text_rel)

    result = audit_module.run_audit(audit_module.AuditPaths(runtime=runtime, db=db_path))

    assert result["summary"]["pass_rows"] == 1
    assert result["summary"]["needs_review_rows"] == 0
    assert result["summary"]["hard_fail_rows"] == 0


def test_audit_marks_missing_formula_value_as_needs_review(tmp_path: Path) -> None:
    text = (
        "2027학년도 수시모집요강 테스트대학교 체육학과 12 실기우수자 "
        "학생부 40 실기 60 학생부교과 400 실기고사 600 "
        "1등급 100 2등급 90 제자리멀리뛰기 10m왕복달리기"
    )
    runtime, pdf_rel, text_rel = _make_runtime(tmp_path, text)
    db_path = _make_db(tmp_path, pdf_rel=pdf_rel, text_rel=text_rel)

    result = audit_module.run_audit(audit_module.AuditPaths(runtime=runtime, db=db_path))

    assert result["summary"]["pass_rows"] == 0
    assert result["summary"]["needs_review_rows"] == 1
    assert "grade point table not exact:2/3" in result["rows"][0]["needs_review"]


def test_audit_marks_missing_hash_as_needs_review(tmp_path: Path) -> None:
    text = (
        "2027학년도 수시모집요강 테스트대학교 체육학과 12 실기우수자 "
        "학생부 40 실기 60 학생부교과 400 실기고사 600 "
        "1등급 100 2등급 90 3등급 80 제자리멀리뛰기 10m왕복달리기"
    )
    runtime, pdf_rel, text_rel = _make_runtime(tmp_path, text)
    db_path = _make_db(tmp_path, pdf_rel=pdf_rel, text_rel=text_rel, include_hashes=False)

    result = audit_module.run_audit(audit_module.AuditPaths(runtime=runtime, db=db_path))

    assert result["summary"]["pass_rows"] == 0
    assert "official_pdf_sha256 missing" in result["rows"][0]["needs_review"]
    assert "official_text_sha256 missing" in result["rows"][0]["needs_review"]


def test_number_match_requires_digit_boundaries() -> None:
    assert audit_module._number_found("실기60%학생부40", "60") is True
    assert audit_module._number_found("실기600점학생부400점", "60") is False


def test_audit_fails_if_source_is_admission_plan_not_susi_guide(tmp_path: Path) -> None:
    text = "2027학년도 수시모집요강 테스트대학교 체육학과 12"
    runtime, pdf_rel, text_rel = _make_runtime(tmp_path, text, pdf_name="2027_테스트대학교_시행계획.pdf")
    db_path = _make_db(tmp_path, pdf_rel=pdf_rel, text_rel=text_rel)

    result = audit_module.run_audit(audit_module.AuditPaths(runtime=runtime, db=db_path))

    assert result["summary"]["hard_fail_rows"] == 1
    assert "source references 대학입학전형시행계획" in result["rows"][0]["hard_failures"]


def test_cli_defaults_runtime_from_reference_root_env(tmp_path: Path, monkeypatch) -> None:
    text = (
        "2027학년도 수시모집요강 테스트대학교 체육학과 12 실기우수자 "
        "학생부 40 실기 60 학생부교과 400 실기고사 600 "
        "1등급 100 2등급 90 3등급 80 제자리멀리뛰기 10m왕복달리기"
    )
    reference_root = tmp_path / "reference"
    runtime, pdf_rel, text_rel = _make_runtime(
        tmp_path,
        text,
        runtime_rel="reference/runtime/susi27_pipeline",
    )
    db_path = _make_db(tmp_path, pdf_rel=pdf_rel, text_rel=text_rel, include_hashes=False)
    monkeypatch.setenv("MIHO_SUSI27_REFERENCE_ROOT", str(reference_root))
    monkeypatch.setenv("MIHO_SUSI27_STAGING_DB", str(db_path))

    result = audit_module.main(["--out-dir", str(tmp_path / "audit"), "--json-only"])

    assert result == 0


def test_cli_requires_runtime_without_default_env(monkeypatch) -> None:
    monkeypatch.delenv("MIHO_SUSI27_REFERENCE_ROOT", raising=False)
    monkeypatch.delenv("MIHO_SUSI27_RUNTIME", raising=False)
    monkeypatch.delenv("MIHO_SUSI27_STAGING_DB", raising=False)

    with pytest.raises(SystemExit) as exc:
        audit_module.main(["--json-only"])

    assert exc.value.code == 2
