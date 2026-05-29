"""Owner-memory recall beyond the recent window + timeline retention.

The owner timeline used to feed only the most recent 60 events into prompt
selection, so anything the owner said earlier was unreachable even on an exact
topic match. search_profile_events now pulls matching older events, and
append_profile_event prunes the timeline to a configurable cap.
"""

from __future__ import annotations

import gateway.owner_profile_context as ctx
from miho_cli import owner_profile


def _use_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    owner_profile.ensure_owner_profile_store()


def test_search_profile_events_finds_old_match(tmp_path, monkeypatch) -> None:
    _use_home(tmp_path, monkeypatch)
    owner_profile.append_profile_event("general", "서하 부상", "서하가 무릎 부상으로 재활 중이다")
    for i in range(80):
        owner_profile.append_profile_event("daily_summary", f"day{i}", "특이사항 없음 일상 기록")

    hits = owner_profile.search_profile_events(["서하"])
    assert hits and any("서하" in h["content"] for h in hits)


def test_recall_surfaces_event_outside_recent_window(tmp_path, monkeypatch) -> None:
    _use_home(tmp_path, monkeypatch)
    owner_profile.append_profile_event("general", "서하 재활", "서하 무릎 재활 계획을 세웠다")
    for i in range(80):
        owner_profile.append_profile_event("daily_summary", f"day{i}", "특이사항 없음")

    block = ctx.build_relevant_owner_profile_context("서하 재활 어떻게 됐어?")
    assert "서하" in block, "an old but on-topic owner memory should still be recalled"


def test_timeline_retention_caps_events(tmp_path, monkeypatch) -> None:
    _use_home(tmp_path, monkeypatch)
    monkeypatch.setenv("MIHO_OWNER_TIMELINE_MAX_EVENTS", "10")
    for i in range(25):
        owner_profile.append_profile_event("general", f"t{i}", f"content number {i}")

    rows = owner_profile.list_profile_events(limit=100)
    assert len(rows) == 10
    contents = {r["content"] for r in rows}
    assert "content number 24" in contents  # newest kept
    assert "content number 0" not in contents  # oldest pruned


def test_domain_tokens_not_stopped() -> None:
    # "max"/"et" are meaningful in this academy/company context (맥스/ET);
    # they must survive tokenization rather than be discarded as stop-words.
    assert "et" not in ctx._STOP_TOKENS
    assert "max" not in ctx._STOP_TOKENS
    assert "max" in ctx._tokenize("max 일정 정리")
