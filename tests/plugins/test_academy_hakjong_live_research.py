"""Tests for hakjong live research refresh policy."""

from __future__ import annotations

import json
from pathlib import Path

import plugins.academy_ops.hakjong_live_research as live


def _db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "susi27_student_record_qualitative.sqlite3"
    db_path.write_text("stub", encoding="utf-8")
    return db_path


def _existing_bundle() -> dict:
    searched_at = "2099-01-01T00:00:00+00:00"
    return {
        "searched_at": searched_at,
        "faculty_live_sources": [
            {
                "searched_at": searched_at,
                "results": [{"title": "기존 교수진", "snippet": "스포츠 체육 교수진", "source": "naver"}],
                "keywords": ["스포츠"],
            }
        ],
        "scholarly_sources": [
            {"searched_at": searched_at, "title": "기존 논문", "snippet": "운동역학 연구", "source": "openalex"}
        ],
        "paper_title_live_probe": [
            {"searched_at": searched_at, "hits_or_titles": ["기존 논문"], "usable_keywords": ["운동역학"]}
        ],
        "field_news_live_probe": [
            {"searched_at": searched_at, "title": "기존 뉴스", "snippet": "건강증진 뉴스", "source": "naver"}
        ],
    }


def test_live_research_refreshes_news_while_reusing_fresh_faculty_and_paper(monkeypatch, tmp_path) -> None:
    db_path = _db_path(tmp_path)
    calls: list[str] = []

    def fake_web(query: str, *, limit: int = 5):
        calls.append(query)
        assert "뉴스" in query
        return [{"title": "새 뉴스", "snippet": "스포츠 과학 최신 뉴스 건강증진", "url": "https://example.test", "source": "naver"}]

    monkeypatch.setattr(live, "search_web_snippets", fake_web)
    monkeypatch.setattr(live, "search_kci", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("paper cache expected")))
    monkeypatch.setattr(live, "search_openalex", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("paper cache expected")))
    monkeypatch.setattr(live, "search_crossref", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("paper cache expected")))

    bundle = live.write_live_research_bundle(
        db_path,
        university="국민대학교",
        department="스포츠건강재활학과",
        admission_track="국민프런티어",
        existing=_existing_bundle(),
    )

    assert bundle is not None
    assert calls == ["국민대학교 스포츠건강재활학과 뉴스 최신 스포츠 과학"]
    assert bundle["refresh_status"] == {
        "faculty": "cache_fresh",
        "paper": "cache_fresh",
        "news": "live_refreshed",
    }
    assert bundle["faculty_live_sources"][0]["results"][0]["title"] == "기존 교수진"
    assert bundle["scholarly_sources"][0]["title"] == "기존 논문"
    assert bundle["field_news_live_probe"][0]["title"] == "새 뉴스"
    assert Path(bundle["bundle_path"]).is_file()


def test_live_research_falls_back_to_cached_news_when_live_search_fails(monkeypatch, tmp_path) -> None:
    db_path = _db_path(tmp_path)

    monkeypatch.setattr(
        live,
        "search_web_snippets",
        lambda *args, **kwargs: [{"title": "검색 실패", "snippet": "blocked", "url": "https://example.test", "source": "naver"}],
    )
    monkeypatch.setattr(live, "search_kci", lambda *args, **kwargs: [])
    monkeypatch.setattr(live, "search_openalex", lambda *args, **kwargs: [])
    monkeypatch.setattr(live, "search_crossref", lambda *args, **kwargs: [])

    bundle = live.write_live_research_bundle(
        db_path,
        university="국민대학교",
        department="스포츠건강재활학과",
        admission_track="국민프런티어",
        existing=_existing_bundle(),
    )

    assert bundle is not None
    assert bundle["refresh_status"]["news"] == "cache_fallback_after_live_failure"
    assert bundle["field_news_live_probe"][0]["title"] == "기존 뉴스"
    saved = json.loads(Path(bundle["bundle_path"]).read_text(encoding="utf-8"))
    assert saved["field_news_live_probe"][0]["title"] == "기존 뉴스"
