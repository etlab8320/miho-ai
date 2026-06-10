"""Hardening tests for life-record readiness gates."""

from __future__ import annotations

from pathlib import Path


def _source_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "record.pdf"
    path.write_bytes(b"%PDF-1.4 test")
    return path


def _identity(name: str | None = "홍길동", school: str | None = "서울고등학교", birth6: str | None = "070101") -> dict:
    return {
        "name": {"value": name, "confidence": 1.0} if name is not None else {},
        "school_name": {"value": school, "confidence": 1.0} if school is not None else {},
        "birth6": {"value": birth6, "confidence": 1.0} if birth6 is not None else {},
        "class_no": {"value": "3", "confidence": 1.0},
        "student_no": {"value": "5", "confidence": 1.0},
    }


def _consensus(*, identity: dict, row_status: str = "confirmed", subject: str = "국어") -> dict:
    return {
        "identity": identity,
        "attendance": [],
        "grades": [
            {
                "_status": row_status,
                "_confidence": 1.0,
                "grade": 1,
                "semester": 1,
                "category": "국어",
                "subject": subject,
                "credits": 4,
                "raw_score": "90/70(10)",
                "achievement": "A",
                "students_count": 200,
                "rank_grade": "2",
            }
        ],
        "notes": [],
        "awards": [],
    }


def _save(tmp_path: Path, consensus: dict) -> tuple[Path, int]:
    from plugins.life_record.repository import save_import

    result = save_import(
        bundle_dir=tmp_path / "thread" / "life_records",
        pdf_path=_source_pdf(tmp_path),
        page_count=1,
        raw_text="raw",
        metadata={"test": True},
        consensus=consensus,
        extraction_method="test",
    )
    return Path(result["db_path"]), int(result["document_id"])


def test_verification_blocks_unknown_identity_even_when_rows_exist(tmp_path) -> None:
    from plugins.life_record.verifier import run_verification

    db_path, document_id = _save(tmp_path, _consensus(identity=_identity(name=None, school=None, birth6=None)))
    result = run_verification(db_path, document_id)

    assert result["status"] == "needs_review"
    identity_round = next(item for item in result["rounds"] if item["round"] == "identity")
    failed = {check["check"] for check in identity_round["failed_checks"]}
    assert {"student_name_identified", "school_identified", "identity_key_complete"} <= failed


def test_verification_blocks_pending_rows_until_human_review(tmp_path) -> None:
    from plugins.life_record.verifier import run_verification

    db_path, document_id = _save(tmp_path, _consensus(identity=_identity(), row_status="needs_review"))
    result = run_verification(db_path, document_id)

    assert result["status"] == "needs_review"
    readiness = next(item for item in result["rounds"] if item["round"] == "human_review_gate")
    assert readiness["failed_checks"][0]["check"] == "no_pending_review_rows"


def test_verification_flags_grade_artifacts(tmp_path) -> None:
    from plugins.life_record.verifier import run_verification

    db_path, document_id = _save(tmp_path, _consensus(identity=_identity(), subject="문서확인번호"))
    result = run_verification(db_path, document_id)

    artifact_round = next(item for item in result["rounds"] if item["round"] == "artifact_scan")
    assert result["status"] == "needs_review"
    assert artifact_round["failed_checks"][0]["check"] == "no_grade_artifacts"


def test_ingest_summary_does_not_call_unverified_import_confirmed() -> None:
    from plugins.life_record.service import format_ingest_summary

    text = format_ingest_summary(
        {
            "identity": {"name": "미상"},
            "counts": {"subject_grade_rows": 0, "special_note_rows": 0, "attendance_rows": 0, "award_rows": 0},
            "verification": {"status": "needs_review", "human_review_required": True, "failed_rounds": 2},
            "consensus_complete": False,
            "promoted": None,
        }
    )

    assert "검수 필요" in text
    assert "중앙 학생DB에 저장됨" not in text


def test_ingest_tool_exposes_hermes_style_backup_path(monkeypatch, tmp_path) -> None:
    from plugins.life_record import tools

    captured: dict = {}

    async def fake_ingest(*args, **kwargs):
        captured["kwargs"] = kwargs
        return {
            "db_path": str(tmp_path / "life_records.sqlite3"),
            "document_id": 7,
            "identity": {"name": "홍길동"},
            "stored_pdf_path": str(tmp_path / "stored.pdf"),
            "source_document_path": str(tmp_path / "source.pdf"),
            "stored_original_path": None,
            "converted_pdf_path": None,
            "photo_paths": [],
            "review_path": str(tmp_path / "review.html"),
            "counts": {"subject_grade_rows": 1, "needs_review_rows": 0},
            "verification": {"status": "pass"},
            "consensus_complete": True,
            "promoted": {"ok": True},
            "runs": 2,
            "backup_path": str(tmp_path / "backups" / "life_records_before_import.sqlite3"),
        }

    monkeypatch.setattr(tools, "ingest_life_record", fake_ingest)
    monkeypatch.setattr(tools, "current_life_record_dir", lambda: tmp_path / "life_records")

    result = tools._ingest_pdf_tool_handler({"pdf_path": str(_source_pdf(tmp_path))})

    assert '"backup_path"' in result
    assert "life_records_before_import.sqlite3" in result
