"""Tests for PE-brain evidence packs used by sports performance tools."""

from __future__ import annotations

import json
from typing import Any

from plugins.sports_performance import pe_brain_evidence
from plugins.sports_performance.feedback_tool import feedback_tool_handler
from plugins.sports_performance.pe_brain_evidence import build_evidence_packs
from plugins.sports_performance.result_reviewer import review_tool_result


def _sample_papers() -> list[dict[str, Any]]:
    return [
        {
            "id": 21,
            "title": "Criterion validity and reliability of standing long jump test",
            "category": "physical",
            "status": "completed",
            "chunk_count": 46,
            "summary": "제자리멀리뛰기(SLJ)는 하체 폭발적 근력과 수평 파워를 평가하는 데 유효한 테스트다.",
            "created_at": "2026-02-04T13:21:57.241257",
        },
        {
            "id": 59,
            "title": "SN Comprehensive Clinical Medicine",
            "category": "mental",
            "status": "completed",
            "chunk_count": 22,
            "summary": "이 논문은 COVID-19에 감염된 임산부의 간 효소 수치와 출산 결과를 조사했다.",
            "created_at": "2026-05-01T00:00:00",
        },
        {
            "id": 88,
            "title": "Generic athlete training and performance review",
            "category": "physical",
            "status": "completed",
            "chunk_count": 12,
            "summary": "이 논문은 athlete training performance를 넓게 언급하지만 종목별 세부 측정 과제가 없다.",
            "created_at": "2026-05-02T00:00:00",
        },
    ]


def test_pe_brain_evidence_packs_accept_domain_papers_and_reject_off_domain() -> None:
    packs = build_evidence_packs(_sample_papers())

    accepted = next(pack for pack in packs if pack["id"] == "pe_brain:21")
    rejected = next(pack for pack in packs if pack["id"] == "pe_brain:59")
    generic = next(pack for pack in packs if pack["id"] == "pe_brain:88")

    assert accepted["quality_status"] == "accepted"
    assert accepted["evidence_depth"] == "summary_only"
    assert "standing_long_jump" in accepted["exercise_keys"]
    assert accepted["source"] == "pe_brain"

    assert rejected["quality_status"] == "rejected"
    assert any("오프도메인" in reason for reason in rejected["quality_reasons"])
    assert generic["quality_status"] == "review_required"
    assert any("종목별 운동 태그" in reason for reason in generic["quality_reasons"])


def test_pe_brain_evidence_tool_searches_accepted_packs_by_exercise(monkeypatch) -> None:
    monkeypatch.setattr(pe_brain_evidence, "_fetch_pe_brain_papers", lambda *_args, **_kwargs: _sample_papers())

    result = json.loads(pe_brain_evidence.pe_brain_evidence_tool_handler({"exercise": "제멀"}))

    assert result["ok"] is True
    assert result["action"] == "search"
    assert result["packs"][0]["id"] == "pe_brain:21"
    assert result["packs"][0]["quality_status"] == "accepted"
    assert result["rag_policy"]["current_mode"] == "evidence_pack_first"


def test_motion_feedback_links_only_accepted_pe_brain_evidence(monkeypatch) -> None:
    packs = build_evidence_packs(_sample_papers())
    monkeypatch.setattr(
        "plugins.sports_performance.pe_brain_evidence.load_pe_brain_evidence_packs",
        lambda: packs,
    )

    result = json.loads(
        feedback_tool_handler(
            {
                "student_name": "홍예지",
                "exercise": "제멀",
                "metrics": {"발사각": 22, "무릎각도": 126},
                "evidence_refs": ["pe_brain:21"],
            }
        )
    )

    assert result["evidence_status"] == "source_pack_linked"
    assert result["evidence_validation"]["accepted_refs"] == ["pe_brain:21"]
    assert result["evidence_packs"][0]["id"] == "pe_brain:21"


def test_reviewer_keeps_result_when_pe_brain_ref_is_rejected(monkeypatch) -> None:
    packs = build_evidence_packs(_sample_papers())
    monkeypatch.setattr(
        "plugins.sports_performance.pe_brain_evidence.load_pe_brain_evidence_packs",
        lambda: packs,
    )
    raw = feedback_tool_handler(
        {
            "student_name": "홍예지",
            "exercise": "제멀",
            "metrics": {"발사각": 22, "무릎각도": 126},
            "evidence_refs": ["pe_brain:59"],
        }
    )

    result = json.loads(raw)
    blocked = json.loads(review_tool_result(tool_name="sports_motion_feedback", args={}, result=raw) or raw)

    assert result["ok"] is True
    assert result["evidence_status"] == "pending_source_pack"
    assert result["evidence_refs"] == []
    assert result["evidence_validation"]["invalid_refs"][0]["ref"] == "pe_brain:59"
    assert blocked["ok"] is True
    assert blocked["reviewer"]["status"] == "retry_needed"
    assert blocked["reviewer"]["retry_tools"] == ["sports_pe_brain_evidence", "sports_motion_feedback"]
    assert blocked["next_action"] == "retry_required"
    assert blocked["delivery_status"] == "provisional"


def test_motion_feedback_does_not_link_unmanaged_external_refs(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.sports_performance.pe_brain_evidence.load_pe_brain_evidence_packs",
        lambda: build_evidence_packs(_sample_papers()),
    )

    result = json.loads(
        feedback_tool_handler(
            {
                "student_name": "홍예지",
                "exercise": "제멀",
                "metrics": {"발사각": 22, "무릎각도": 126},
                "evidence_refs": ["manual:anything"],
            }
        )
    )

    assert result["evidence_status"] == "pending_source_pack"
    assert result["evidence_refs"] == []
    assert "외부 근거" in result["evidence_validation"]["invalid_refs"][0]["reason"]


def test_pe_brain_ref_must_match_exercise_tag(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.sports_performance.pe_brain_evidence.load_pe_brain_evidence_packs",
        lambda: build_evidence_packs(_sample_papers()),
    )

    result = json.loads(
        feedback_tool_handler(
            {
                "student_name": "홍예지",
                "exercise": "왕복달리기",
                "metrics": {"turn_angle": 68, "contact_time": 0.42},
                "evidence_refs": ["pe_brain:21"],
            }
        )
    )

    assert result["evidence_status"] == "pending_source_pack"
    assert result["evidence_validation"]["invalid_refs"][0]["ref"] == "pe_brain:21"


def test_pe_brain_sync_failure_reports_cache_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    monkeypatch.setattr(pe_brain_evidence, "_fetch_pe_brain_papers", lambda *_args, **_kwargs: _sample_papers())
    pe_brain_evidence.pe_brain_evidence_tool_handler({"action": "sync"})

    def _raise_fetch(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise OSError("offline")

    monkeypatch.setattr(pe_brain_evidence, "_fetch_pe_brain_papers", _raise_fetch)

    result = json.loads(pe_brain_evidence.pe_brain_evidence_tool_handler({"action": "sync"}))

    assert result["ok"] is True
    assert result["source_info"]["status"] == "fallback_cache"
    assert result["source_info"]["source_error"] == "OSError"
    assert any("동기화" in warning for warning in result["warnings"])
