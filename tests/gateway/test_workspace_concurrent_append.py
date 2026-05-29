"""Concurrency guard for workspace JSONL appends.

Concurrent Discord turns in the same thread append to the same JSONL file.
Without an exclusive lock the writes interleave and corrupt a line. These
tests assert that path_lock/append_jsonl_locked serialize writers so every
line stays valid JSON and no record is lost.
"""

from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

from gateway.discord_workspace_paths import append_jsonl_locked, count_lines


def _worker(args: tuple[str, int]) -> None:
    path_str, idx = args
    # A non-trivial payload makes torn writes easy to detect as invalid JSON.
    append_jsonl_locked(Path(path_str), {"idx": idx, "pad": "x" * 200})


def test_append_jsonl_locked_returns_sequential_counts(tmp_path: Path) -> None:
    path = tmp_path / "rag" / "messages.jsonl"
    assert append_jsonl_locked(path, {"a": 1}) == 1
    assert append_jsonl_locked(path, {"b": 2}) == 2
    assert count_lines(path) == 2


def test_concurrent_appends_keep_every_line_valid(tmp_path: Path) -> None:
    path = tmp_path / "rag" / "messages.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    writers = 12
    with multiprocessing.Pool(writers) as pool:
        pool.map(_worker, [(str(path), i) for i in range(writers)])

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == writers, "a write was lost or the file was truncated"
    seen = set()
    for line in lines:
        record = json.loads(line)  # raises if a line was torn by interleaving
        seen.add(record["idx"])
    assert seen == set(range(writers)), "every writer's record must survive"
