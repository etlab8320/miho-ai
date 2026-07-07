"""Relationship layer for Miho System WikiGraph governance maps."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Iterable

from miho_constants import get_miho_home

from . import system_wikigraph as wg


RELATION_TYPES = {
    "uses",
    "uses_agent",
    "uses_skill",
    "uses_tool",
    "uses_toolset",
    "mitigates",
    "prevents",
    "participates_in",
}
FAILURE_TERMS = (
    "failure",
    "failed",
    "error",
    "timeout",
    "missing",
    "blocked",
    "denied",
    "unavailable",
    "leak",
    "오탐",
    "실패",
    "누락",
    "차단",
    "막힘",
    "방지",
    "깨짐",
)


def sync_relationships(*, project_root: str | Path | None = None) -> dict[str, Any]:
    """Infer skill/tool/agent/cron/failure relationships into graph.db."""

    wg.init_wiki()
    conn = wg.connect()
    stats = {
        "skills_scanned": 0,
        "skill_tool_edges": 0,
        "failure_nodes": 0,
        "mitigation_edges": 0,
        "governance_edges": 0,
        "cron_jobs": 0,
        "edges": 0,
    }
    try:
        _clear_layer_edges(conn)
        known_tools = _known_tools(conn)
        _sync_skill_relationships(conn, known_tools, stats)
        _sync_governance_registry(conn, stats)
        _sync_cron_jobs(conn, stats)
        conn.commit()
        _refresh_actual_counts(conn, stats)
    finally:
        conn.close()
    _write_relationship_page(stats, project_root=project_root)
    return {
        "success": True,
        "summary": stats,
        "wiki_dir": str(wg.system_paths().wiki_dir),
        "db_path": str(wg.system_paths().db_path),
    }


def render_governance_relationship_html(
    *,
    output_path: str | Path | None = None,
    limit: int = 180,
) -> dict[str, Any]:
    """Render a self-contained relationship map focused on governance edges."""

    wg.init_wiki()
    conn = wg.connect()
    try:
        edges = _relationship_edges(conn, limit=limit)
        node_ids = sorted({edge["source_id"] for edge in edges} | {edge["target_id"] for edge in edges})
        nodes = _nodes_by_id(conn, node_ids)
    finally:
        conn.close()
    doc = _relationship_html(nodes=nodes, edges=edges)
    if output_path is None:
        output_path = wg.system_paths().wiki_dir / "maps" / "governance-relationship-map.html"
    out = Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    wg.append_log(f"relationships visualized | output={out}")
    return {"success": True, "output_path": str(out), "nodes": len(nodes), "edges": len(edges)}


def _sync_skill_relationships(conn: Any, known_tools: set[str], stats: dict[str, int]) -> None:
    rows = conn.execute(
        "SELECT id, title, path FROM nodes WHERE type='Skill' AND path != '' ORDER BY id"
    ).fetchall()
    for row in rows:
        path = Path(str(row["path"] or "")).expanduser()
        if not path.exists() or path.is_dir():
            continue
        content = wg.safe_read(path, max_chars=120_000)
        if not content:
            continue
        stats["skills_scanned"] += 1
        for tool in _mentioned_tools(content, known_tools):
            tool_id = f"tool:{tool}"
            wg.upsert_edge(
                conn,
                source_id=str(row["id"]),
                relation="uses",
                target_id=tool_id,
                status="inferred",
                confidence=0.68,
                evidence="skill text mentions registered tool",
            )
            stats["skill_tool_edges"] += 1
            stats["edges"] += 1
        for failure in _extract_failure_labels(content):
            failure_id = _upsert_failure(conn, failure, stats, evidence="skill text failure language")
            wg.upsert_edge(
                conn,
                source_id=str(row["id"]),
                relation="mitigates",
                target_id=failure_id,
                status="inferred",
                confidence=0.58,
                evidence="skill text describes failure prevention or recovery",
            )
            stats["mitigation_edges"] += 1
            stats["edges"] += 1


def _sync_governance_registry(conn: Any, stats: dict[str, int]) -> None:
    try:
        from plugins.governance_os.registry import load_builtin_registry
    except Exception:
        return
    try:
        registry = load_builtin_registry()
    except Exception:
        return
    for role_key, role in sorted(registry.roles.items()):
        agent_id = f"agent:{role_key}"
        wg.upsert_node(
            conn,
            node_id=agent_id,
            node_type="Agent",
            title=getattr(role, "name", role_key) or role_key,
            summary="; ".join(getattr(role, "responsibilities", ()) or ())[:500],
            component="governance",
            risk="high",
            status="observed",
            metadata={"role_key": role_key},
        )
    for playbook_key, playbook in sorted(registry.playbooks.items()):
        playbook_id = f"playbook:{playbook_key}"
        wg.upsert_node(
            conn,
            node_id=playbook_id,
            node_type="GovernancePlaybook",
            title=playbook_key,
            summary=str(getattr(playbook, "delivery_format", "") or "")[:500],
            component="governance",
            risk="high",
            status="observed",
            metadata={"domain": getattr(playbook, "domain", ""), "review_gates": list(playbook.review_gates)},
        )
        failure_id = _upsert_failure(
            conn,
            f"{playbook_key}: unreviewed or wrong final delivery",
            stats,
            evidence="governance playbook review contract",
        )
        for role_key in playbook.agent_chain:
            agent_id = f"agent:{role_key}"
            _edge(conn, playbook_id, "uses_agent", agent_id, "governance playbook agent chain", stats)
            _edge(conn, agent_id, "participates_in", playbook_id, "governance playbook agent chain", stats)
            _edge(conn, agent_id, "mitigates", failure_id, "agent participates in governed delivery recovery", stats)
        for tool in playbook.required_tools:
            tool_id = f"tool:{tool}"
            wg.upsert_node(
                conn,
                node_id=tool_id,
                node_type="Tool",
                title=tool,
                component="governance",
                risk="high",
                status="observed",
            )
            _edge(conn, playbook_id, "uses_tool", tool_id, "governance required_tools contract", stats)
            _edge(conn, tool_id, "prevents", failure_id, "required tool prevents unsupported final claims", stats)
            for role_key in playbook.agent_chain:
                _edge(
                    conn,
                    f"agent:{role_key}",
                    "uses_tool",
                    tool_id,
                    "agent tool use inferred from playbook required_tools",
                    stats,
                )
        stats["governance_edges"] = stats["edges"] - stats["skill_tool_edges"] - stats["mitigation_edges"]


def _sync_cron_jobs(conn: Any, stats: dict[str, int]) -> None:
    jobs_path = get_miho_home() / "cron" / "jobs.json"
    jobs = _load_cron_jobs(jobs_path)
    for job in jobs:
        job_id = str(job.get("id") or job.get("name") or "cron-job").strip()
        if not job_id:
            continue
        node_id = f"cron:{wg.slug_for(job_id)}"
        prompt = str(job.get("prompt") or job.get("name") or job_id)
        wg.upsert_node(
            conn,
            node_id=node_id,
            node_type="CronJob",
            title=str(job.get("name") or job_id),
            summary=prompt[:500],
            path=str(jobs_path),
            component="cron",
            risk="high",
            status="observed" if job.get("enabled", True) else "stale",
            metadata={"schedule": job.get("schedule"), "enabled": job.get("enabled", True)},
        )
        stats["cron_jobs"] += 1
        for skill in _string_items(job.get("skills") or job.get("skill")):
            skill_id = f"skill:{Path(skill).name}"
            wg.upsert_node(conn, node_id=skill_id, node_type="Skill", title=skill, component="runtime-skills", status="inferred")
            _edge(conn, node_id, "uses_skill", skill_id, "cron job skill field", stats)
        for toolset in _string_items(job.get("enabled_toolsets")):
            toolset_id = f"toolset:{toolset}"
            wg.upsert_node(conn, node_id=toolset_id, node_type="Toolset", title=toolset, component="tools", status="inferred")
            _edge(conn, node_id, "uses_toolset", toolset_id, "cron job enabled_toolsets field", stats)
        for failure in _extract_failure_labels(prompt):
            failure_id = _upsert_failure(conn, failure, stats, evidence="cron prompt failure language")
            _edge(conn, node_id, "mitigates", failure_id, "cron job prompt describes prevention or recovery", stats)


def _known_tools(conn: Any) -> set[str]:
    tools = {str(row["title"] or "").strip() for row in conn.execute("SELECT title FROM nodes WHERE type='Tool'")}
    try:
        from plugins.decision_twin.contracts import decision_tool_contracts

        tools.update(decision_tool_contracts())
    except Exception:
        pass
    try:
        from plugins.governance_os.registry import load_builtin_registry

        for playbook in load_builtin_registry().playbooks.values():
            tools.update(playbook.required_tools)
    except Exception:
        pass
    return {tool for tool in tools if len(tool) >= 4}


def _clear_layer_edges(conn: Any) -> None:
    placeholders = ",".join("?" for _ in RELATION_TYPES)
    conn.execute(
        f"DELETE FROM edges WHERE relation IN ({placeholders}) AND ("
        "evidence LIKE 'skill text%' OR evidence LIKE 'governance%' OR "
        "evidence LIKE 'agent tool%' OR evidence LIKE 'required tool%' OR "
        "evidence LIKE 'cron job%')",
        tuple(sorted(RELATION_TYPES)),
    )


def _mentioned_tools(content: str, known_tools: set[str]) -> list[str]:
    blob = f" {content.casefold()} "
    found: list[str] = []
    for tool in sorted(known_tools):
        low = tool.casefold()
        variants = {low, low.replace("_", " "), low.replace("_", "-")}
        if any(_contains_token(blob, variant) for variant in variants) and tool not in found:
            found.append(tool)
    return found[:40]


def _contains_token(blob: str, token: str) -> bool:
    if not token.strip():
        return False
    if any(ch in token for ch in " _-/"):
        return token in blob
    return re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", blob) is not None


def _extract_failure_labels(content: str) -> list[str]:
    labels: list[str] = []
    for match in re.finditer(r"`([^`\n]*(?:failure|error|timeout|missing|blocked|leak)[^`\n]*)`", content, re.I):
        labels.append(match.group(1))
    for line in content.splitlines():
        compact = " ".join(line.strip(" -*#>\t").split())
        if len(compact) < 8:
            continue
        low = compact.casefold()
        if any(term in low for term in FAILURE_TERMS):
            labels.append(compact[:120])
    return _unique(labels)[:8]


def _upsert_failure(conn: Any, label: str, stats: dict[str, int], *, evidence: str) -> str:
    title = " ".join(str(label or "").split())[:140] or "unknown failure"
    node_id = f"failure:{wg.slug_for(title)[:96]}"
    wg.upsert_node(
        conn,
        node_id=node_id,
        node_type="Failure",
        title=title,
        summary=evidence,
        component="governance",
        risk="high",
        status="inferred",
    )
    stats["failure_nodes"] += 1
    return node_id


def _edge(conn: Any, source: str, relation: str, target: str, evidence: str, stats: dict[str, int]) -> None:
    wg.upsert_edge(conn, source_id=source, relation=relation, target_id=target, status="inferred", confidence=0.64, evidence=evidence)
    stats["edges"] += 1


def _relationship_edges(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    per_relation = max(8, int(limit) // max(1, len(RELATION_TYPES)))
    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for relation in sorted(RELATION_TYPES):
        rows = conn.execute(
            "SELECT * FROM edges WHERE relation=? ORDER BY confidence DESC, source_id LIMIT ?",
            (relation, per_relation),
        ).fetchall()
        for row in rows:
            edge = dict(row)
            key = (str(edge["source_id"]), str(edge["relation"]), str(edge["target_id"]))
            if key not in seen:
                seen.add(key)
                collected.append(edge)
    return collected[: int(limit)]


def _refresh_actual_counts(conn: Any, stats: dict[str, int]) -> None:
    placeholders = ",".join("?" for _ in RELATION_TYPES)
    stats["edges"] = int(
        conn.execute(
            f"SELECT COUNT(*) FROM edges WHERE relation IN ({placeholders})",
            tuple(sorted(RELATION_TYPES)),
        ).fetchone()[0]
    )
    stats["failure_nodes"] = int(
        conn.execute("SELECT COUNT(*) FROM nodes WHERE type='Failure'").fetchone()[0]
    )
    stats["skill_tool_edges"] = int(
        conn.execute(
            "SELECT COUNT(*) FROM edges e JOIN nodes s ON s.id=e.source_id "
            "JOIN nodes t ON t.id=e.target_id "
            "WHERE e.relation='uses' AND s.type='Skill' AND t.type='Tool'"
        ).fetchone()[0]
    )
    stats["mitigation_edges"] = int(
        conn.execute("SELECT COUNT(*) FROM edges WHERE relation='mitigates'").fetchone()[0]
    )


def _nodes_by_id(conn: Any, node_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ids = [node_id for node_id in node_ids if node_id]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(f"SELECT * FROM nodes WHERE id IN ({placeholders})", ids).fetchall()
    return {str(row["id"]): dict(row) for row in rows}


def _relationship_html(*, nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    relation_counts: dict[str, int] = {}
    for edge in edges:
        relation_counts[str(edge.get("relation") or "")] = relation_counts.get(str(edge.get("relation") or ""), 0) + 1
    chips = "".join(f"<span>{html.escape(key)} {value}</span>" for key, value in sorted(relation_counts.items()))
    rows = "\n".join(_edge_row(edge, nodes) for edge in edges)
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>Miho Governance Relationship Map</title>
<style>
body{{margin:0;background:oklch(97% .01 180);color:oklch(22% .035 190);font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:34px 28px 52px}}h1{{font-size:30px;margin:0 0 8px;font-weight:780;letter-spacing:0}}
.sub{{max-width:74ch;color:oklch(40% .035 195);line-height:1.58;margin-bottom:18px}}.chips{{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 24px}}
.chips span{{border:1px solid oklch(78% .04 185);background:oklch(93% .026 178);border-radius:999px;padding:7px 11px;font-size:13px}}
table{{width:100%;border-collapse:separate;border-spacing:0;background:oklch(99% .006 180);border:1px solid oklch(84% .026 185);border-radius:8px;overflow:hidden}}
th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid oklch(88% .018 185);vertical-align:top;font-size:13px;line-height:1.45}}th{{font-size:12px;text-transform:uppercase;color:oklch(38% .05 185);background:oklch(94% .018 180)}}
tr:last-child td{{border-bottom:0}}.type{{font-weight:700;color:oklch(34% .075 178)}}.muted{{color:oklch(48% .03 190)}}
</style></head><body><main class="wrap">
<h1>Miho Governance Relationship Map</h1>
<p class="sub">기존 System WikiGraph에 스킬, 도구, 크론, 거버넌스 에이전트, 실패 방지 관계선을 얹은 운영 지도입니다. 관계는 현재 소스, 스킬 문서, cron 설정, Governance registry에서 다시 추출됩니다.</p>
<div class="chips"><span>nodes {len(nodes)}</span><span>edges {len(edges)}</span>{chips}</div>
<table><thead><tr><th>Source</th><th>Relation</th><th>Target</th><th>Evidence</th></tr></thead><tbody>{rows}</tbody></table>
</main></body></html>"""


def _edge_row(edge: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> str:
    source = str(edge.get("source_id") or "")
    target = str(edge.get("target_id") or "")
    return (
        "<tr>"
        f"<td>{_node_cell(source, nodes.get(source))}</td>"
        f"<td class='type'>{html.escape(str(edge.get('relation') or ''))}</td>"
        f"<td>{_node_cell(target, nodes.get(target))}</td>"
        f"<td class='muted'>{html.escape(str(edge.get('evidence') or ''))}</td>"
        "</tr>"
    )


def _node_cell(node_id: str, node: dict[str, Any] | None) -> str:
    title = str((node or {}).get("title") or node_id)
    node_type = str((node or {}).get("type") or "")
    return f"<b>{html.escape(title)}</b><br><span class='muted'>{html.escape(node_type)} · {html.escape(node_id)}</span>"


def _write_relationship_page(stats: dict[str, int], *, project_root: str | Path | None) -> None:
    paths = wg.system_paths()
    path = paths.wiki_dir / "governance" / "governance-relationship-map.md"
    root = str(project_root or Path.cwd())
    content = f"""---
title: Governance Relationship Map
created: {wg.today()}
updated: {wg.today()}
type: map
status: inferred
tags: [miho, governance, wikigraph, relationships]
sources: [{root}, plugins/governance_os/registry.json, ~/.miho/cron/jobs.json]
---

# Governance Relationship Map

This page summarizes the relationship layer added on top of the existing System
WikiGraph. It does not replace the SQLite graph; it records the latest sync
counts and points operators to the rendered map.

```json
{json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True)}
```

Run:

```bash
miho evolution wikigraph relationships
```
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _load_cron_jobs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        value = raw.get("jobs", raw)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [item for item in value.values() if isinstance(item, dict)]
    return []


def _string_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = " ".join(str(value or "").split())
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
