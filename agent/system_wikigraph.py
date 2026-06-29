"""Miho System WikiGraph: local system wiki + graph inventory.

This module builds a conservative, local "digital twin" of a Miho install.  It
keeps source-of-truth files where they already live, then records a searchable
wiki scaffold and a SQLite graph of code files, tests, skills, tools, config
references, and evolution events.

Privacy rule: never copy secret values or user/student data into the wiki/graph.
Only paths, hashes, structural summaries, and safe metadata are stored.
"""

from __future__ import annotations

import ast
import hashlib
import html
import json
import math
import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from miho_constants import get_miho_home

SYSTEM_WIKI_DIRNAME = "system_wiki"
SYSTEM_GRAPH_DIRNAME = "system_graph"
GRAPH_DB_NAME = "graph.db"

TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".sh",
    ".ini",
    ".cfg",
}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".pytest-cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".tox",
    ".eggs",
}

SENSITIVE_NAME_PARTS = {
    ".env",
    "secret",
    "token",
    "credential",
    "credentials",
    "keyfile",
    "private_key",
}

CONFIG_SAFE_NAMES = {
    "config.yaml",
    "cli-config.yaml",
    "cli-config.yaml.example",
    ".env.example",
    "pyproject.toml",
    "package.json",
}

COMPONENT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("gateway/", "gateway"),
    ("plugins/governance_os/", "governance"),
    ("tools/", "tools"),
    ("agent/", "agent"),
    ("miho_cli/", "cli"),
    ("cron/", "cron"),
    ("skills/", "bundled-skills"),
    ("optional-skills/", "optional-skills"),
    ("tests/", "tests"),
    ("docs/", "docs"),
    ("gateway/platforms/", "gateway-platforms"),
    ("ui-tui/", "tui"),
    ("tui_gateway/", "tui-gateway"),
)

RISK_COMPONENTS = {"gateway", "governance", "tools", "agent", "cron", "gateway-platforms"}


@dataclass(frozen=True)
class SystemPaths:
    miho_home: Path
    wiki_dir: Path
    graph_dir: Path
    db_path: Path


def system_paths() -> SystemPaths:
    home = get_miho_home()
    graph_dir = home / SYSTEM_GRAPH_DIRNAME
    return SystemPaths(
        miho_home=home,
        wiki_dir=home / SYSTEM_WIKI_DIRNAME,
        graph_dir=graph_dir,
        db_path=graph_dir / GRAPH_DB_NAME,
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def slug_for(value: str) -> str:
    out = []
    for ch in value.lower():
        if ch.isalnum() or ch in {"-", "_"}:
            out.append(ch)
        elif ch in {"/", " ", ".", ":"}:
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "item"


def is_probably_sensitive(path: Path) -> bool:
    lowered = str(path).lower()
    name = path.name.lower()
    if name in CONFIG_SAFE_NAMES:
        return False
    return any(part in lowered for part in SENSITIVE_NAME_PARTS)


def is_indexable_file(path: Path) -> bool:
    if is_probably_sensitive(path):
        return False
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return False
    try:
        if path.stat().st_size > 2_000_000:
            return False
    except OSError:
        return False
    return True


def iter_project_files(project_root: Path) -> Iterator[Path]:
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        root_path = Path(root)
        for filename in files:
            path = root_path / filename
            if is_indexable_file(path):
                yield path


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_read(path: Path, *, max_chars: int = 180_000) -> str:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return raw[:max_chars]


def classify_component(rel_path: str) -> str:
    normalized = rel_path.replace(os.sep, "/")
    best = "root"
    best_len = -1
    for prefix, component in COMPONENT_PREFIXES:
        if normalized.startswith(prefix) and len(prefix) > best_len:
            best = component
            best_len = len(prefix)
    return best


def risk_for(component: str, rel_path: str) -> str:
    if component in RISK_COMPONENTS:
        return "high"
    if rel_path.endswith((".md", ".txt")) or component in {"docs", "tests"}:
        return "low"
    return "medium"


def ast_symbols(path: Path) -> list[str]:
    if path.suffix != ".py":
        return []
    source = safe_read(path)
    if not source:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
    return symbols[:80]


def infer_tool_names(path: Path) -> list[str]:
    if path.suffix != ".py":
        return []
    source = safe_read(path, max_chars=220_000)
    names: set[str] = set()
    for match in re.finditer(r"registry\.register\(\s*name\s*=\s*['\"]([^'\"]+)['\"]", source, re.DOTALL):
        names.add(match.group(1))
    for marker in ("registry.register(", "register_tool("):
        if marker in source:
            # Backward-compatible best-effort for single-line registrations.
            for line in source.splitlines():
                if marker in line and ("name=" in line or "'" in line or '"' in line):
                    for quote in ("'", '"'):
                        parts = line.split(quote)
                        if len(parts) >= 3 and parts[1].replace("_", "").replace("-", "").isalnum():
                            names.add(parts[1])
                            break
    if path.name.endswith("_tool.py"):
        names.add(path.stem)
    return sorted(names)[:80]


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT DEFAULT '',
            path TEXT DEFAULT '',
            component TEXT DEFAULT '',
            risk TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'observed',
            hash TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            target_id TEXT NOT NULL,
            status TEXT DEFAULT 'inferred',
            confidence REAL DEFAULT 0.5,
            evidence TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_id, relation, target_id)
        );
        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            project_root TEXT DEFAULT '',
            changed_files_json TEXT DEFAULT '[]',
            summary_json TEXT DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
        CREATE INDEX IF NOT EXISTS idx_nodes_component ON nodes(component);
        CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
        """
    )
    conn.commit()


def connect() -> sqlite3.Connection:
    paths = system_paths()
    paths.graph_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(paths.db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def upsert_node(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    node_type: str,
    title: str,
    summary: str = "",
    path: str = "",
    component: str = "",
    risk: str = "medium",
    status: str = "observed",
    content_hash: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO nodes(id, type, title, summary, path, component, risk, status, hash, metadata_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            type=excluded.type,
            title=excluded.title,
            summary=excluded.summary,
            path=excluded.path,
            component=excluded.component,
            risk=excluded.risk,
            status=excluded.status,
            hash=excluded.hash,
            metadata_json=excluded.metadata_json,
            updated_at=excluded.updated_at
        """,
        (
            node_id,
            node_type,
            title,
            summary,
            path,
            component,
            risk,
            status,
            content_hash,
            json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            now,
            now,
        ),
    )


def upsert_edge(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    relation: str,
    target_id: str,
    status: str = "inferred",
    confidence: float = 0.5,
    evidence: str = "",
) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO edges(source_id, relation, target_id, status, confidence, evidence, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id, relation, target_id) DO UPDATE SET
            status=excluded.status,
            confidence=excluded.confidence,
            evidence=excluded.evidence,
            updated_at=excluded.updated_at
        """,
        (source_id, relation, target_id, status, float(confidence), evidence, now, now),
    )


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def append_log(message: str) -> None:
    paths = system_paths()
    paths.wiki_dir.mkdir(parents=True, exist_ok=True)
    log = paths.wiki_dir / "log.md"
    if not log.exists():
        log.write_text("# Miho System WikiGraph Log\n\n", encoding="utf-8")
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n## [{today()}] {message}\n")


def init_wiki() -> dict[str, Any]:
    paths = system_paths()
    paths.wiki_dir.mkdir(parents=True, exist_ok=True)
    paths.graph_dir.mkdir(parents=True, exist_ok=True)
    for sub in (
        "architecture",
        "governance",
        "gateway",
        "tools",
        "skills",
        "templates",
        "tests",
        "failures",
        "policies",
        "raw",
        "maps",
    ):
        (paths.wiki_dir / sub).mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    schema = f"""# Miho System WikiGraph Schema

## Domain
This wiki covers the local Miho system itself: codebase structure, tools, skills,
templates, tests, governance rules, evolution events, failures, config surfaces,
and update relationships.

## Source of truth
- Code source: `/Users/etlab/projects/miho-ai/`
- Runtime state: `~/.miho/`
- Evolution ledger: `~/.miho/evolution/events.jsonl`
- Graph database: `~/.miho/system_graph/graph.db`

The WikiGraph is an index and judgment map. It does not replace code, tests,
logs, or explicit user instructions.

## Privacy boundary
Do not copy secrets, `.env` values, student data, phone numbers, counseling
notes, raw school records, or private Discord logs into wiki pages. Store only
safe paths, hashes, anonymized summaries, source references, and structural
metadata.

## Node status
- observed: directly observed from filesystem, config, or ledger
- inferred: relationship inferred from path/name/import/test convention
- verified: backed by a passing test, explicit event, or direct source evidence
- stale: likely outdated and needs resync/review
- deprecated: intentionally superseded

## Required page frontmatter
```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: architecture | governance | gateway | tool | skill | template | test | failure | policy | map
status: observed | inferred | verified | stale | deprecated
tags: []
sources: []
---
```

## Graph relation vocabulary
- contains
- affects
- depends_on
- validates
- validated_by
- documents
- documented_in
- mitigates
- caused_by
- changed_by
- requires_test
- related_to
- owns

## Update policy
Every substantial Miho code/config/skill/tool change should run:

```bash
miho evolution wikigraph sync --from-git
```

Low-risk observations may be recorded automatically. Rule/skill/governance
promotions still need validation through Evolution OS and tests.
"""
    index = f"""# Miho System WikiGraph Index

> Local digital twin map for Miho. Read this before changing Miho internals.
> Last updated: {today()}

## Core maps
- [[architecture/system-overview]] — high-level runtime and source map.
- [[governance/governance-os-map]] — governance, self-harness, readiness, and failure loop map.
- [[gateway/gateway-delivery-map]] — gateway and Discord delivery surfaces.
- [[tools/tool-registry-map]] — tool registry and tool-safety surfaces.
- [[skills/skill-system-map]] — skill storage, curator, and mutation map.
- [[tests/test-impact-map]] — test selection and impact conventions.
- [[policies/privacy-and-source-boundary]] — what may and may not enter the WikiGraph.

## Generated inventories
Run `miho evolution wikigraph sync --full` to populate graph.db with code, tests,
skills, tools, configs, and evolution events.
"""
    overview = f"""---
title: Miho Runtime System Overview
created: {today()}
updated: {today()}
type: architecture
status: observed
tags: [miho, architecture, wikigraph]
sources: [/Users/etlab/projects/miho-ai/AGENTS.md]
---

# Miho Runtime System Overview

Miho runs from the local codebase and keeps runtime state under `~/.miho`.
This page is the human-readable entry point; exact file inventory and relations
live in `~/.miho/system_graph/graph.db`.

## Source anchors
- `run_agent.py` — core agent loop.
- `model_tools.py` and `tools/registry.py` — tool discovery and execution.
- `miho_cli/` and `cli.py` — CLI and slash command routing.
- `gateway/` — Discord and messaging delivery.
- `plugins/governance_os/` — governance runtime.
- `agent/evolution*.py` — evolution ledger, training, immunity, rollback.
- `~/.miho/skills/` — user/runtime skill tree.

## Linked maps
See [[governance/governance-os-map]], [[gateway/gateway-delivery-map]],
[[tools/tool-registry-map]], and [[tests/test-impact-map]].
"""
    governance = f"""---
title: Miho Governance OS Map
created: {today()}
updated: {today()}
type: governance
status: observed
tags: [miho, governance, evolution]
sources: [agent/evolution.py, plugins/governance_os]
---

# Miho Governance OS Map

Governance protects Miho changes with readiness checks, drills, final delivery
rules, proposal/promotion flow, and rollbackable skill snapshots.

## Operating principle
LLM-centered semantic judgment is preferred for meaning. If the semantic judge is
unavailable, the system should fail visibly/closed rather than substituting a
Python keyword fallback for meaning.

## Graph anchors
- `component:governance`
- `component:agent`
- `event:*` from `~/.miho/evolution/events.jsonl`
- `rule:*` from `~/.miho/evolution/harness_rules.json`

## Required update habit
After governance code, skill, or test changes, run `miho evolution wikigraph sync --from-git`.
"""
    gateway = f"""---
title: Gateway Delivery Map
created: {today()}
updated: {today()}
type: gateway
status: observed
tags: [miho, gateway, discord, delivery]
sources: [gateway]
---

# Gateway Delivery Map

Gateway files control Discord and other messaging delivery. This surface is high
risk because a completed run can still fail the user if final delivery, media
resolution, restart drain, or context recovery breaks.

## Watch points
- Long-running runs must not fail silently.
- MEDIA paths must stay inside configured safe roots.
- Restart/drain behavior must preserve visible final/checkpoint delivery.

## Related maps
See [[governance/governance-os-map]] and [[tests/test-impact-map]].
"""
    tools_page = f"""---
title: Tool Registry Map
created: {today()}
updated: {today()}
type: tool
status: observed
tags: [miho, tools, registry]
sources: [tools/registry.py, model_tools.py]
---

# Tool Registry Map

Tool execution flows through the registry/discovery chain. The graph stores tool
files and best-effort tool nodes without copying secrets or private data.

## Privacy boundary
Tool schemas and safe names are indexable. Runtime API keys, `.env` values, raw
student records, and private logs are not.
"""
    skills_page = f"""---
title: Skill System Map
created: {today()}
updated: {today()}
type: skill
status: observed
tags: [miho, skills, curator]
sources: [~/.miho/skills, skills]
---

# Skill System Map

Runtime skills live under `~/.miho/skills/`; bundled skills live in the repo.
Skill mutations should be recorded in Evolution OS with snapshots when possible.

## Related maps
See [[governance/governance-os-map]] and [[policies/privacy-and-source-boundary]].
"""
    tests_page = f"""---
title: Test Impact Map
created: {today()}
updated: {today()}
type: test
status: observed
tags: [miho, tests, impact]
sources: [tests]
---

# Test Impact Map

The graph links files to nearby tests by component and naming convention. These
relations are `inferred` until a test receipt or explicit source verifies them.

## Conservative defaults
- gateway changes require gateway/e2e delivery tests when available.
- governance changes require `tests/plugins/test_governance_os*.py` focus tests.
- tool registry changes require tool and registry tests.
"""
    privacy = f"""---
title: Privacy and Source Boundary
created: {today()}
updated: {today()}
type: policy
status: verified
tags: [miho, privacy, source-boundary]
sources: []
---

# Privacy and Source Boundary

The WikiGraph indexes Miho's system structure, not private user/student data.

## Never copy into the wiki/graph
- `.env` values, provider keys, bot tokens, passwords.
- Student names paired with private records, phone numbers, counseling notes.
- Raw school records, attendance/payment details, Discord private message bodies.
- Full logs that may contain secrets.

## Allowed
- Safe file paths and hashes.
- Structural summaries, components, relation types, and test names.
- Anonymized failure patterns and explicit operational rules.
"""

    files = {
        "SCHEMA.md": schema,
        "index.md": index,
        "architecture/system-overview.md": overview,
        "governance/governance-os-map.md": governance,
        "gateway/gateway-delivery-map.md": gateway,
        "tools/tool-registry-map.md": tools_page,
        "skills/skill-system-map.md": skills_page,
        "tests/test-impact-map.md": tests_page,
        "policies/privacy-and-source-boundary.md": privacy,
    }
    for rel, content in files.items():
        path = paths.wiki_dir / rel
        if write_if_missing(path, content):
            created.append(str(path))
    conn = connect()
    try:
        upsert_node(conn, node_id="wiki:system", node_type="Wiki", title="Miho System Wiki", path=str(paths.wiki_dir), component="wikigraph", risk="low", status="verified")
        upsert_node(conn, node_id="graph:system", node_type="Graph", title="Miho System Graph", path=str(paths.db_path), component="wikigraph", risk="low", status="verified")
        upsert_edge(conn, source_id="wiki:system", relation="documents", target_id="graph:system", status="verified", confidence=1.0, evidence="wikigraph init")
        conn.commit()
    finally:
        conn.close()
    append_log("create | System WikiGraph initialized")
    return {"success": True, "wiki_dir": str(paths.wiki_dir), "db_path": str(paths.db_path), "created": created}


def project_root_from(path: str | Path | None = None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    return Path.cwd().resolve()


def git_changed_files(project_root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=project_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return []
    changed: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        # Handles " M path", "A  path", "R old -> new", "?? path".
        rest = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        if rest:
            changed.append(rest)
    return changed


def sync_project(*, project_root: str | Path | None = None, full: bool = False, from_git: bool = False) -> dict[str, Any]:
    init_wiki()
    root = project_root_from(project_root)
    changed = git_changed_files(root) if from_git else []
    files: list[Path]
    if from_git and changed and not full:
        files = [root / rel for rel in changed if is_indexable_file(root / rel)]
    else:
        files = list(iter_project_files(root))
    conn = connect()
    started = utc_now()
    cur = conn.execute(
        "INSERT INTO sync_runs(started_at, project_root, changed_files_json) VALUES (?, ?, ?)",
        (started, str(root), json.dumps(changed, ensure_ascii=False)),
    )
    sync_id = int(cur.lastrowid or 0)
    stats = {"files": 0, "tests": 0, "tools": 0, "skills": 0, "events": 0, "configs": 0, "edges": 0}
    try:
        for path in files:
            if not path.exists() or not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            component = classify_component(rel)
            symbols = ast_symbols(path)
            try:
                line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                line_count = 0
            node_type = "Test" if rel.startswith("tests/") else "CodeFile"
            if rel.startswith(("skills/", "optional-skills/")) and path.name == "SKILL.md":
                node_type = "Skill"
            if path.name in CONFIG_SAFE_NAMES:
                node_type = "Config"
            node_id = f"{node_type.lower()}:{rel}"
            upsert_node(
                conn,
                node_id=node_id,
                node_type=node_type,
                title=rel,
                summary=f"{component} {path.suffix or 'file'}; {line_count} lines",
                path=str(path),
                component=component,
                risk=risk_for(component, rel),
                status="observed",
                content_hash=file_hash(path),
                metadata={"symbols": symbols, "lines": line_count, "extension": path.suffix},
            )
            stats["files"] += 1
            if node_type == "Test":
                stats["tests"] += 1
                upsert_edge(conn, source_id=node_id, relation="validates", target_id=f"component:{component}", status="inferred", confidence=0.55, evidence="test path convention")
                stats["edges"] += 1
            if node_type == "Skill":
                stats["skills"] += 1
                upsert_edge(conn, source_id=node_id, relation="documents", target_id=f"component:{component}", status="observed", confidence=0.7, evidence="bundled skill file")
                stats["edges"] += 1
            if node_type == "Config":
                stats["configs"] += 1
            component_id = f"component:{component}"
            upsert_node(conn, node_id=component_id, node_type="Component", title=component, component=component, risk="high" if component in RISK_COMPONENTS else "medium", status="observed")
            upsert_edge(conn, source_id=component_id, relation="contains", target_id=node_id, status="observed", confidence=0.85, evidence="path prefix classification")
            stats["edges"] += 1
            for tool in infer_tool_names(path):
                tool_id = f"tool:{tool}"
                upsert_node(conn, node_id=tool_id, node_type="Tool", title=tool, path=str(path), component=component, risk=risk_for(component, rel), status="inferred")
                upsert_edge(conn, source_id=tool_id, relation="owned_by", target_id=node_id, status="inferred", confidence=0.6, evidence="tool registration/file naming convention")
                stats["tools"] += 1
                stats["edges"] += 1
            if rel.startswith("tests/"):
                continue
            conn.execute("DELETE FROM edges WHERE source_id=? AND relation='requires_test'", (node_id,))
            related_tests = infer_related_tests(root, rel, component)
            for test_rel in related_tests[:20]:
                test_id = f"test:{test_rel}"
                upsert_edge(conn, source_id=node_id, relation="requires_test", target_id=test_id, status="inferred", confidence=0.5, evidence="component/name-based test selection")
                stats["edges"] += 1
        stats["events"] = ingest_evolution_events(conn)
        ingest_runtime_skills(conn, stats)
        summary = dict(stats)
        conn.execute(
            "UPDATE sync_runs SET finished_at=?, summary_json=? WHERE id=?",
            (utc_now(), json.dumps(summary, ensure_ascii=False, sort_keys=True), sync_id),
        )
        conn.commit()
    finally:
        conn.close()
    append_log(f"sync | project={root} files={stats['files']} events={stats['events']} from_git={from_git} full={full}")
    update_inventory_pages(stats, root, changed)
    return {"success": True, "sync_id": sync_id, "project_root": str(root), "changed_files": changed, "summary": stats, "wiki_dir": str(system_paths().wiki_dir), "db_path": str(system_paths().db_path)}


def infer_related_tests(root: Path, rel: str, component: str) -> list[str]:
    tests_dir = root / "tests"
    if not tests_dir.exists():
        return []
    base = Path(rel).stem.replace("test_", "")
    component_aliases = {component.replace("-", "_")}
    if component.startswith("gateway"):
        component_aliases.add("gateway")
    if component == "governance":
        component_aliases.update({"governance", "governance_os"})
    if component == "tools":
        component_aliases.update({"tool", "tools", "registry"})

    scored: dict[str, int] = {}
    generic_names = {"base", "utils", "helpers", "common", "main", "__init__"}
    for test in iter_project_files(tests_dir):
        if test.suffix != ".py" or not test.name.startswith("test_"):
            continue
        test_rel = test.relative_to(root).as_posix()
        low = test_rel.lower().replace("-", "_")
        score = 0
        if any(alias and alias in low for alias in component_aliases):
            score += 30
        if component == "gateway" and "gateway" in low:
            score += 30
        if component.startswith("gateway") and "gateway" in low:
            score += 30
        if component == "governance" and "governance_os" in low:
            score += 40
        if base and base.lower() not in generic_names and base.lower() in low:
            score += 10
        if score:
            scored[test_rel] = score
    return [item for item, _score in sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))[:60]]


def ingest_evolution_events(conn: sqlite3.Connection) -> int:
    events_path = get_miho_home() / "evolution" / "events.jsonl"
    if not events_path.exists():
        return 0
    count = 0
    with events_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_id = f"event:{event.get('id')}"
            title = str(event.get("title") or event_id)
            kind = str(event.get("kind") or "event")
            upsert_node(
                conn,
                node_id=event_id,
                node_type="EvolutionEvent",
                title=title,
                summary=str(event.get("summary") or "")[:500],
                component="evolution",
                risk="medium",
                status=str(event.get("status") or "observed"),
                metadata={"kind": kind, "created_at": event.get("created_at"), "proposal_id": event.get("proposal_id")},
            )
            for changed in event.get("changed_files") or []:
                changed_id = f"codefile:{changed}"
                upsert_edge(conn, source_id=event_id, relation="changed_by", target_id=changed_id, status="observed", confidence=0.75, evidence="evolution ledger changed_files")
            count += 1
    return count


def ingest_runtime_skills(conn: sqlite3.Connection, stats: dict[str, int]) -> None:
    skills_root = get_miho_home() / "skills"
    if not skills_root.exists():
        return
    for skill_md in skills_root.rglob("SKILL.md"):
        if is_probably_sensitive(skill_md):
            continue
        rel = skill_md.relative_to(skills_root).as_posix()
        skill_name = skill_md.parent.name
        node_id = f"skill:{skill_name}"
        content = safe_read(skill_md, max_chars=80_000)
        upsert_node(
            conn,
            node_id=node_id,
            node_type="Skill",
            title=skill_name,
            summary=_first_heading_or_description(content),
            path=str(skill_md),
            component="runtime-skills",
            risk="medium",
            status="observed",
            content_hash=file_hash(skill_md),
            metadata={"relative_path": rel},
        )
        upsert_edge(conn, source_id="component:runtime-skills", relation="contains", target_id=node_id, status="observed", confidence=0.9, evidence="runtime skill tree")
        stats["skills"] += 1
        stats["edges"] += 1


def _first_heading_or_description(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("description:"):
            return stripped.split(":", 1)[1].strip().strip('"')[:300]
        if stripped.startswith("# "):
            return stripped[2:].strip()[:300]
    return ""


def update_inventory_pages(stats: dict[str, int], root: Path, changed: Sequence[str]) -> None:
    paths = system_paths()
    raw = paths.wiki_dir / "raw" / "source-inventory.md"
    content = f"""---
title: Source Inventory
created: {today()}
updated: {today()}
type: map
status: observed
tags: [miho, inventory, sources]
sources: [{root}]
---

# Source Inventory

Last sync: {utc_now()}

## Project root
`{root}`

## Runtime roots
- Wiki: `{paths.wiki_dir}`
- Graph: `{paths.db_path}`
- Miho home: `{paths.miho_home}`

## Last sync summary
```json
{json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True)}
```

## Changed files from git
"""
    if changed:
        content += "\n".join(f"- `{item}`" for item in changed) + "\n"
    else:
        content += "- none or not requested\n"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(content, encoding="utf-8")

    index = paths.wiki_dir / "index.md"
    if index.exists():
        txt = index.read_text(encoding="utf-8")
        marker = "> Last updated:"
        lines = txt.splitlines()
        for i, line in enumerate(lines):
            if line.startswith(marker):
                lines[i] = f"> Last updated: {today()}"
        index.write_text("\n".join(lines) + "\n", encoding="utf-8")


def graph_status() -> dict[str, Any]:
    paths = system_paths()
    init_wiki()
    conn = connect()
    try:
        node_counts = {row["type"]: int(row["count"]) for row in conn.execute("SELECT type, COUNT(*) AS count FROM nodes GROUP BY type ORDER BY type")}
        edge_counts = {row["relation"]: int(row["count"]) for row in conn.execute("SELECT relation, COUNT(*) AS count FROM edges GROUP BY relation ORDER BY relation")}
        sync = conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
        last_sync = dict(sync) if sync else None
    finally:
        conn.close()
    return {"success": True, "wiki_dir": str(paths.wiki_dir), "db_path": str(paths.db_path), "node_counts": node_counts, "edge_counts": edge_counts, "last_sync": last_sync}


def impact(query: str, *, limit: int = 40) -> dict[str, Any]:
    init_wiki()
    q = (query or "").strip()
    if not q:
        raise ValueError("query is required")
    conn = connect()
    try:
        like = f"%{q}%"
        nodes = [dict(row) for row in conn.execute(
            "SELECT * FROM nodes WHERE id LIKE ? OR title LIKE ? OR path LIKE ? OR component LIKE ? ORDER BY risk DESC, type, title LIMIT ?",
            (like, like, like, like, int(limit)),
        )]
        node_ids = [n["id"] for n in nodes]
        edges: list[dict[str, Any]] = []
        if node_ids:
            placeholders = ",".join("?" for _ in node_ids)
            sql = f"SELECT * FROM edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders}) ORDER BY confidence DESC LIMIT ?"
            edges = [dict(row) for row in conn.execute(sql, (*node_ids, *node_ids, int(limit) * 3))]
    finally:
        conn.close()
    return {"success": True, "query": q, "nodes": nodes, "edges": edges}


def render_impact_text(result: dict[str, Any]) -> str:
    lines = [f"WikiGraph impact: {result.get('query')}"]
    nodes = result.get("nodes") or []
    if not nodes:
        return lines[0] + "\n  no matching nodes"
    lines.append("Nodes:")
    for n in nodes[:20]:
        lines.append(f"  - {n.get('id')} [{n.get('type')}] component={n.get('component') or '-'} risk={n.get('risk')}")
    edges = result.get("edges") or []
    if edges:
        lines.append("Edges:")
        for e in edges[:40]:
            lines.append(f"  - {e.get('source_id')} --{e.get('relation')}--> {e.get('target_id')} ({e.get('status')}, {e.get('confidence')})")
    return "\n".join(lines)


def status_text(status: dict[str, Any]) -> str:
    lines = ["Miho System WikiGraph: ENABLED", f"  wiki: {status['wiki_dir']}", f"  graph: {status['db_path']}"]
    lines.append("  nodes:")
    for k, v in sorted((status.get("node_counts") or {}).items()):
        lines.append(f"    {k}: {v}")
    lines.append("  edges:")
    for k, v in sorted((status.get("edge_counts") or {}).items()):
        lines.append(f"    {k}: {v}")
    last = status.get("last_sync")
    if last:
        lines.append(f"  last_sync: #{last.get('id')} {last.get('finished_at') or last.get('started_at')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Automation, GraphRAG, and visualization
# ---------------------------------------------------------------------------

HOOK_NAMES = ("post-commit", "post-merge", "post-checkout", "post-rewrite")


def _find_repo_root(project_root: str | Path | None = None) -> Path:
    root = project_root_from(project_root)
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return Path(proc.stdout.strip()).resolve()
    except (OSError, subprocess.CalledProcessError):
        return root


def install_git_hooks(*, project_root: str | Path | None = None, force: bool = False) -> dict[str, Any]:
    """Install local git hooks that keep WikiGraph synced after external edits.

    Hooks are deliberately local to this checkout. They do not get committed and
    they never block a git operation; failures are logged under ~/.miho/logs.
    """
    repo = _find_repo_root(project_root)
    git_dir_proc = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if git_dir_proc.returncode != 0:
        raise RuntimeError(f"not a git repository: {repo}")
    git_dir = Path(git_dir_proc.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = repo / git_dir
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    miho_bin = os.environ.get("MIHO_WIKIGRAPH_MIHO_BIN") or "miho"
    log_path = get_miho_home() / "logs" / "system_wikigraph_hooks.log"
    installed: list[str] = []
    skipped: list[str] = []
    marker = "# MIHO_SYSTEM_WIKIGRAPH_HOOK"
    script = f"""#!/bin/sh
{marker}
# Auto-generated by Miho System WikiGraph. Local hook; safe to edit/remove.
MIHO_WIKIGRAPH_PROJECT_ROOT={sh_quote(str(repo))}
export MIHO_WIKIGRAPH_PROJECT_ROOT
mkdir -p {sh_quote(str(log_path.parent))}
(
  cd {sh_quote(str(repo))} || exit 0
  {sh_quote(miho_bin)} evolution wikigraph sync --full --project-root {sh_quote(str(repo))}
) >> {sh_quote(str(log_path))} 2>&1 || true
"""
    for hook in HOOK_NAMES:
        path = hooks_dir / hook
        if path.exists():
            existing = path.read_text(encoding="utf-8", errors="replace")
            if marker not in existing and not force:
                skipped.append(str(path))
                continue
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)
        installed.append(str(path))
    append_log(f"automation | installed git hooks repo={repo} installed={len(installed)} skipped={len(skipped)}")
    return {"success": True, "repo": str(repo), "installed": installed, "skipped": skipped, "log_path": str(log_path)}


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def watch_once(*, project_root: str | Path | None = None) -> dict[str, Any]:
    """Run one change-aware sync pass. Useful for cron/watchdog integration."""
    return sync_project(project_root=project_root, from_git=True)


def graphrag(query: str, *, hops: int = 2, limit: int = 80) -> dict[str, Any]:
    """Return a compact graph-expanded answer substrate for Miho self-queries."""
    seed = impact(query, limit=limit)
    seed_ids = [n["id"] for n in seed.get("nodes") or []]
    conn = connect()
    try:
        seen = set(seed_ids)
        frontier = set(seed_ids)
        all_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        for _ in range(max(0, int(hops))):
            if not frontier:
                break
            placeholders = ",".join("?" for _ in frontier)
            sql = f"SELECT * FROM edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders}) ORDER BY confidence DESC LIMIT ?"
            rows = [dict(row) for row in conn.execute(sql, (*frontier, *frontier, int(limit) * 6))]
            next_frontier: set[str] = set()
            for row in rows:
                key = (row["source_id"], row["relation"], row["target_id"])
                all_edges[key] = row
                for node_id in (row["source_id"], row["target_id"]):
                    if node_id not in seen:
                        seen.add(node_id)
                        next_frontier.add(node_id)
            frontier = next_frontier
        node_rows: list[dict[str, Any]] = []
        if seen:
            ids = sorted(seen)[: max(int(limit) * 4, int(limit))]
            placeholders = ",".join("?" for _ in ids)
            node_rows = [dict(row) for row in conn.execute(f"SELECT * FROM nodes WHERE id IN ({placeholders})", ids)]
    finally:
        conn.close()
    wiki_hits = _wiki_hits(query, limit=12)
    risks = sorted(
        (n for n in node_rows if n.get("risk") == "high"),
        key=lambda n: (n.get("type") or "", n.get("id") or ""),
    )[:20]
    tests = sorted((n for n in node_rows if n.get("type") == "Test"), key=lambda n: n.get("id") or "")[:30]
    return {
        "success": True,
        "query": query,
        "seed_nodes": seed.get("nodes") or [],
        "nodes": node_rows,
        "edges": list(all_edges.values()),
        "wiki_hits": wiki_hits,
        "high_risk_nodes": risks,
        "related_tests": tests,
    }


def _wiki_hits(query: str, *, limit: int = 12) -> list[dict[str, str]]:
    paths = system_paths()
    q = query.lower().strip()
    hits: list[dict[str, str]] = []
    if not paths.wiki_dir.exists():
        return hits
    for md in paths.wiki_dir.rglob("*.md"):
        rel = md.relative_to(paths.wiki_dir).as_posix()
        text = safe_read(md, max_chars=60_000)
        haystack = (rel + "\n" + text).lower()
        score = haystack.count(q) if q else 0
        if score or any(part and part in haystack for part in q.split()):
            title = rel
            for line in text.splitlines():
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip()
                    break
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            hits.append({"path": str(md), "relative_path": rel, "title": title, "score": str(score)})
        if len(hits) >= limit:
            break
    return hits


def render_graphrag_text(result: dict[str, Any]) -> str:
    lines = [f"WikiGraph GraphRAG: {result.get('query')}"]
    lines.append(f"  nodes={len(result.get('nodes') or [])} edges={len(result.get('edges') or [])} wiki_hits={len(result.get('wiki_hits') or [])}")
    if result.get("high_risk_nodes"):
        lines.append("High-risk nodes:")
        for n in result["high_risk_nodes"][:12]:
            lines.append(f"  - {n.get('id')} [{n.get('type')}] component={n.get('component')}")
    if result.get("related_tests"):
        lines.append("Related tests:")
        for n in result["related_tests"][:12]:
            lines.append(f"  - {n.get('id')}")
    if result.get("wiki_hits"):
        lines.append("Wiki pages:")
        for hit in result["wiki_hits"][:8]:
            lines.append(f"  - {hit.get('relative_path')} — {hit.get('title')}")
    return "\n".join(lines)


def render_graph_html(query: str, *, output_path: str | Path | None = None, limit: int = 90) -> dict[str, Any]:
    """Render a self-contained HTML/SVG graph map for the query."""
    result = graphrag(query, hops=2, limit=limit)
    nodes = result.get("nodes") or []
    edges = result.get("edges") or []
    selected_edges = edges[: min(len(edges), 140)]
    node_ids: list[str] = []
    for edge in selected_edges:
        for node_id in (edge.get("source_id"), edge.get("target_id")):
            if node_id and node_id not in node_ids:
                node_ids.append(node_id)
    for node in nodes:
        if len(node_ids) >= limit:
            break
        if node.get("id") not in node_ids:
            node_ids.append(node.get("id"))
    node_map = {n.get("id"): n for n in nodes}
    n = max(1, len(node_ids))
    width, height = 1500, 1000
    cx, cy = width / 2, height / 2
    radius = min(width, height) * 0.38
    positions: dict[str, tuple[float, float]] = {}
    for i, node_id in enumerate(node_ids):
        angle = 2 * math.pi * i / n
        positions[node_id] = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
    colors = {
        "CodeFile": "#60a5fa",
        "Test": "#34d399",
        "Skill": "#c084fc",
        "Tool": "#fbbf24",
        "EvolutionEvent": "#fb7185",
        "Component": "#f97316",
        "Config": "#94a3b8",
        "Wiki": "#22d3ee",
        "Graph": "#22d3ee",
    }
    edge_svg = []
    for edge in selected_edges:
        s, t = edge.get("source_id"), edge.get("target_id")
        if s not in positions or t not in positions:
            continue
        x1, y1 = positions[s]
        x2, y2 = positions[t]
        edge_svg.append(
            f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' stroke='rgba(148,163,184,.36)' stroke-width='1.2'><title>{html.escape(str(edge.get('relation')))}</title></line>"
        )
    node_svg = []
    for node_id in node_ids:
        node = node_map.get(node_id, {"id": node_id, "type": "Unknown", "risk": "medium"})
        x, y = positions[node_id]
        typ = str(node.get("type") or "Unknown")
        color = colors.get(typ, "#e5e7eb")
        stroke = "#ef4444" if node.get("risk") == "high" else "#0f172a"
        label = _short_label(node_id)
        node_svg.append(
            f"<g><circle cx='{x:.1f}' cy='{y:.1f}' r='16' fill='{color}' stroke='{stroke}' stroke-width='2'><title>{html.escape(node_id)}\n{html.escape(str(node.get('summary') or ''))}</title></circle>"
            f"<text x='{x + 20:.1f}' y='{y + 4:.1f}' font-size='12' fill='#e5e7eb'>{html.escape(label)}</text></g>"
        )
    rows = []
    for node in nodes[:60]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(node.get('type') or ''))}</td>"
            f"<td>{html.escape(str(node.get('id') or ''))}</td>"
            f"<td>{html.escape(str(node.get('component') or ''))}</td>"
            f"<td>{html.escape(str(node.get('risk') or ''))}</td>"
            "</tr>"
        )
    doc = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Miho WikiGraph — {html.escape(query)}</title>
<style>
body{{margin:0;background:#0b1020;color:#e5e7eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
.wrap{{padding:28px}} h1{{margin:0 0 6px;font-size:30px}} .sub{{color:#94a3b8;margin-bottom:18px}}
svg{{width:100%;height:auto;background:radial-gradient(circle at center,#172554,#020617);border:1px solid #1e293b;border-radius:22px}}
table{{width:100%;border-collapse:collapse;margin-top:22px;font-size:13px}} th,td{{border-bottom:1px solid #1e293b;padding:9px 10px;text-align:left;vertical-align:top}} th{{color:#93c5fd}}
.badge{{display:inline-block;background:#1e293b;border:1px solid #334155;padding:5px 9px;border-radius:999px;margin-right:6px;color:#cbd5e1}}
</style></head><body><div class='wrap'>
<h1>Miho System WikiGraph</h1><div class='sub'>Query: <b>{html.escape(query)}</b></div>
<div><span class='badge'>nodes {len(nodes)}</span><span class='badge'>edges {len(edges)}</span><span class='badge'>wiki hits {len(result.get('wiki_hits') or [])}</span></div>
<svg viewBox='0 0 {width} {height}' role='img' aria-label='Miho WikiGraph map'>
<defs><marker id='arrow' markerWidth='10' markerHeight='10' refX='9' refY='3' orient='auto' markerUnits='strokeWidth'><path d='M0,0 L0,6 L9,3 z' fill='#64748b'/></marker></defs>
{''.join(edge_svg)}
{''.join(node_svg)}
</svg>
<table><thead><tr><th>Type</th><th>ID</th><th>Component</th><th>Risk</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</div></body></html>"""
    paths = system_paths()
    if output_path is None:
        out_dir = paths.wiki_dir / "maps"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{slug_for(query)}.html"
    out = Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    append_log(f"visualize | query={query} output={out}")
    return {"success": True, "output_path": str(out), "nodes": len(nodes), "edges": len(edges), "wiki_hits": len(result.get("wiki_hits") or [])}


def _short_label(node_id: str) -> str:
    tail = node_id.split(":", 1)[-1]
    if "/" in tail:
        tail = tail.rsplit("/", 1)[-1]
    return tail[:34]
