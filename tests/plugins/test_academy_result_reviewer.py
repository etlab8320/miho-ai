"""Tests for the academy result reviewer hook."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

from plugins.academy_ops.result_reviewer import (
    block_academy_handrolled_outputs,
    review_tool_result,
)


class _FakeReviewerLlm:
    def __init__(self, parsed: dict) -> None:
        self.parsed = parsed
        self.calls: list[dict] = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed=self.parsed)


def _pass_review() -> dict:
    return {
        "status": "pass",
        "errors": [],
        "warnings": [],
        "checked": ["내용", "근거", "요청 의도"],
        "retry_instructions": "",
    }


def test_blocks_handrolled_practical_pdf_generation() -> None:
    blocked = block_academy_handrolled_outputs(
        tool_name="execute_code",
        args={"code": "make a pdf for 서연 실기전형 추천 리포트 without using tools"},
    )

    assert blocked and blocked["action"] == "block"
    assert "academy_practical_reco_package" in blocked["message"]


def test_allows_dedicated_academy_report_tool() -> None:
    assert (
        block_academy_handrolled_outputs(
            tool_name="academy_practical_reco_package",
            args={"student_name": "서연"},
        )
        is None
    )


def test_practical_review_blocks_missing_single_pipeline_evidence(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    manifest = tmp_path / "report.practical_reco_validation.json"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    manifest.write_text(
        json.dumps(
            {
                "ok": True,
                "pdf_path": str(pdf),
                "student_name": "서연",
                "school_names": ["한국체육대학교"],
                "evidence_tools": ["susi27_score_calculate"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw = json.dumps(
        {
            "ok": True,
            "file_path": str(pdf),
            "manifest_path": str(manifest),
            "media_tag": f"MEDIA:{pdf}",
        },
        ensure_ascii=False,
    )

    reviewed = json.loads(
        review_tool_result(
            tool_name="academy_practical_reco_package",
            args={},
            result=raw,
        )
    )

    assert reviewed["ok"] is False
    assert reviewed["reviewer"]["status"] == "blocked"
    assert "susi27_recommend_candidates" in " ".join(reviewed["errors"])


def test_hakjong_review_passes_canonical_manifest(tmp_path: Path) -> None:
    pdf = tmp_path / "hakjong.pdf"
    html = tmp_path / "hakjong.html"
    manifest = tmp_path / "hakjong.hakjong_validation.json"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    html.write_text("<html></html>", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "ok": True,
                "manifest_version": 2,
                "generator": "academy_hakjong_report_package",
                "pdf_path": str(pdf),
                "html_path": str(html),
                "student_name": "홍길동",
                "university_names": ["성균관대학교"],
                "student_stage": "grade3",
                "checks": {
                    "schema": {
                        "evidence_tools": ["life_record_lookup"],
                        "visible_text_chars": 1700,
                    },
                    "pdf": {"pages": 4, "printed_text_chars": 1600},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw = json.dumps(
        {
            "ok": True,
            "file_path": str(pdf),
            "manifest_path": str(manifest),
            "media_tag": f"MEDIA:{pdf}",
            "checks": {"pdf": {"pages": 4}},
        },
        ensure_ascii=False,
    )

    reviewed = json.loads(
        review_tool_result(
            tool_name="academy_hakjong_report_package",
            args={},
            result=raw,
            llm=_FakeReviewerLlm(_pass_review()),
        )
    )

    assert reviewed["ok"] is True
    assert reviewed["reviewer"]["status"] == "pass"
    assert reviewed["reviewer"]["mode"] == "llm_subagent"


def test_hakjong_review_records_governance_outcome(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants
    from agent import evolution

    importlib.reload(miho_constants)
    importlib.reload(evolution)

    pdf = tmp_path / "hakjong.pdf"
    html = tmp_path / "hakjong.html"
    manifest = tmp_path / "hakjong.hakjong_validation.json"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    html.write_text("<html></html>", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "ok": True,
                "manifest_version": 2,
                "generator": "academy_hakjong_report_package",
                "pdf_path": str(pdf),
                "html_path": str(html),
                "student_name": "홍길동",
                "university_names": ["성균관대학교"],
                "student_stage": "grade3",
                "checks": {
                    "schema": {
                        "evidence_tools": ["life_record_lookup"],
                        "visible_text_chars": 1700,
                    },
                    "pdf": {"pages": 4, "printed_text_chars": 1600},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw = json.dumps(
        {
            "ok": True,
            "file_path": str(pdf),
            "manifest_path": str(manifest),
            "media_tag": f"MEDIA:{pdf}",
        },
        ensure_ascii=False,
    )

    review_tool_result(
        tool_name="academy_hakjong_report_package",
        args={},
        result=raw,
        llm=_FakeReviewerLlm(_pass_review()),
    )

    event = evolution.list_events(limit=1)[0]
    outcome = event["metadata"]["governance_outcome"]
    assert event["kind"] == "note"
    assert outcome["playbook_key"] == "academy_hakjong_report"
    assert outcome["tools_used"] == ["academy_hakjong_report_package"]
    assert outcome["review_status"] == "pass"
    assert outcome["artifact_paths"] == [str(pdf), str(manifest)]


def test_hakjong_review_blocks_when_subagent_fails(tmp_path: Path) -> None:
    pdf = tmp_path / "hakjong.pdf"
    html = tmp_path / "hakjong.html"
    manifest = tmp_path / "hakjong.hakjong_validation.json"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    html.write_text("<html></html>", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "ok": True,
                "manifest_version": 2,
                "generator": "academy_hakjong_report_package",
                "pdf_path": str(pdf),
                "html_path": str(html),
                "student_name": "홍길동",
                "university_names": ["성균관대학교"],
                "student_stage": "grade3",
                "checks": {
                    "schema": {
                        "evidence_tools": ["life_record_lookup"],
                        "visible_text_chars": 1700,
                    },
                    "pdf": {"pages": 4, "printed_text_chars": 1600},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw = json.dumps(
        {
            "ok": True,
            "file_path": str(pdf),
            "manifest_path": str(manifest),
            "media_tag": f"MEDIA:{pdf}",
        },
        ensure_ascii=False,
    )
    llm = _FakeReviewerLlm(
        {
            "status": "fail",
            "errors": ["PDF 2페이지 하단에서 문장이 겹쳐 보인다."],
            "warnings": [],
            "checked": ["PDF 이미지", "레이아웃"],
            "retry_instructions": "내용을 줄이고 같은 도구를 다시 호출해라.",
        }
    )

    reviewed = json.loads(
        review_tool_result(
            tool_name="academy_hakjong_report_package",
            args={},
            result=raw,
            llm=llm,
        )
    )

    assert reviewed["ok"] is False
    assert reviewed["reviewer"]["stage"] == "llm_subagent"
    assert "문장이 겹쳐" in " ".join(reviewed["errors"])


def test_susi_review_blocks_unreachable_candidate() -> None:
    raw = json.dumps(
        {
            "student": "서연",
            "region_filter": "전국",
            "candidates": [
                {
                    "university": "불가대",
                    "department": "체육교육과",
                    "admission_track": "실기",
                    "student_record_score": 100.0,
                    "max_possible_total": 300.0,
                    "prev_final_total": 350.0,
                    "suggested_verdict": "상향",
                }
            ],
        },
        ensure_ascii=False,
    )

    reviewed = json.loads(
        review_tool_result(
            tool_name="susi27_recommend_candidates",
            args={"student_query": "서연", "region": "전국"},
            result=raw,
        )
    )

    assert reviewed["ok"] is False
    assert reviewed["reviewer"]["status"] == "blocked"
    assert "만점 합산" in " ".join(reviewed["errors"])


def test_susi_recommend_candidates_uses_fast_contract_gate_without_llm() -> None:
    llm = _FakeReviewerLlm(
        {
            "status": "fail",
            "errors": ["candidate lookup should not call the LLM reviewer"],
            "warnings": [],
            "checked": [],
            "retry_instructions": "do not retry",
        }
    )
    raw = json.dumps(
        {
            "ok": True,
            "candidates": [
                {
                    "university": "테스트대학교",
                    "department": "체육교육과",
                    "admission_track": "수시 실기",
                    "max_possible_total": 1000,
                    "prev_final_total": 860,
                    "suggested_verdict": "적정",
                }
            ],
        },
        ensure_ascii=False,
    )

    reviewed = json.loads(
        review_tool_result(
            tool_name="susi27_recommend_candidates",
            args={"student_query": "수민", "region": "수도권 우선, 충청, 강원"},
            result=raw,
            llm=llm,
        )
    )

    assert llm.calls == []
    assert reviewed["ok"] is True
    assert reviewed["reviewer"]["status"] == "pass"
    assert reviewed["reviewer"]["mode"] == "deterministic_gate"


def test_life_record_review_marks_human_review_without_blocking() -> None:
    raw = json.dumps(
        {
            "ok": True,
            "operation": "life_record.ingest_pdf",
            "verification": {
                "status": "needs_review",
                "human_review_required": True,
            },
            "review_path": "/tmp/review.html",
        },
        ensure_ascii=False,
    )

    reviewed = json.loads(
        review_tool_result(
            tool_name="life_record_ingest_pdf",
            args={},
            result=raw,
        )
    )

    assert reviewed["ok"] is True
    assert reviewed["reviewer"]["status"] == "needs_human_review"
    assert "확정 표현 금지" in reviewed["assistant_guidance"]
