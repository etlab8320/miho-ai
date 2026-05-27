"""Tool handlers for YouTube operations."""

from __future__ import annotations

import json
from typing import Any

from .cache import YouTubeCache
from .card_renderer import YouTubeCardRenderError, font_license_note, render_summary_card_png
from .ids import canonical_url, extract_video_id
from .rag import save_summary_to_thread_rag
from .summary import summarize_transcript
from .transcript import YouTubeFetchError, fetch_transcript, fetch_video_metadata

_LLM: Any = None


def set_llm(llm: Any) -> None:
    global _LLM
    _LLM = llm


def _youtube_analyze_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    url = str(payload.get("url") or "").strip()
    video_id = extract_video_id(url)
    if video_id is None:
        return _json({"ok": False, "message": "유튜브 영상 링크나 video_id를 찾지 못했어."})

    render_card = bool(payload.get("render_card", False))
    force_refresh = bool(payload.get("force_refresh", False))
    cache = YouTubeCache()
    cached = None if force_refresh else cache.load_summary(video_id)
    if cached is not None and not _needs_report_refresh(cached):
        return _json(_final_payload(cached, cache=cache, cached=True, render_card=render_card))

    metadata = fetch_video_metadata(video_id)
    try:
        segments = fetch_transcript(video_id, _languages(payload.get("languages")))
    except YouTubeFetchError as exc:
        return _json({"ok": False, "message": str(exc), "video_id": video_id})
    if not segments:
        return _json({"ok": False, "message": "이 영상에서 확인 가능한 자막을 찾지 못했어.", "video_id": video_id})

    summary = summarize_transcript(metadata=metadata, segments=segments, llm=_LLM)
    summary = cache.save_summary(summary)
    return _json(_final_payload(summary, cache=cache, cached=False, render_card=render_card))


def _final_payload(
    summary,
    *,
    cache: YouTubeCache,
    cached: bool,
    render_card: bool,
) -> dict[str, Any]:
    card_error = ""
    media_tag = ""
    if render_card:
        if summary.card_image_path:
            image_path = summary.card_image_path
        else:
            try:
                image_path = str(render_summary_card_png(summary, cache.card_output_dir(summary.video_id)))
                summary.card_image_path = image_path
                cache.save_summary(summary)
            except YouTubeCardRenderError as exc:
                image_path = ""
                card_error = str(exc)
        if image_path:
            media_tag = f"MEDIA:{image_path}"
    save_summary_to_thread_rag(summary)
    message = _answer_text(summary)
    if media_tag:
        message = f"{message}\n{media_tag}"
    return {
        "ok": True,
        "operation": "youtube.analyze",
        "cached": cached,
        "summary": summary.to_dict(),
        "message": message,
        "media_tag": media_tag,
        "card_error": card_error,
        "font": font_license_note(),
        "assistant_guidance": (
            "Use the summary facts only. Do not invent points beyond summary/coverage. "
            "If card_error is present, explain the image render issue in Korean."
        ),
    }


def _needs_report_refresh(summary) -> bool:
    return not all(
        [
            str(getattr(summary, "one_line_summary", "") or "").strip(),
            str(getattr(summary, "miho_judgment", "") or "").strip(),
            str(getattr(summary, "conclusion", "") or "").strip(),
            str(getattr(summary.metadata, "published_at", "") or "").strip(),
        ]
    )


def _answer_text(summary) -> str:
    one_line = summary.one_line_summary or _first(summary.summary_lines) or summary.topic
    judgment = summary.miho_judgment or "영상의 주장은 참고하되, 실제 적용 전에는 근거와 맥락을 한 번 더 확인하는 게 좋아."
    conclusion = summary.conclusion or one_line
    lines = [
        f"{summary.short_title}",
        f"원본: {summary.metadata.title or canonical_url(summary.video_id)}",
        f"채널: {summary.metadata.channel or '확인 불가'}",
        f"게시일: {summary.metadata.published_at or '확인 불가'}",
        "",
        f"영상 핵심은 “{one_line}”야.",
        "",
        "1. 주제",
        summary.topic or one_line,
        "",
        "2. 한 줄 요약",
        one_line,
        "",
        "3. 주요 내용",
        *_numbered_or_bullets(summary.important_points or summary.summary_lines, limit=7),
        "",
        "4. 미호의 판단",
        judgment,
        "",
        "5. 사용자 맥락에서 도움되는 점",
        *_numbered_or_bullets(summary.profile_help or summary.practical_takeaways or summary.lessons, limit=4),
        "",
        "6. 결론",
        conclusion,
    ]
    return "\n".join(lines).strip()


def _first(items: list[str]) -> str:
    return next((str(item).strip() for item in items if str(item).strip()), "")


def _numbered_or_bullets(items: list[str], *, limit: int) -> list[str]:
    cleaned = [str(item).strip() for item in items if str(item).strip()][:limit]
    if not cleaned:
        return ["- 자막에서 신뢰할 만한 세부 항목을 충분히 뽑지 못했어."]
    return [f"- {item}" for item in cleaned]


def _languages(raw: Any) -> list[str] | None:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()] or None
    if isinstance(raw, str) and raw.strip():
        return [item.strip() for item in raw.split(",") if item.strip()]
    return None


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
