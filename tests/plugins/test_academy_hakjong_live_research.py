"""Tests for hakjong live research refresh policy."""

from __future__ import annotations

import json
from pathlib import Path

import plugins.academy_ops.hakjong_live_research as live
from plugins.academy_ops.hakjong_faculty_research import (
    build_faculty_research,
    extract_faculty_profiles,
    read_page_text,
    recover_existing_faculty_research,
)


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
        "faculty_paper_sources": [
            {"searched_at": searched_at, "title": "기존 교수 논문", "snippet": "운동역학 연구", "source": "openalex"}
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


def test_latest_live_research_bundle_prefers_usable_faculty_cache(tmp_path) -> None:
    bundle_dir = tmp_path / "school_specific_source_bundles"
    bundle_dir.mkdir()
    good = bundle_dir / "국민대학교_스포츠건강재활학과_국민프런티어_live_research_auto_1.json"
    empty = bundle_dir / "국민대학교_스포츠건강재활학과_국민프런티어_live_research_auto_2.json"
    good.write_text(json.dumps({"faculty_profiles": [{"name": "이기광", "major": "운동역학"}]}), encoding="utf-8")
    empty.write_text(json.dumps({"faculty_profiles": [], "faculty_paper_sources": []}), encoding="utf-8")
    selected = live.latest_live_research_bundle(
        tmp_path / "susi27_student_record_qualitative.sqlite3",
        university="국민대학교",
        department="스포츠건강재활학과",
        admission_track="국민프런티어",
    )
    assert selected is not None
    assert selected["faculty_profiles"][0]["name"] == "이기광"
    assert selected["bundle_path"].endswith("_1.json")


def test_latest_live_research_bundle_ignores_noisy_faculty_cache(tmp_path) -> None:
    bundle_dir = tmp_path / "school_specific_source_bundles"
    bundle_dir.mkdir()
    noisy = bundle_dir / "경희대학교_스포츠의학과_기회균형I_live_research_auto_1.json"
    empty = bundle_dir / "경희대학교_스포츠의학과_기회균형I_live_research_auto_2.json"
    noisy.write_text(json.dumps({"faculty_profiles": [{"name": "인사말", "major": "소개"}]}), encoding="utf-8")
    empty.write_text(json.dumps({"faculty_profiles": [], "faculty_paper_sources": []}), encoding="utf-8")
    selected = live.latest_live_research_bundle(
        tmp_path / "susi27_student_record_qualitative.sqlite3",
        university="경희대학교",
        department="스포츠의학과",
        admission_track="기회균형I",
    )
    assert selected is not None
    assert selected["faculty_profiles"] == []
    assert selected["bundle_path"].endswith("_2.json")


def test_latest_live_research_bundle_sanitizes_mixed_faculty_cache(tmp_path) -> None:
    bundle_dir = tmp_path / "school_specific_source_bundles"
    bundle_dir.mkdir()
    mixed = bundle_dir / "경희대학교_스포츠의학과_기회균형I_live_research_auto_1.json"
    mixed.write_text(
        json.dumps({
            "faculty_profiles": [
                {"name": "인사말", "major": "소개"},
                {"name": "박지홍", "major": "스포츠의학"},
            ]
        }),
        encoding="utf-8",
    )
    selected = live.latest_live_research_bundle(
        tmp_path / "susi27_student_record_qualitative.sqlite3",
        university="경희대학교",
        department="스포츠의학과",
        admission_track="기회균형I",
    )
    assert selected is not None
    assert selected["faculty_profiles"] == [{"name": "박지홍", "major": "스포츠의학"}]


def test_latest_live_research_bundle_drops_wrong_university_source_cache(tmp_path) -> None:
    bundle_dir = tmp_path / "school_specific_source_bundles"
    bundle_dir.mkdir()
    wrong = bundle_dir / "서울과학기술대학교_스포츠과학과_농어촌학생_live_research_auto_1.json"
    wrong.write_text(
        json.dumps({
            "faculty_source_pages": [{"url": "https://sports.snu.ac.kr/prof"}],
            "faculty_profiles": [{"name": "강준호", "major": "스포츠경영학"}],
            "faculty_paper_sources": [{"title": "The Effects of Psychological Skills Training on Golf Performance"}],
        }),
        encoding="utf-8",
    )
    selected = live.latest_live_research_bundle(
        tmp_path / "susi27_student_record_qualitative.sqlite3",
        university="서울과학기술대학교",
        department="스포츠과학과",
        admission_track="농어촌학생",
    )
    assert selected is not None
    assert selected["faculty_profiles"] == []
    assert selected["faculty_paper_sources"] == []


def test_sports_science_department_adds_second_live_keyword() -> None:
    keywords = live.keywords_from_text("스포츠 연구", department="스포츠과학과")

    assert "스포츠" in keywords
    assert "스포츠과학" in keywords


def test_live_research_enrichment_hides_search_page_chrome() -> None:
    content = {
        "track_section": {"rows": [], "strong_points": {"bullets": []}},
        "strategy_section": {"actions": [{"body": "학생부 보완"}], "interview_rows": []},
    }
    profile = {
        "live_research": {
            "paper_title_live_probe": [{"usable_keywords": ["스포츠과학"]}],
            "field_news_live_probe": [
                {
                    "title": "국민대학교 스포츠건강재활학과 뉴스 최신 스포츠 과학 : 네이버 검색 메뉴 영역",
                    "keywords": ["운동처방", "Year", "검색옵션"],
                }
            ],
        }
    }

    applied = live.apply_live_research_enrichment(content, profile)
    visible = json.dumps(content, ensure_ascii=False)

    assert applied is True
    assert "교수 연구 제목: 교수진·논문·뉴스 키워드: 스포츠과학·운동처방" in visible
    assert "Year" not in visible
    assert "검색옵션" not in visible
    assert "네이버 검색 메뉴" not in visible
    assert "본문 영역" not in visible
    assert "지식iN" not in visible
    assert content["strategy_section"]["interview_rows"] == []


def test_faculty_profiles_extract_names_and_majors() -> None:
    text = """
    이대택
    Lee, DaeTaek
    * 소속 스포츠건강재활학과
    * 전공 운동 생리학
    * 이메일 dtlee@kookmin.ac.kr
    이기광
    Lee, KiKwang
    * 소속 스포츠건강재활학과
    * 전공 운동역학
    * 이메일 kklee@kookmin.ac.kr
    """

    profiles = extract_faculty_profiles(text, department="스포츠건강재활학과")

    assert profiles[0]["name"] == "이대택"
    assert profiles[0]["major"] == "운동 생리학"
    assert "Dae Taek Lee" in profiles[0]["english_variants"]
    assert profiles[1]["name"] == "이기광"
    assert profiles[1]["major"] == "운동역학"


def test_faculty_profiles_extract_markdown_without_space() -> None:
    text = """
    ## 강준호 교수
    **전공**스포츠경영학
    **이메일**kangjh@snu.ac.kr
    ## 권성호 교수
    **전공**스포츠심리학
    """

    profiles = extract_faculty_profiles(text, department="체육교육과")

    assert profiles[0]["name"] == "강준호"
    assert profiles[0]["major"] == "스포츠경영학"
    assert profiles[1]["name"] == "권성호"


def test_faculty_profiles_extract_list_and_table_layouts() -> None:
    text = """
    * 교수 스포츠마케팅
    * 장경로
    * kchang@skku.edu
    [관심분야]
    스포츠산업에서의 고객만족
    교수 | 박정준 | 상세보기 | 직책/직급 | 교수 | 주전공 | 스포츠교육학(스포츠인성교육) | 담당과목
    """

    profiles = extract_faculty_profiles(text, department="스포츠과학과")

    assert profiles[0]["name"] == "박정준"
    assert profiles[0]["major"] == "스포츠교육학(스포츠인성교육)"
    assert profiles[1]["name"] == "장경로"
    assert profiles[1]["major"] == "스포츠마케팅"


def test_read_page_text_follows_faculty_iframe(monkeypatch) -> None:
    calls: list[str] = []

    def fake_open(url: str, *, timeout: int = 8) -> str:
        calls.append(url)
        if "r.jina.ai/https://outer.test" in url:
            return ""
        if url == "https://outer.test/professor":
            return '<iframe src="https://m.hanyang.ac.kr/v3/staf001001.page?sosok_cd=H0004700"></iframe>'
        if "r.jina.ai/https://m.hanyang.ac.kr/v3/staf001001.page" in url:
            return "#### 박성배 교수 / 전임교원\n* **연구분야**스포츠산업학"
        raise AssertionError(url)

    monkeypatch.setattr("plugins.academy_ops.hakjong_faculty_research.open_url", fake_open)
    text = read_page_text("https://outer.test/professor")
    assert "박성배 교수" in text
    assert any("m.hanyang.ac.kr" in call for call in calls)


def test_faculty_profiles_use_research_field_not_major_inside_department_name() -> None:
    text = """
    #### 박성배 교수 / 전임교원
    * **소속**스포츠산업과학부 스포츠매니지먼트전공
    * **보직**스포츠매니지먼트전공주임
    * **연구분야**스포츠산업학
    #### 이종성 부교수 / 전임교원
    * **연구분야**스포츠 문화사
    """
    profiles = extract_faculty_profiles(text, department="스포츠매니지먼트")
    assert profiles[0]["name"] == "박성배"
    assert profiles[0]["major"] == "스포츠산업학"
    assert profiles[1]["name"] == "이종성"
    assert profiles[1]["major"] == "스포츠 문화사"


def test_faculty_profiles_reject_ui_and_recruiting_noise() -> None:
    text = """
    확인 요청 | 내용을 확인하여 수정사항을 회신주시기 바랍니다.
    교수 | 확인 | 상세보기 | 전공 | 별 모집 정보
    교수 | 직급 | 상세보기 | 주전공 | 이름 검색하기
    공과대학 | 건축학부 | 초빙분야 | 동아시아 건축역사이론 전공 우대 선발
    교수 | 임명주 | 상세보기 | 직책/직급 | 교수 | 주전공 | 체육학 | 담당과목
    """

    profiles = extract_faculty_profiles(text, department="스포츠의학부")

    assert [profile["name"] for profile in profiles] == ["임명주"]


def test_faculty_profiles_reject_department_intro_noise() -> None:
    text = """
    CHA University
    전공소개
    About Major
    인사말
    전공소개
    About Major
    교수진
    교과 과정
    전공 교육과정
    공지사항
    전공 소식
    """

    assert extract_faculty_profiles(text, department="스포츠의학과") == []


def test_recover_existing_faculty_research_keeps_good_cache_when_live_empty() -> None:
    existing = {
        "faculty_profiles": [{"name": "이기광", "major": "운동역학"}],
        "faculty_source_pages": [{"url": "https://sport.kookmin.ac.kr"}],
        "faculty_paper_sources": [{"title": "Gender Differences in Lower Limbs Kinematics and Kinetics"}],
        "faculty_query_log": ["이기광 국민대학교 운동역학 논문"],
    }
    recovered = recover_existing_faculty_research({"faculty_profiles": [], "faculty_paper_sources": []}, existing)
    assert recovered["faculty_profiles"][0]["name"] == "이기광"
    assert "Gender Differences" in recovered["faculty_paper_sources"][0]["title"]


def test_faculty_research_uses_professor_name_queries(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        "plugins.academy_ops.hakjong_faculty_research.search_naver_links",
        lambda query, *, limit=6: [{"title": "교수소개", "url": "https://sport.kookmin.ac.kr/prof"}],
    )
    monkeypatch.setattr(
        "plugins.academy_ops.hakjong_faculty_research.read_page_text",
        lambda url: "이기광\nLee, KiKwang\n* 소속 스포츠건강재활학과\n* 전공 운동역학\n* 이메일 kklee@kookmin.ac.kr",
    )

    def fake_scholarly(query: str):
        calls.append(query)
        return [
            {
                "title": "Y-Balance Test 시 마커리스 시스템에서 산출된 하지운동학적 변인의 타당도",
                "snippet": "유연우, Lee Ki Kwang, 운동역학, 하지운동학",
                "source": "openalex",
            }
        ]

    bundle = build_faculty_research(
        "국민대학교",
        "스포츠건강재활학과",
        scholarly_search=fake_scholarly,
        max_faculty=2,
    )

    assert any("이기광 국민대학교 운동역학 논문" in call for call in calls)
    assert any("Ki Kwang Lee 운동역학 research" in call for call in calls)
    assert bundle["faculty_profiles"][0]["name"] == "이기광"
    assert bundle["faculty_paper_sources"][0]["faculty_name"] == "이기광"
    assert "Y-Balance Test" in bundle["faculty_paper_sources"][0]["title"]


def test_faculty_research_rejects_professor_page_titles_as_papers(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.academy_ops.hakjong_faculty_research.search_naver_links",
        lambda query, *, limit=6: [
            {"title": "교수소개 - SNU", "snippet": "강준호 스포츠경영학", "url": "https://sports.snu.ac.kr/prof"},
            {"title": "The Dynamics of Sport Sponsorship Activation", "snippet": "강준호 sport marketing", "url": "https://example.test/paper"},
        ],
    )
    monkeypatch.setattr(
        "plugins.academy_ops.hakjong_faculty_research.read_page_text",
        lambda url: "## 강준호 교수\n**전공**스포츠경영학\n",
    )

    bundle = build_faculty_research(
        "서울대학교",
        "체육교육과",
        scholarly_search=lambda query: [],
        max_faculty=1,
    )

    assert [source["title"] for source in bundle["faculty_paper_sources"]] == [
        "The Dynamics of Sport Sponsorship Activation"
    ]


def test_faculty_research_rejects_bookstore_titles_as_papers(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.academy_ops.hakjong_faculty_research.search_naver_links",
        lambda query, *, limit=6: [
            {"title": "교수진 소개", "snippet": "박성배 연구분야 스포츠산업학", "url": "https://outer.test/prof"},
            {"title": "[중고샵] 스포츠 에이전트의 겉과 속", "snippet": "박성배 스포츠산업", "url": "https://book.test/used"},
        ],
    )
    monkeypatch.setattr(
        "plugins.academy_ops.hakjong_faculty_research.read_page_text",
        lambda url: "#### 박성배 교수 / 전임교원\n* **연구분야**스포츠산업학\n",
    )

    bundle = build_faculty_research(
        "한양대학교",
        "스포츠매니지먼트",
        scholarly_search=lambda query: [],
        max_faculty=1,
    )

    assert bundle["faculty_paper_sources"] == []


def test_faculty_research_prefers_official_university_domain(monkeypatch) -> None:
    def fake_links(query: str, *, limit: int = 6):
        return [
            {"title": "서울대 교수소개", "snippet": "강준호 스포츠경영학", "url": "https://sports.snu.ac.kr/prof"},
            {"title": "서울과기대 교수소개", "snippet": "김교수 스포츠과학", "url": "https://sports.seoultech.ac.kr/prof"},
        ]

    def fake_page(url: str) -> str:
        if "seoultech.ac.kr" in url:
            return "## 김교수 교수\n**전공**스포츠과학"
        return "## 강준호 교수\n**전공**스포츠경영학"

    monkeypatch.setattr("plugins.academy_ops.hakjong_faculty_research.search_naver_links", fake_links)
    monkeypatch.setattr("plugins.academy_ops.hakjong_faculty_research.read_page_text", fake_page)

    bundle = build_faculty_research(
        "서울과학기술대학교",
        "스포츠과학과",
        scholarly_search=lambda query: [],
        max_faculty=2,
    )

    assert [profile["name"] for profile in bundle["faculty_profiles"]] == ["김교수"]


def test_live_research_enrichment_prefers_professor_paper_titles() -> None:
    content = {
        "track_section": {"rows": [], "strong_points": {"bullets": []}},
        "strategy_section": {"actions": [{"body": "학생부 보완"}], "interview_rows": []},
    }
    profile = {
        "live_research": {
            "faculty_paper_sources": [
                {
                    "title": "Y-Balance Test 시 마커리스 시스템에서 산출된 하지운동학적 변인의 타당도",
                    "snippet": "이기광 운동역학",
                }
            ],
            "paper_title_live_probe": [{"usable_keywords": ["운동역학", "하지운동학"]}],
            "field_news_live_probe": [{"keywords": ["스포츠과학"]}],
        }
    }

    applied = live.apply_live_research_enrichment(content, profile)
    visible = json.dumps(content, ensure_ascii=False)

    assert applied is True
    assert "교수 연구 제목: Y-Balance Test 시 마커리스 시스템" in visible
