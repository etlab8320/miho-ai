from __future__ import annotations

import json

from plugins.academy_ops.hakjong_graduate_content import adapt_for_graduate


def test_adapt_for_graduate_removes_gap_plan_and_future_design_language() -> None:
    content = {
        "student": {"name": "장지용"},
        "university": {"name": "국민대", "department": "스포츠건강재활학과", "track": "학생부종합"},
        "badge": {"action": "학생부 근거 보완"},
        "cover": {
            "metrics": [{"label": "키워드", "value": "재활운동·기능평가"}],
            "key_judgment": {"body": "3학년 1학기 세특 설계가 필요하다."},
        },
        "track_section": {
            "rows": [
                {
                    "label": "최신 학과 흐름",
                    "official": "교수 논문/뉴스 근거: 근손상 예방·운동처방",
                }
            ],
        },
        "diagnosis_section": {"strength": {"body": "3학년 1학기에 세특을 보강한다."}},
        "strategy_section": {
            "actions": [{"title": "학생 기록 확장", "body": "세특을 운동생리 주제로 정리하여 보완한다."}],
            "gap_plan": {"title": "학교맞춤 세특 설계", "subjects": [{"field": "체육"}]},
            "final_judgment": {"body": "보완 후 검토"},
        },
    }

    adapted = adapt_for_graduate(content)
    strategy = adapted["strategy_section"]
    strategy_text = json.dumps(strategy, ensure_ascii=False)

    assert "gap_plan" not in strategy
    assert "완성 생기부 활용 전략" == strategy["heading"]
    assert "지원 가능성 판단" in strategy["final_judgment"]["body"]
    assert "면접 방어" in strategy["final_judgment"]["body"]
    assert "세특" not in strategy_text
    assert "3학년 1학기" not in strategy_text
