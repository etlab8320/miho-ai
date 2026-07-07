"""Safe external prompt corpus indexing for Miho System WikiGraph.

This module treats public prompt repositories as reference material, not as
runtime prompt text.  It records metadata, hashes, and high-level patterns so
Miho can compare governance practices without copying third-party prompt bodies
into its own prompts or generated wiki pages.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from miho_constants import get_miho_home

from . import system_wikigraph as wg

DEFAULT_CORPUS_ROOT = get_miho_home() / "governance" / "external_prompt_corpus"
MAX_SOURCE_BYTES = 1_500_000
MAX_SCAN_CHARS = 120_000

PROMPT_FILE_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml"}
PATTERN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "tool_policy": ("tool", "function call", "function_call", "tools", "shell", "terminal"),
    "safety_policy": ("safety", "secret", "password", "credential", "destructive", "permission", "approval"),
    "coding_loop": ("git status", "test", "tests", "lint", "build", "diff", "commit", "pull request", "pr"),
    "memory_policy": ("memory", "remember", "persistent", "profile", "preference"),
    "final_answer_policy": ("final answer", "final response", "summary", "deliver", "complete", "done"),
    "clarification_policy": ("ask", "clarify", "question", "ambiguous", "assumption"),
    "agent_loop": ("plan", "step", "iterate", "retry", "verify", "recover", "failure"),
}


class ExternalCorpusError(ValueError):
    """Raised when an external prompt corpus cannot be safely indexed."""


def sync_external_prompt_corpus(*, source: str | Path | None = None) -> dict[str, Any]:
    """Index an external prompt corpus into System WikiGraph without copying bodies.

    If *source* is omitted, the default local reference directory is prepared and
    summarized.  The function never clones a remote repository and never writes
    prompt bodies into the wiki/graph; it stores hashes, paths, and pattern
    counts only.
    """

    wg.init_wiki()
    root = _resolve_source(source)
    root.mkdir(parents=True, exist_ok=True)

    stats = {
        "source": str(root),
        "files_scanned": 0,
        "artifacts_indexed": 0,
        "patterns_indexed": 0,
        "edges": 0,
        "skipped_sensitive": 0,
        "skipped_large": 0,
    }
    pattern_totals: Counter[str] = Counter()
    conn = wg.connect()
    try:
        _upsert_corpus_root(conn, root)
        for path in _iter_prompt_files(root):
            if wg.is_probably_sensitive(path):
                stats["skipped_sensitive"] += 1
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_SOURCE_BYTES:
                stats["skipped_large"] += 1
                continue
            stats["files_scanned"] += 1
            content = wg.safe_read(path, max_chars=MAX_SCAN_CHARS)
            patterns = detect_patterns(content)
            for key, count in patterns.items():
                pattern_totals[key] += count
            _upsert_artifact(conn, root, path, size=size, patterns=patterns, stats=stats)
        for pattern, count in sorted(pattern_totals.items()):
            _upsert_pattern(conn, pattern, count)
            stats["patterns_indexed"] += 1
        conn.commit()
    finally:
        conn.close()

    drill_candidates = build_self_harness_drill_candidates(pattern_totals)
    _write_external_prompt_pages(
        root=root,
        stats=stats,
        pattern_totals=pattern_totals,
        drill_candidates=drill_candidates,
    )
    wg.append_log(
        "external-prompts sync | "
        f"source={root} files={stats['files_scanned']} artifacts={stats['artifacts_indexed']}"
    )
    return {
        "success": True,
        "source": str(root),
        "summary": stats,
        "patterns": dict(sorted(pattern_totals.items())),
        "drill_candidates": drill_candidates,
        "wiki_dir": str(wg.system_paths().wiki_dir),
        "db_path": str(wg.system_paths().db_path),
    }


def detect_patterns(content: str) -> dict[str, int]:
    """Return high-level governance pattern counts from prompt text."""

    lowered = (content or "").lower()
    counts: dict[str, int] = {}
    for pattern, keywords in PATTERN_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            score += lowered.count(keyword.lower())
        if score:
            counts[pattern] = score
    return counts


def build_self_harness_drill_candidates(pattern_totals: Counter[str] | dict[str, int]) -> list[dict[str, Any]]:
    """Convert external prompt patterns into safe Self-Harness drill ideas.

    The output is candidate-only. It creates no active runtime rule and requires
    explicit test implementation plus Evolution OS promotion before activation.
    """

    totals = Counter(pattern_totals or {})
    specs: dict[str, tuple[str, str, str]] = {
        "tool_policy": (
            "tool_required_when_state_is_needed",
            "When a request depends on live/file/system state, Miho must use a tool before answering.",
            "tests/plugins/test_governance_os_policy.py",
        ),
        "safety_policy": (
            "secrets_and_destructive_actions_fail_closed",
            "Secret handling and destructive operations must fail closed without leaking or guessing.",
            "tests/plugins/test_governance_os_policy.py",
        ),
        "coding_loop": (
            "coding_runs_verify_before_final",
            "Coding changes should check worktree state, run focused tests, and review diffs before final delivery.",
            "tests/plugins/test_governance_os_self_harness.py",
        ),
        "final_answer_policy": (
            "final_answer_requires_delivery_evidence",
            "Final delivery should cite actual tool/artifact evidence and avoid unsupported completion claims.",
            "tests/plugins/test_governance_os_final_delivery_agent.py",
        ),
        "clarification_policy": (
            "ask_only_when_missing_context_is_material",
            "Miho should act on obvious defaults and ask only when missing context changes the safe action.",
            "tests/plugins/test_governance_os_goal_first_prompts.py",
        ),
        "memory_policy": (
            "durable_memory_only_for_stable_preferences",
            "Memory updates should store durable confirmed preferences, not temporary task progress.",
            "tests/plugins/test_governance_os_domain_packs.py",
        ),
        "agent_loop": (
            "long_running_work_has_recovery_path",
            "Long-running work needs visible recovery/checkpoint behavior instead of silent failure.",
            "tests/plugins/test_governance_os_readiness_probes.py",
        ),
    }
    candidates: list[dict[str, Any]] = []
    for pattern, count in totals.most_common():
        if pattern not in specs or count <= 0:
            continue
        drill_id, intent, test_target = specs[pattern]
        candidates.append(
            {
                "id": f"external_prompt_drill:{drill_id}",
                "source_pattern": pattern,
                "observed_keyword_hits": int(count),
                "intent": intent,
                "target_test": test_target,
                "activation_policy": "candidate_only_until_explicit_test_implementation",
            }
        )
    return candidates


def _resolve_source(source: str | Path | None) -> Path:
    if source is None or str(source).strip() == "":
        return DEFAULT_CORPUS_ROOT
    root = Path(source).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise ExternalCorpusError(f"external prompt source is not a directory: {root}")
    return root


def _iter_prompt_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in wg.SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() in PROMPT_FILE_EXTENSIONS:
            yield path


def _upsert_corpus_root(conn: sqlite3.Connection, root: Path) -> None:
    wg.upsert_node(
        conn,
        node_id="external-prompt-corpus:local",
        node_type="ExternalPromptCorpus",
        title="Local External Prompt Corpus",
        summary="Reference-only prompt corpus metadata for Miho governance comparison; prompt bodies are not copied into Miho prompts.",
        path=str(root),
        component="external-prompts",
        risk="medium",
        status="observed",
        metadata={
            "default_root": str(DEFAULT_CORPUS_ROOT),
            "body_storage_policy": "metadata_hashes_and_pattern_counts_only",
        },
    )


def _upsert_artifact(
    conn: sqlite3.Connection,
    root: Path,
    path: Path,
    *,
    size: int,
    patterns: dict[str, int],
    stats: dict[str, int],
) -> None:
    rel = path.relative_to(root).as_posix()
    artifact_id = f"external-prompt:{wg.slug_for(rel)}"
    wg.upsert_node(
        conn,
        node_id=artifact_id,
        node_type="ExternalPromptArtifact",
        title=rel,
        summary=_safe_summary(rel, patterns),
        path=str(path),
        component="external-prompts",
        risk="medium",
        status="observed",
        content_hash=wg.file_hash(path),
        metadata={
            "relative_path": rel,
            "size_bytes": size,
            "patterns": patterns,
            "license_boundary": "reference-only; do not embed third-party prompt bodies in Miho runtime prompts",
        },
    )
    wg.upsert_edge(
        conn,
        source_id="external-prompt-corpus:local",
        relation="contains",
        target_id=artifact_id,
        status="observed",
        confidence=0.9,
        evidence="local external prompt corpus file",
    )
    stats["edges"] += 1
    stats["artifacts_indexed"] += 1
    for pattern in patterns:
        pattern_id = f"external-prompt-pattern:{pattern}"
        wg.upsert_edge(
            conn,
            source_id=artifact_id,
            relation="observes_pattern",
            target_id=pattern_id,
            status="inferred",
            confidence=0.55,
            evidence="keyword-level pattern count; prompt body not copied",
        )
        wg.upsert_edge(
            conn,
            source_id=pattern_id,
            relation="informs",
            target_id="component:governance",
            status="inferred",
            confidence=0.5,
            evidence="external prompt pattern can inform Miho governance checks",
        )
        stats["edges"] += 2


def _upsert_pattern(conn: sqlite3.Connection, pattern: str, count: int) -> None:
    wg.upsert_node(
        conn,
        node_id=f"external-prompt-pattern:{pattern}",
        node_type="ExternalPromptPattern",
        title=pattern.replace("_", " ").title(),
        summary=f"Observed {count} keyword hit(s) across indexed external prompt files.",
        component="external-prompts",
        risk="low",
        status="inferred",
        metadata={"keyword_hits": count, "keywords": list(PATTERN_KEYWORDS.get(pattern, ()))},
    )


def _safe_summary(rel: str, patterns: dict[str, int]) -> str:
    if not patterns:
        return f"External prompt reference file: {rel}; no tracked governance pattern keywords found."
    names = ", ".join(sorted(patterns))
    return f"External prompt reference file: {rel}; observed pattern families: {names}."


def _write_external_prompt_pages(
    *,
    root: Path,
    stats: dict[str, int],
    pattern_totals: Counter[str],
    drill_candidates: list[dict[str, Any]],
) -> None:
    paths = wg.system_paths()
    page = paths.wiki_dir / "external-prompts" / "prompt-corpus-map.md"
    pattern_lines = "\n".join(f"- `{name}`: {count}" for name, count in sorted(pattern_totals.items()))
    if not pattern_lines:
        pattern_lines = "- No external prompt files indexed yet. Place a local checkout under the source directory or pass `--source`."
    content = f"""---
title: External Prompt Corpus Map
created: {wg.today()}
updated: {wg.today()}
type: map
status: observed
tags: [miho, governance, external-prompts, wikigraph]
sources: [{root}]
---

# External Prompt Corpus Map

Miho can reference public prompt repositories as an external governance corpus.
This page is intentionally metadata-only: it does not copy prompt bodies into
Miho's runtime prompt, skills, or wiki pages.

## Source
`{root}`

## Safety boundary
- Store file paths, hashes, sizes, and high-level pattern counts.
- Do not paste third-party prompt bodies into Miho system prompts.
- Keep license/source attribution with the local checkout.
- Treat extracted patterns as checklist/test inspiration, not direct runtime rules.

## Latest sync summary
```json
{json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True)}
```

## Observed pattern families
{pattern_lines}

## Operator command
```bash
miho evolution wikigraph external-prompts sync --source {root}
```
"""
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(content, encoding="utf-8")

    drills = paths.wiki_dir / "external-prompts" / "self-harness-drill-candidates.md"
    drill_lines = "\n".join(
        f"- `{item['id']}` → {item['intent']} (`{item['target_test']}`)"
        for item in drill_candidates
    )
    if not drill_lines:
        drill_lines = "- No drill candidates yet."
    drills.write_text(
        f"""---
title: External Prompt Self-Harness Drill Candidates
created: {wg.today()}
updated: {wg.today()}
type: map
status: inferred
tags: [miho, governance, external-prompts, self-harness]
sources: [{root}]
---

# External Prompt Self-Harness Drill Candidates

These are candidate-only drill ideas derived from external prompt pattern counts.
They are not active runtime rules. A candidate becomes active only after a real
test is implemented, validation passes, and Evolution OS promotion records a
rollbackable receipt.

## Candidates
{drill_lines}

```json
{json.dumps(drill_candidates, ensure_ascii=False, indent=2, sort_keys=True)}
```
""",
        encoding="utf-8",
    )

    policy = paths.wiki_dir / "policies" / "external-prompt-corpus-boundary.md"
    if not policy.exists():
        policy.write_text(
            f"""---
title: External Prompt Corpus Boundary
created: {wg.today()}
updated: {wg.today()}
type: policy
status: verified
tags: [miho, governance, external-prompts, license-boundary]
sources: []
---

# External Prompt Corpus Boundary

External prompt repositories are reference material for Miho governance analysis.
They must stay out of Miho runtime prompts unless separately reviewed for
license, provenance, safety, and product fit.

Allowed: paths, hashes, source URLs, license notes, section names, and pattern
counts. Disallowed: copying full third-party prompt bodies into Miho system
prompts, bundled skills, or generated policy pages.
""",
            encoding="utf-8",
        )
