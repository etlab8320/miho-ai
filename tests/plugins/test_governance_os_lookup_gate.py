"""Fast-governance contracts for academy lookup tools."""

from __future__ import annotations

import json

from plugins.academy_ops.result_reviewer import review_tool_result
from plugins.governance_os.result_transform import governance_transform_tool_result


def test_susi_candidate_lookup_does_not_run_auxiliary_llm_review(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def broken_auxiliary_reviewer(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        raise AssertionError("candidate lookup must not run the auxiliary LLM reviewer")

    monkeypatch.setattr(
        "plugins.governance_os.review._call_auxiliary_reviewer",
        broken_auxiliary_reviewer,
    )
    raw = json.dumps(
        {
            "ok": True,
            "candidates": [
                {
                    "university": "테스트대학교",
                    "department": "스포츠과학과",
                    "admission_track": "수시 실기",
                    "max_possible_total": 1000,
                    "prev_final_total": 880,
                    "suggested_verdict": "적정",
                }
            ],
        },
        ensure_ascii=False,
    )
    reviewed = review_tool_result(
        tool_name="susi27_recommend_candidates",
        args={"student_query": "수민", "region": "수도권 우선, 충청, 강원"},
        result=raw,
    )

    transformed = governance_transform_tool_result(
        tool_name="susi27_recommend_candidates",
        result=reviewed,
        governance_skip_ledger=True,
    )

    assert transformed is None
    assert calls == []
