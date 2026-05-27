from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from miho_cli.plugins import PluginContext, PluginManager, PluginManifest


def test_video_id_extraction_rejects_invalid_url() -> None:
    from plugins.youtube_ops.ids import extract_video_id

    assert extract_video_id("https://www.youtube.com/watch?v=Ghj69GLDiqI") == "Ghj69GLDiqI"
    assert extract_video_id("https://youtu.be/Ghj69GLDiqI?t=4") == "Ghj69GLDiqI"
    assert extract_video_id("https://example.com/watch?v=Ghj69GLDiqI") is None
    assert extract_video_id("not a youtube link") is None


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
    ctx._manager.invoke_hook("pre_gateway_dispatch", event=event)

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
