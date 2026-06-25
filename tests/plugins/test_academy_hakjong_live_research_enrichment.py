from __future__ import annotations

import json

from plugins.academy_ops import hakjong_live_research as live


def test_live_research_enrichment_updates_existing_flow_row_with_paper_title() -> None:
    content = {
        "track_section": {
            "rows": [{"label": "최신 학과 흐름", "official": "교수 논문/뉴스 근거: 공식 자료", "judgment": "기존"}],
            "strong_points": {"bullets": []},
        },
        "strategy_section": {"actions": [{"body": "학생부 보완"}], "interview_rows": []},
    }
    profile = {
        "live_research": {
            "faculty_paper_sources": [
                {
                    "title": "엘리트 보디빌딩 선수들의 경기력 향상보조제 복용 실태조사",
                    "snippet": "스포츠과학 보디빌딩 경기력",
                }
            ],
            "paper_title_live_probe": [{"usable_keywords": ["스포츠과학"]}],
            "field_news_live_probe": [{"keywords": ["스포츠과학"]}],
        }
    }

    applied = live.apply_live_research_enrichment(content, profile)
    visible = json.dumps(content, ensure_ascii=False)

    assert applied is True
    assert "교수 연구 제목: 엘리트 보디빌딩 선수들의 경기력 향상보조제" in visible
    assert "공식 자료" not in visible


def test_live_research_enrichment_omits_interview_copy_when_no_interview() -> None:
    content = {
        "track_section": {"rows": [], "strong_points": {"bullets": []}},
        "strategy_section": {
            "actions": [{"body": "학생부 보완"}],
            "interview_rows": [],
            "final_judgment": {"body": "최종 판단"},
        },
    }
    profile = {"live_research": {"paper_title_live_probe": [{"usable_keywords": ["스포츠과학", "보디빌딩"]}]}}

    live.apply_live_research_enrichment(content, profile)
    body = content["strategy_section"]["final_judgment"]["body"]

    assert "면접 답변" not in body
    assert "세특 보완 문장" in body


def test_live_research_enrichment_uses_completed_record_copy_for_graduate() -> None:
    content = {
        "track_section": {"rows": [], "strong_points": {"bullets": []}},
        "strategy_section": {
            "heading": "완성 생기부 활용 전략",
            "actions": [{"body": "최종 점검"}],
            "interview_rows": [{"question": "지원 동기", "point": "기록 근거"}],
            "final_judgment": {"body": "완성 생기부 기록 근거로 판단"},
        },
    }
    profile = {"live_research": {"paper_title_live_probe": [{"usable_keywords": ["재활운동", "기능평가"]}]}}

    live.apply_live_research_enrichment(content, profile)
    strategy_text = json.dumps(content["strategy_section"], ensure_ascii=False)

    assert "학생부 보완 문장" not in strategy_text
    assert "세특·면접 답변" not in strategy_text
    assert "서류 해석 문장" in strategy_text
    assert "면접 답변" in strategy_text


def test_live_research_keywords_drop_sentence_fragments() -> None:
    bundle = {
        "paper_title_live_probe": [{"usable_keywords": ["스포츠과학", "할 수 있고"]}],
        "field_news_live_probe": [{"keywords": ["운동생리학"]}],
    }

    keywords = live.live_research_keywords(bundle)

    assert "할 수 있고" not in keywords
    assert keywords == ["스포츠과학", "운동생리학"]
