from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "audit_susi27_pixel_formula_ocr.py"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("audit_susi27_pixel_formula_ocr", SCRIPT_PATH)
assert SPEC and SPEC.loader
pixel_audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pixel_audit
SPEC.loader.exec_module(pixel_audit)


def _row(pdf_rel: str = "source_files/pdfs_official/테스트대학교/2027_테스트대학교_수시모집요강.pdf") -> dict[str, str]:
    score = {
        "stage_weights": {"student_record": "40", "practical": "60"},
        "stage_scores": {"student_record": "400", "practical": "600"},
        "grade_points": {"1": "100", "2": "90", "3": "80"},
    }
    events = {
        "practical_full_score": "600",
        "events": [{"name": "제자리멀리뛰기"}, {"name": "10m왕복달리기"}],
    }
    return {
        "university_id": "1",
        "university": "테스트대학교",
        "department": "체육학과",
        "admission_track": "실기우수자",
        "quota": "12",
        "pdf_rel_path": pdf_rel,
        "score_logic_json": json.dumps(score, ensure_ascii=False),
        "practical_events_json": json.dumps(events, ensure_ascii=False),
        "admission_meta_json": json.dumps({"stage2": {"student_record": "40", "practical": "60"}}, ensure_ascii=False),
        "school_info_json": "{}",
    }


def test_pixel_audit_passes_when_pixel_ocr_contains_all_formula_values(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime" / "susi27_pipeline"
    pdf_rel = _row()["pdf_rel_path"]
    pdf_path = runtime / pdf_rel
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4 test")
    manifest = {pixel_audit._manifest_key(pdf_rel): hashlib.sha256(pdf_path.read_bytes()).hexdigest()}
    pixel_text = (
        "2027학년도 수시모집요강 테스트대학교 체육학과 12 실기우수자 "
        "학생부 40 실기 60 학생부교과 400 실기고사 600 "
        "1등급 100 2등급 90 3등급 80 제자리멀리뛰기 10m왕복달리기"
    )
    monkeypatch.setattr(pixel_audit, "_pdf_text_pages", lambda _: {3: "체육학과 실기우수자 전형방법"})
    monkeypatch.setattr(pixel_audit, "_ocr_page", lambda *_: pixel_text)

    result = pixel_audit.audit_row(_row(), runtime, manifest, {}, "apple_vision", 3, False)

    assert result["status"] == "pixel_pass"
    assert result["candidate_pages"] == [3]


def test_pixel_audit_keeps_number_boundary_failures_in_review(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime" / "susi27_pipeline"
    pdf_rel = _row()["pdf_rel_path"]
    pdf_path = runtime / pdf_rel
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4 test")
    manifest = {pixel_audit._manifest_key(pdf_rel): hashlib.sha256(pdf_path.read_bytes()).hexdigest()}
    monkeypatch.setattr(pixel_audit, "_pdf_text_pages", lambda _: {1: "체육학과 실기우수자"})
    monkeypatch.setattr(pixel_audit, "_ocr_page", lambda *_: "체육학과 실기우수자 실기 600 학생부 400")

    result = pixel_audit.audit_row(_row(), runtime, manifest, {}, "apple_vision", 3, False)

    assert result["status"] == "pixel_needs_review"
    assert "pixel_stage_weights:missing" in result["needs_review"]


def test_candidate_pages_prioritize_department_and_practical_tokens() -> None:
    pages = {
        1: "표지 수시모집요강",
        2: "경제학과 학생부 40 실기 60",
        3: "체육학과 실기우수자 제자리멀리뛰기 10m왕복달리기",
    }
    expectations = pixel_audit._expectations(
        _row(),
        json.loads(_row()["score_logic_json"]),
        json.loads(_row()["practical_events_json"]),
        json.loads(_row()["admission_meta_json"]),
    )

    assert pixel_audit._candidate_pages(_row(), expectations, pages, 2)[0] == 3


def test_pixel_number_match_accepts_ocr_commas_without_substring_false_positive() -> None:
    assert pixel_audit._pixel_number_found("환산점수 1,000 등급", "1000") is True
    assert pixel_audit._pixel_number_found("환산점수 10,000 등급", "1000") is False


def test_pixel_audit_scans_available_pages_when_text_layer_has_no_candidates(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime" / "susi27_pipeline"
    pdf_rel = _row()["pdf_rel_path"]
    pdf_path = runtime / pdf_rel
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4 scan")
    manifest = {pixel_audit._manifest_key(pdf_rel): hashlib.sha256(pdf_path.read_bytes()).hexdigest()}
    pixel_pages = {
        1: "표지",
        2: (
            "테스트대학교 체육학과 12 실기우수자 학생부 40 실기 60 "
            "학생부교과 400 실기고사 600 1등급 100 2등급 90 3등급 80 "
            "제자리멀리뛰기 10m왕복달리기"
        ),
    }
    monkeypatch.setattr(pixel_audit, "_pdf_text_pages", lambda _: {1: "", 2: ""})
    monkeypatch.setattr(pixel_audit, "_ocr_page", lambda _pdf, number, *_: pixel_pages[number])

    result = pixel_audit.audit_row(_row(), runtime, manifest, {}, "apple_vision", 3, False)

    assert result["status"] == "pixel_pass"
    assert result["candidate_pages"] == [2]


def test_pixel_audit_caps_fallback_ocr_pages_before_scoring(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime" / "susi27_pipeline"
    pdf_rel = _row()["pdf_rel_path"]
    pdf_path = runtime / pdf_rel
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4 scan")
    manifest = {pixel_audit._manifest_key(pdf_rel): hashlib.sha256(pdf_path.read_bytes()).hexdigest()}
    text_pages = {number: "" for number in range(1, 7)}
    pixel_pages = {
        1: "표지",
        2: "목차",
        3: (
            "테스트대학교 체육학과 12 실기우수자 학생부 40 실기 60 "
            "학생부교과 400 실기고사 600 1등급 100 2등급 90 3등급 80 "
            "제자리멀리뛰기 10m왕복달리기"
        ),
        4: "이 페이지는 max_pages 상한 밖이다",
        5: "이 페이지도 읽으면 안 된다",
        6: "이 페이지도 읽으면 안 된다",
    }
    seen_pages: list[int] = []
    monkeypatch.setattr(pixel_audit, "_pdf_text_pages", lambda _: text_pages)

    def _fake_ocr_page(_pdf: Path, number: int, *_args: object) -> str:
        seen_pages.append(number)
        return pixel_pages[number]

    monkeypatch.setattr(pixel_audit, "_ocr_page", _fake_ocr_page)

    result = pixel_audit.audit_row(_row(), runtime, manifest, {}, "apple_vision", 3, False)

    assert result["status"] == "pixel_pass"
    assert result["candidate_pages"] == [3]
    assert seen_pages == [1, 2, 3]
