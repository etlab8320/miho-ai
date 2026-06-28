from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from miho_cli.plugins import PluginContext, PluginManager, PluginManifest


def test_video_id_extraction_rejects_invalid_url() -> None:
    from plugins.youtube_ops.ids import extract_video_id

    assert extract_video_id("https://www.youtube.com/watch?v=Ghj69GLDiqI") == "Ghj69GLDiqI"
    assert extract_video_id("https://youtu.be/Ghj69GLDiqI?t=4") == "Ghj69GLDiqI"
    assert extract_video_id("https://example.com/watch?v=Ghj69GLDiqI") is None
    assert extract_video_id("not a youtube link") is None


def test_youtube_preflight_routes_url_without_phrase_hardcoding() -> None:
    from plugins.youtube_ops.pre_gateway import youtube_preflight_decision

    decision = youtube_preflight_decision("https://www.youtube.com/watch?v=Ghj69GLDiqI 이거 봐줘")

    assert decision is not None
    assert decision.args["url"] == "https://www.youtube.com/watch?v=Ghj69GLDiqI 이거 봐줘"
    assert decision.args["render_card"] is False
    assert decision.args["force_refresh"] is False
    assert youtube_preflight_decision("https://example.com/watch?v=Ghj69GLDiqI 정리") is None


def test_youtube_preflight_enables_card_for_image_requests() -> None:
    from plugins.youtube_ops.pre_gateway import youtube_preflight_decision

    decision = youtube_preflight_decision("https://youtu.be/Ghj69GLDiqI 이미지 카드로 줘")

    assert decision is not None
    assert decision.args["render_card"] is True


def test_summary_covers_every_transcript_chunk() -> None:
    from plugins.youtube_ops.models import TranscriptSegment, VideoMetadata
    from plugins.youtube_ops.summary import summarize_transcript

    calls: list[str] = []
    segments = [
        TranscriptSegment(start=0.0, text=f"chunk marker {index} " * 300)
        for index in range(5)
    ]

    class FakeLlm:
        def complete_structured(self, **kwargs):
            text = kwargs["input"][0]["text"]
            calls.append(text)
            if "Chunk" in kwargs["instructions"]:
                return SimpleNamespace(
                    parsed={
                        "claims": [f"claim {len(calls)}"],
                        "important_points": [f"point {len(calls)}"],
                        "tags": ["RAG"],
                    },
                    provider="fake",
                    model="fake",
                )
            return SimpleNamespace(
                parsed={
                    "short_title": "RAG 검색 방식의 진화",
                    "topic": "RAG 검색 방식의 변화",
                    "summary_lines": ["키워드와 의미 검색을 함께 봐야 한다."],
                    "important_points": ["하이브리드 검색이 핵심이다."],
                    "lessons": ["데이터 성격에 맞춰 검색 전략을 나눈다."],
                    "practical_takeaways": ["PACA/Peak 문서는 RAG와 SQL을 분리한다."],
                    "tags": ["RAG", "하이브리드검색"],
                },
                provider="fake",
                model="fake",
            )

    result = summarize_transcript(
        metadata=VideoMetadata(video_id="Ghj69GLDiqI", title="원본", channel="채널"),
        segments=segments,
        llm=FakeLlm(),
        chunk_chars=900,
    )

    assert result.coverage["chunk_count"] > 1
    assert result.coverage["processed_chunk_count"] == result.coverage["chunk_count"]
    assert result.short_title == "RAG 검색 방식의 진화"
    assert "하이브리드검색" in result.tags
    assert result.one_line_summary == "키워드와 의미 검색을 함께 봐야 한다."
    assert result.miho_judgment == ""


def test_youtube_summary_refuses_no_llm_heuristic_fallback() -> None:
    from plugins.youtube_ops.models import TranscriptSegment, VideoMetadata
    from plugins.youtube_ops.summary import YouTubeSummaryLLMError, summarize_transcript

    with pytest.raises(YouTubeSummaryLLMError, match="requires an LLM"):
        summarize_transcript(
            metadata=VideoMetadata(video_id="Ghj69GLDiqI", title="AI 개발 구조", channel="채널"),
            segments=[TranscriptSegment(start=0, text="AI가 코드를 만들어 줘도 사용자는 구조를 이해해야 한다")],
            llm=None,
            chunk_chars=900,
        )


def test_cache_reuses_same_video_id_and_uniquifies_titles(tmp_path: Path) -> None:
    from plugins.youtube_ops.cache import YouTubeCache
    from plugins.youtube_ops.models import SummaryResult, VideoMetadata

    cache = YouTubeCache(tmp_path)
    first = SummaryResult(
        video_id="Ghj69GLDiqI",
        canonical_url="https://www.youtube.com/watch?v=Ghj69GLDiqI",
        short_title="RAG 검색 방식의 진화",
        metadata=VideoMetadata(video_id="Ghj69GLDiqI", title="원본1", channel="채널"),
        topic="주제",
        summary_lines=["요약"],
        important_points=["포인트"],
        lessons=["교훈"],
        practical_takeaways=["적용"],
        tags=["RAG"],
        coverage={"summary_basis": "full_transcript"},
    )
    second = SummaryResult(
        video_id="abc123XYZ09",
        canonical_url="https://www.youtube.com/watch?v=abc123XYZ09",
        short_title="RAG 검색 방식의 진화",
        metadata=VideoMetadata(video_id="abc123XYZ09", title="원본2", channel="채널"),
        topic="주제",
        summary_lines=["요약"],
        important_points=["포인트"],
        lessons=["교훈"],
        practical_takeaways=["적용"],
        tags=["RAG"],
        coverage={"summary_basis": "full_transcript"},
    )

    assert cache.load_summary("Ghj69GLDiqI") is None
    saved_first = cache.save_summary(first)
    saved_second = cache.save_summary(second)

    assert cache.load_summary("Ghj69GLDiqI") is not None
    assert saved_first.short_title == "RAG 검색 방식의 진화"
    assert saved_second.short_title.startswith("RAG 검색 방식의 진화")
    assert saved_second.short_title != saved_first.short_title

def test_summary_from_old_cache_keeps_new_fields_compatible() -> None:
    from plugins.youtube_ops.models import SummaryResult

    summary = SummaryResult.from_dict(
        {
            "video_id": "Ghj69GLDiqI",
            "canonical_url": "https://www.youtube.com/watch?v=Ghj69GLDiqI",
            "short_title": "이전 캐시",
            "metadata": {"video_id": "Ghj69GLDiqI", "title": "원본", "channel": "채널"},
            "topic": "주제",
            "summary_lines": ["요약"],
            "important_points": ["포인트"],
            "lessons": [],
            "practical_takeaways": [],
            "tags": [],
            "coverage": {},
        }
    )

    assert summary.one_line_summary == ""
    assert summary.miho_judgment == ""
    assert summary.profile_help == []
    assert summary.metadata.published_at == ""

def test_youtube_answer_text_uses_learning_report_shape() -> None:
    from plugins.youtube_ops.models import SummaryResult, VideoMetadata
    from plugins.youtube_ops.tools import _answer_text

    summary = SummaryResult(
        video_id="Ghj69GLDiqI",
        canonical_url="https://www.youtube.com/watch?v=Ghj69GLDiqI",
        short_title="AI 개발 구조 지도",
        metadata=VideoMetadata(
            video_id="Ghj69GLDiqI",
            title="바이브코딩 입문",
            channel="생존연구소",
            published_at="2026-05-01",
        ),
        topic="AI로 개발할 때 알아야 하는 기본 구조",
        summary_lines=["AI가 코드를 만들어도 개발 구조를 알아야 한다."],
        important_points=["프롬프트보다 컨텍스트가 중요하다.", "Git, API, DB 개념이 필요하다."],
        lessons=["용어를 알아야 막힌 지점을 찾을 수 있다."],
        practical_takeaways=["개발 요청을 프론트엔드, 백엔드, DB로 나눠 지시한다."],
        tags=["바이브코딩"],
        coverage={"summary_basis": "full_transcript"},
        one_line_summary="AI에게 코딩을 맡겨도 개발 구조를 읽을 줄 알아야 한다.",
        miho_judgment="입문자에게 필요한 용어 지도에 가깝다.",
        profile_help=["AI 개발 요청을 구조화하는 데 바로 쓸 수 있다."],
        conclusion="문법보다 구조 이해가 먼저다.",
    )

    text = _answer_text(summary)

    assert "채널: 생존연구소" in text
    assert "게시일: 2026-05-01" in text
    assert "1. 주제" in text
    assert "2. 한 줄 요약" in text
    assert "3. 주요 내용" in text
    assert "4. 미호의 판단" in text
    assert "5. 사용자 맥락에서 도움되는 점" in text
    assert "6. 결론" in text
    assert "입문자에게 필요한 용어 지도" in text

def test_analyze_tool_refreshes_legacy_youtube_cache(tmp_path: Path, monkeypatch) -> None:
    from plugins.youtube_ops import tools as tool_module
    from plugins.youtube_ops.cache import YouTubeCache
    from plugins.youtube_ops.models import SummaryResult, TranscriptSegment, VideoMetadata

    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    cache = YouTubeCache()
    legacy = SummaryResult(
        video_id="Ghj69GLDiqI",
        canonical_url="https://www.youtube.com/watch?v=Ghj69GLDiqI",
        short_title="예전 요약",
        metadata=VideoMetadata(video_id="Ghj69GLDiqI", title="예전", channel="채널"),
        topic="예전 주제",
        summary_lines=["얕은 요약"],
        important_points=["얕은 포인트"],
        lessons=[],
        practical_takeaways=[],
        tags=[],
        coverage={"summary_basis": "full_transcript"},
    )
    cache.save_summary(legacy)
    monkeypatch.setattr(
        tool_module,
        "fetch_video_metadata",
        lambda video_id: VideoMetadata(
            video_id=video_id,
            title="새 제목",
            channel="새 채널",
            published_at="2026-05-27",
        ),
    )
    monkeypatch.setattr(
        tool_module,
        "fetch_transcript",
        lambda video_id, languages=None: [TranscriptSegment(start=0, text="새 전체 자막")],
    )
    monkeypatch.setattr(
        tool_module,
        "summarize_transcript",
        lambda **_: SummaryResult(
            video_id="Ghj69GLDiqI",
            canonical_url="https://www.youtube.com/watch?v=Ghj69GLDiqI",
            short_title="새 리포트",
            metadata=VideoMetadata(
                video_id="Ghj69GLDiqI",
                title="새 제목",
                channel="새 채널",
                published_at="2026-05-27",
            ),
            topic="새 주제",
            summary_lines=["새 요약"],
            important_points=["새 포인트"],
            lessons=[],
            practical_takeaways=[],
            tags=[],
            coverage={"summary_basis": "full_transcript"},
            one_line_summary="새 한 줄",
            miho_judgment="새 판단",
            profile_help=["새 도움"],
            conclusion="새 결론",
        ),
    )

    payload = json.loads(
        tool_module._youtube_analyze_tool_handler({"url": "https://youtu.be/Ghj69GLDiqI"})
    )

    assert payload["cached"] is False
    assert payload["summary"]["short_title"] == "새 리포트"
    assert "새 판단" in payload["message"]


def test_card_html_uses_short_title_and_goyang_font() -> None:
    from plugins.youtube_ops.card_template import render_card_html
    from plugins.youtube_ops.models import SummaryResult, VideoMetadata

    summary = SummaryResult(
        video_id="Ghj69GLDiqI",
        canonical_url="https://www.youtube.com/watch?v=Ghj69GLDiqI",
        short_title="RAG 검색 방식의 진화",
        metadata=VideoMetadata(video_id="Ghj69GLDiqI", title="LLMOps 7강", channel="코딩하는초롱"),
        topic="RAG의 변화",
        summary_lines=["하이브리드 검색이 실무 표준으로 간다."],
        important_points=["키워드 검색과 의미 검색을 분리해서 써야 한다."],
        lessons=["검색 전략은 데이터 성격에 맞춰야 한다."],
        practical_takeaways=["학원 문서형 지식은 RAG, 운영 데이터는 SQL로 나눈다."],
        tags=["RAG", "검색"],
        coverage={"summary_basis": "full_transcript", "segment_count": 270},
    )

    html = render_card_html(summary, font_css="@font-face{font-family:'GoyangDeogyang';}")

    assert "RAG 검색 방식의 진화" in html
    assert "LLMOps 7강" in html
    assert "GoyangDeogyang" in html
    assert "중요 포인트" in html
    assert "note-shell" in html
    assert "signal-row" in html


def test_card_renderer_uses_content_aware_height(tmp_path: Path, monkeypatch) -> None:
    from plugins.youtube_ops import card_renderer
    from plugins.youtube_ops.models import SummaryResult, VideoMetadata

    captured: dict[str, int] = {}

    def fake_capture(html_path, image_path, *, width, height):
        captured["width"] = width
        captured["height"] = height
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(card_renderer, "capture_html_to_png", fake_capture)
    monkeypatch.setattr(card_renderer, "goyang_font_css", lambda: "")
    monkeypatch.setattr(card_renderer, "_measure_html_height", lambda html_path: 760)
    summary = SummaryResult(
        video_id="Ghj69GLDiqI",
        canonical_url="https://www.youtube.com/watch?v=Ghj69GLDiqI",
        short_title="짧은 요약",
        metadata=VideoMetadata(video_id="Ghj69GLDiqI", title="원본", channel="채널"),
        topic="핵심만 짧게 정리한 영상",
        summary_lines=["핵심은 빠른 캐시와 전체 자막 검증이다."],
        important_points=["같은 영상은 다시 요약하지 않는다."],
        lessons=[],
        practical_takeaways=[],
        tags=["유튜브요약"],
        coverage={"summary_basis": "full_transcript", "segment_count": 20},
    )

    card_renderer.render_summary_card_png(summary, tmp_path)

    assert captured["width"] == 1200
    assert captured["height"] == 832


def test_ytdlp_vtt_parser_deduplicates_caption_fragments() -> None:
    from plugins.youtube_ops.transcript import parse_vtt_transcript

    vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
RAG 검색은

00:00:02.500 --> 00:00:04.000
RAG 검색은

00:00:04.000 --> 00:00:06.000
하이브리드로 간다
"""

    segments = parse_vtt_transcript(vtt)

    assert [segment.text for segment in segments] == ["RAG 검색은", "하이브리드로 간다"]
    assert segments[0].start == 1.0


def test_ytdlp_failure_is_plain_korean(monkeypatch) -> None:
    from plugins.youtube_ops import transcript

    monkeypatch.setattr(
        transcript.subprocess,
        "run",
        lambda *_, **__: SimpleNamespace(
            returncode=1,
            stderr="ERROR: [youtube] Ghj69GLDiqI: Video unavailable",
            stdout="",
        ),
    )

    try:
        transcript._fetch_with_ytdlp("Ghj69GLDiqI")
    except transcript.YouTubeFetchError as exc:
        assert str(exc) == "비공개이거나 삭제된 영상 같아."
    else:
        raise AssertionError("expected YouTubeFetchError")


def test_analyze_tool_saves_rag_and_returns_media_tag(tmp_path: Path, monkeypatch) -> None:
    from plugins.youtube_ops import register
    from plugins.youtube_ops.context import capture_gateway_context
    from plugins.youtube_ops import tools as tool_module
    from plugins.youtube_ops.models import SummaryResult, TranscriptSegment, VideoMetadata

    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    monkeypatch.setattr(
        tool_module,
        "fetch_video_metadata",
        lambda video_id: VideoMetadata(video_id=video_id, title="LLMOps 7강", channel="코딩하는초롱"),
    )
    monkeypatch.setattr(
        tool_module,
        "fetch_transcript",
        lambda video_id, languages=None: [TranscriptSegment(start=0, text="RAG와 하이브리드 검색 설명")],
    )
    monkeypatch.setattr(
        tool_module,
        "summarize_transcript",
        lambda **_: SummaryResult(
            video_id="Ghj69GLDiqI",
            canonical_url="https://www.youtube.com/watch?v=Ghj69GLDiqI",
            short_title="RAG 검색 방식의 진화",
            metadata=VideoMetadata(video_id="Ghj69GLDiqI", title="LLMOps 7강", channel="코딩하는초롱"),
            topic="RAG의 변화",
            summary_lines=["하이브리드 검색이 중요하다."],
            important_points=["키워드 검색과 의미 검색을 같이 본다."],
            lessons=["검색 전략을 분리한다."],
            practical_takeaways=["운영 데이터와 문서 지식을 분리한다."],
            tags=["RAG", "하이브리드검색"],
            coverage={"summary_basis": "full_transcript", "segment_count": 1},
        ),
    )

    def fake_render(summary, output_dir):
        path = output_dir / "card.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        return path

    monkeypatch.setattr(tool_module, "render_summary_card_png", fake_render)

    source = SimpleNamespace(
        guild_id="g1",
        chat_id="c1",
        parent_chat_id="",
        thread_id="",
        chat_name="youtube",
        user_id="u1",
    )
    event = SimpleNamespace(source=source, text="https://www.youtube.com/watch?v=Ghj69GLDiqI 요약")
    ctx = PluginContext(PluginManifest(name="youtube_ops", key="youtube_ops"), PluginManager())
    register(ctx)
    capture_gateway_context(event)

    payload = json.loads(
        tool_module._youtube_analyze_tool_handler(
            {"url": "https://www.youtube.com/watch?v=Ghj69GLDiqI", "render_card": True}
        )
    )

    assert payload["ok"] is True
    assert payload["cached"] is False
    assert payload["summary"]["short_title"] == "RAG 검색 방식의 진화"
    assert payload["media_tag"].startswith("MEDIA:")
    rag_path = tmp_path / ".miho" / "discord" / "guilds" / "g1" / "channels" / "youtube__c1" / "rag" / "messages.jsonl"
    assert rag_path.exists()
    rag_lines = rag_path.read_text(encoding="utf-8").splitlines()
    assert len(rag_lines) == 1
    assert "RAG 검색 방식의 진화" in rag_lines[0]


@pytest.mark.asyncio
async def test_youtube_pre_gateway_dispatch_responds_with_tool_result(monkeypatch) -> None:
    import plugins.youtube_ops as youtube_ops

    seen: dict[str, object] = {}

    def fake_handler(args):
        seen.update(args)
        return json.dumps({"ok": True, "message": "빠른 유튜브 요약\nMEDIA:/tmp/card.png"}, ensure_ascii=False)

    monkeypatch.setattr(youtube_ops, "_youtube_analyze_tool_handler", fake_handler)
    event = SimpleNamespace(text="https://www.youtube.com/watch?v=Ghj69GLDiqI 이미지로 정리해줘", source=SimpleNamespace())

    result = await youtube_ops._youtube_pre_gateway_dispatch(event=event)

    assert result["action"] == "respond"
    assert result["text"] == "빠른 유튜브 요약\nMEDIA:/tmp/card.png"
    assert result["route"] == "youtube_ops"
    assert result["reason"] == "youtube_preflight"
    assert seen["render_card"] is True
    assert seen["force_refresh"] is False


@pytest.mark.asyncio
async def test_youtube_pre_gateway_dispatch_allows_non_youtube_text(monkeypatch) -> None:
    import plugins.youtube_ops as youtube_ops

    def fail_handler(args):
        raise AssertionError(args)

    monkeypatch.setattr(youtube_ops, "_youtube_analyze_tool_handler", fail_handler)
    event = SimpleNamespace(text="오늘 학원 일정 줘", source=SimpleNamespace())

    assert await youtube_ops._youtube_pre_gateway_dispatch(event=event) == {"action": "allow"}
