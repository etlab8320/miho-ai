"""Frontend tool evaluation corpus for Miho System WikiGraph.

This module records public frontend tool metadata and Miho adoption guidance as
reference facts. It does not install dependencies, copy third-party code, or
change any product frontend. The goal is to let Miho remember which tools were
vetted, why they fit MAX/Miho work, and what guardrails apply before future
project-specific adoption.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from typing import Any

from . import system_wikigraph as wg


@dataclass(frozen=True)
class FrontendTool:
    repo: str
    url: str
    category: str
    adoption: str
    priority: int
    stars: int
    license: str
    pushed: str
    release: str
    release_date: str
    stack: tuple[str, ...]
    korea_fit: str
    best_for: tuple[str, ...]
    cautions: tuple[str, ...]
    recommendation: str


FRONTEND_TOOLS: tuple[FrontendTool, ...] = (
    FrontendTool("shadcn-ui/ui", "https://github.com/shadcn-ui/ui", "component_system", "standard_candidate", 1, 118339, "MIT", "2026-07-07", "shadcn@4.13.0", "2026-07-03", ("React", "Next.js", "Tailwind", "Radix/Base UI"), "High: clean Korean SaaS/admin UI when retokenized with MAX/Toss-like spacing and copy.", ("MAX operations dashboards", "student cards", "admissions tables", "admin forms"), ("Do not use default template look unchanged.", "Retokenize typography, spacing, and status colors."), "Use as the primary copy-owned component baseline for React/Next/Tailwind projects."),
    FrontendTool("heroui-inc/heroui", "https://github.com/heroui-inc/heroui", "component_library", "project_by_project", 2, 29815, "Apache-2.0", "2026-07-07", "v3.2.2", "2026-07-07", ("React", "UI library"), "High for polished parent/student-facing surfaces and fast prototypes.", ("student dashboards", "parent-facing cards", "quick admin prototypes"), ("Less ownership than shadcn-style copy components.", "Avoid mixing full UI libraries without a token plan."), "Use when speed and polished default interactions matter more than deep design-system ownership."),
    FrontendTool("mui/base-ui", "https://github.com/mui/base-ui", "headless_primitives", "design_system_core", 3, 10264, "MIT", "2026-07-07", "v1.6.0", "2026-06-18", ("React", "unstyled", "accessibility"), "Medium-high: invisible foundation for accessible Korean product UI.", ("modals", "menus", "popovers", "selects", "tabs"), ("Not visually complete by itself.", "Requires Miho/MAX tokens and components."), "Use as accessible primitive foundation when building owned design-system components."),
    FrontendTool("radix-ui/primitives", "https://github.com/radix-ui/primitives", "headless_primitives", "indirect_via_shadcn", 4, 19032, "MIT", "2026-07-06", "", "", ("React", "accessibility", "primitives"), "Medium-high: stable behavior layer behind clean Korean SaaS components.", ("accessible primitives", "shadcn-compatible components"), ("Prefer indirect use through shadcn unless a primitive needs direct control.",), "Keep as the proven primitive layer; direct adoption only for components shadcn does not cover well."),
    FrontendTool("motiondivision/motion", "https://github.com/motiondivision/motion", "motion", "standard_candidate", 5, 32691, "MIT", "2026-07-01", "", "", ("React", "JavaScript", "animation"), "High: Toss/Kakao/Naver-style small transitions when used sparingly.", ("card reveal", "modal transitions", "dashboard state changes", "mobile microinteractions"), ("Overuse makes product feel slow or gimmicky.", "Motion must explain state changes, not decorate randomly."), "Use for intentional microinteractions and page/state transitions."),
    FrontendTool("formkit/auto-animate", "https://github.com/formkit/auto-animate", "motion", "standard_candidate", 6, 13870, "MIT", "2026-07-01", "", "", ("React", "Vue", "vanilla JS"), "High for subtle list/filter movement in operational Korean SaaS UI.", ("student list filtering", "attendance roster sorting", "consultation candidate changes", "ranking changes"), ("Use Motion for complex sequences; keep Auto Animate for simple layout changes.",), "Use as low-cost default for simple list and layout transitions."),
    FrontendTool("storybookjs/storybook", "https://github.com/storybookjs/storybook", "quality_workbench", "standard_candidate", 7, 90497, "MIT", "2026-07-07", "v10.4.6", "2026-06-16", ("React", "Vue", "design systems", "component testing"), "Medium: not visual style, but essential for consistent components across Korean product surfaces.", ("component documentation", "states", "visual QA", "design-system regression"), ("Do not introduce if the project is too small to maintain stories.", "Use only for stable shared components."), "Use for shared MAX/Miho component libraries and state documentation."),
    FrontendTool("toss/suspensive", "https://github.com/toss/suspensive", "korea_ux_runtime", "standard_candidate", 8, 1029, "MIT", "2026-07-04", "@suspensive/codemods@3.21.3", "2026-07-04", ("React", "Suspense", "ErrorBoundary", "SSR"), "Very high: Toss-style resilient loading/error boundaries for data-heavy services.", ("student dashboards", "PACA/Peak API surfaces", "report generation waits", "SSR data boundaries"), ("Must pair with plain Korean fallback/error copy.", "Do not hide real data errors behind infinite loading."), "Adopt in data-heavy Next/React apps for safe loading and recovery boundaries."),
    FrontendTool("toss/overlay-kit", "https://github.com/toss/overlay-kit", "korea_ux_runtime", "standard_candidate", 9, 720, "MIT", "2026-06-04", "overlay-kit@1.9.0", "2026-02-25", ("React", "overlay"), "Very high: modal/bottom-sheet flows match Korean service interaction patterns.", ("student selection", "consultation note input", "confirmation flows", "score evidence popups"), ("Govern dangerous actions with confirmation and recovery copy.",), "Adopt for overlay-heavy workflows after project-level UI token review."),
    FrontendTool("toss/use-funnel", "https://github.com/toss/use-funnel", "korea_ux_runtime", "workflow_candidate", 10, 568, "MIT", "2026-04-09", "0.0.12", "2025-06-09", ("React", "wizard", "step state"), "Very high for step-by-step admissions/counseling flows.", ("student selection to recommendation", "score review funnels", "PDF generation flow"), ("Use only when the flow is truly step-based; avoid over-structuring simple forms.",), "Use for high-stakes multi-step flows such as admissions recommendation and parent-facing setup."),
    FrontendTool("naver/egjs-flicking", "https://github.com/naver/egjs-flicking", "korea_mobile_ui", "standard_candidate", 11, 2923, "MIT", "2026-07-07", "4.16.0", "2026-06-26", ("React", "Vue", "Angular", "carousel"), "Very high: proven Korean mobile carousel/card interaction style.", ("student cards", "monthly-test cards", "recommended university cards", "parent notices"), ("Do not bury primary actions inside hard-to-discover carousels.",), "Use for mobile-first card browsing surfaces where horizontal interaction is expected."),
    FrontendTool("intentui/intentui", "https://github.com/intentui/intentui", "component_system", "reference_or_partial", 12, 1941, "MIT", "2026-07-06", "v3.8.4", "2026-06-30", ("React", "React Aria", "Tailwind"), "Medium-high: calm accessible SaaS style if localized and retokenized.", ("accessible component references", "React Aria patterns"), ("Do not mix wholesale with shadcn/HeroUI without design ownership.",), "Use as reference or targeted component source, not default stack."),
    FrontendTool("bitjaru/styleseed", "https://github.com/bitjaru/styleseed", "ai_design_reference", "reference_only", 13, 653, "MIT", "2026-07-06", "v2.8.0", "2026-07-06", ("AI coding", "design rules", "Toss skin", "shadcn"), "High as a reference because it includes Toss-like design judgment patterns.", ("Miho UI judgement", "Self-Harness UI drills", "design corpus"), ("Do not make it a runtime dependency before separate review.", "Use as reference/corpus metadata first."), "Index as reference material for Miho UI judgment and WikiGraph, not as product dependency."),
    FrontendTool("onlook-dev/onlook", "https://github.com/onlook-dev/onlook", "ai_visual_editor", "lab_only", 14, 26141, "Apache-2.0", "2026-06-09", "v0.2.32", "2025-07-17", ("React", "Next.js", "Tailwind", "AI visual editor"), "Medium: visually powerful, but operational/security fit must be tested separately.", ("experimental design workspace", "visual editing spikes"), ("Project file access and AI edit scope need security review.", "Too heavy for Miho runtime integration."), "Keep as lab-only candidate until permission model and workflow are reviewed."),
)

STACK_POLICY = {
    "max_frontend_standard": ("shadcn-ui/ui", "motiondivision/motion", "formkit/auto-animate", "storybookjs/storybook", "toss/suspensive", "toss/overlay-kit", "naver/egjs-flicking"),
    "parent_student_mobile": ("heroui-inc/heroui", "motiondivision/motion", "formkit/auto-animate", "naver/egjs-flicking"),
    "miho_design_intelligence_reference": ("bitjaru/styleseed", "shadcn-ui/ui", "toss/suspensive", "naver/egjs-flicking"),
}


def sync_frontend_tool_corpus() -> dict[str, Any]:
    """Sync vetted frontend tool metadata into Miho System WikiGraph."""

    wg.init_wiki()
    conn = wg.connect()
    summary = {"tools_indexed": 0, "stacks_indexed": 0, "edges": 0}
    category_counts = Counter(tool.category for tool in FRONTEND_TOOLS)
    adoption_counts = Counter(tool.adoption for tool in FRONTEND_TOOLS)
    try:
        _upsert_root(conn)
        for tool in FRONTEND_TOOLS:
            _upsert_tool(conn, tool, summary)
        for category, count in sorted(category_counts.items()):
            _upsert_group(conn, "FrontendToolCategory", "frontend-tool-category", category, count, "classified_as", "category", summary)
        for adoption, count in sorted(adoption_counts.items()):
            _upsert_group(conn, "FrontendToolAdoptionPolicy", "frontend-tool-adoption", adoption, count, "uses_adoption_policy", "adoption", summary)
        for stack_name, repos in STACK_POLICY.items():
            _upsert_stack(conn, stack_name, repos, summary)
        conn.commit()
    finally:
        conn.close()
    _write_frontend_tool_pages(summary=summary, category_counts=category_counts, adoption_counts=adoption_counts)
    wg.append_log(f"frontend-tools sync | tools={summary['tools_indexed']} stacks={summary['stacks_indexed']} edges={summary['edges']}")
    return {"success": True, "summary": summary, "categories": dict(sorted(category_counts.items())), "adoptions": dict(sorted(adoption_counts.items())), "wiki_dir": str(wg.system_paths().wiki_dir), "db_path": str(wg.system_paths().db_path)}


def build_ui_self_harness_candidates() -> list[dict[str, Any]]:
    return [
        {"id": "frontend_ui_drill:tool_adoption_requires_project_target", "intent": "Do not install frontend dependencies until the target project/app is explicit.", "source": "Miho frontend tool corpus", "target_test": "tests/plugins/test_governance_os_policy.py", "activation_policy": "candidate_only_until_test_implemented"},
        {"id": "frontend_ui_drill:korean_product_ui_requires_states", "intent": "Korean product UI recommendations must account for loading, empty, error, disabled, mobile, and accessibility states.", "source": "product-ui-design skill + frontend tool corpus", "target_test": "tests/plugins/test_governance_os_domain_packs.py", "activation_policy": "candidate_only_until_test_implemented"},
        {"id": "frontend_ui_drill:motion_must_explain_state_change", "intent": "Motion/animation recommendations should improve state comprehension and avoid decorative bloat.", "source": "Motion + Auto Animate evaluation", "target_test": "tests/agent/test_frontend_tool_corpus.py", "activation_policy": "candidate_only_until_test_implemented"},
        {"id": "frontend_ui_drill:reference_tools_not_runtime_dependencies", "intent": "Reference-only design intelligence tools such as StyleSeed should be indexed as corpus metadata before runtime adoption.", "source": "StyleSeed adoption policy", "target_test": "tests/agent/test_frontend_tool_corpus.py", "activation_policy": "candidate_only_until_test_implemented"},
    ]


def _upsert_root(conn: sqlite3.Connection) -> None:
    wg.upsert_node(conn, node_id="frontend-tool-corpus:recommended", node_type="FrontendToolCorpus", title="Recommended Frontend Tool Corpus", summary="Vetted frontend tool metadata and adoption guidance for Miho/MAX UI work; reference-only until a target project is explicit.", component="frontend-tools", risk="medium", status="observed", metadata={"source_policy": "public GitHub metadata + Miho evaluation", "install_policy": "do_not_install_until_target_project_is_explicit", "primary_stack": "shadcn/ui + Tailwind + Motion + Auto Animate + Storybook + Toss/Naver UX tools"})


def _upsert_tool(conn: sqlite3.Connection, tool: FrontendTool, summary: dict[str, int]) -> None:
    node_id = f"frontend-tool:{wg.slug_for(tool.repo)}"
    wg.upsert_node(conn, node_id=node_id, node_type="FrontendTool", title=tool.repo, summary=tool.recommendation, path=tool.url, component="frontend-tools", risk=_risk_for(tool), status=tool.adoption, metadata={"repo": tool.repo, "url": tool.url, "category": tool.category, "adoption": tool.adoption, "priority": tool.priority, "stars": tool.stars, "license": tool.license, "pushed": tool.pushed, "release": tool.release, "release_date": tool.release_date, "stack": list(tool.stack), "korea_fit": tool.korea_fit, "best_for": list(tool.best_for), "cautions": list(tool.cautions), "recommendation": tool.recommendation})
    wg.upsert_edge(conn, source_id="frontend-tool-corpus:recommended", relation="contains", target_id=node_id, confidence=max(0.1, min(1.0, (15.0 - float(tool.priority)) / 14.0)), evidence=f"priority={tool.priority}; adoption={tool.adoption}")
    summary["tools_indexed"] += 1
    summary["edges"] += 1


def _upsert_group(conn: sqlite3.Connection, node_type: str, prefix: str, value: str, count: int, relation: str, metadata_key: str, summary: dict[str, int]) -> None:
    group_id = f"{prefix}:{value}"
    wg.upsert_node(conn, node_id=group_id, node_type=node_type, title=value, summary=f"{value} applies to {count} vetted frontend tool(s).", component="frontend-tools", risk="low", status="observed", metadata={"tool_count": count})
    for tool in FRONTEND_TOOLS:
        if getattr(tool, metadata_key) != value:
            continue
        wg.upsert_edge(conn, source_id=f"frontend-tool:{wg.slug_for(tool.repo)}", relation=relation, target_id=group_id, confidence=1.0, evidence=f"{metadata_key}={value}")
        summary["edges"] += 1


def _upsert_stack(conn: sqlite3.Connection, stack_name: str, repos: tuple[str, ...], summary: dict[str, int]) -> None:
    stack_id = f"frontend-stack:{stack_name}"
    wg.upsert_node(conn, node_id=stack_id, node_type="FrontendStackRecommendation", title=stack_name.replace("_", " "), summary=_stack_summary(stack_name), component="frontend-tools", risk="medium", status="recommended", metadata={"repos": list(repos), "install_policy": "project_explicit_required"})
    summary["stacks_indexed"] += 1
    for repo in repos:
        wg.upsert_edge(conn, source_id=stack_id, relation="recommends_tool", target_id=f"frontend-tool:{wg.slug_for(repo)}", confidence=0.9, evidence=f"stack={stack_name}")
        summary["edges"] += 1


def _risk_for(tool: FrontendTool) -> str:
    if tool.adoption in {"lab_only", "reference_only"}:
        return "medium"
    if tool.adoption in {"standard_candidate", "design_system_core", "indirect_via_shadcn"}:
        return "low"
    return "medium"


def _stack_summary(stack_name: str) -> str:
    if stack_name == "max_frontend_standard":
        return "Primary MAX/Miho React/Next Korean SaaS stack: owned components, subtle motion, state documentation, and Toss/Naver UX utilities."
    if stack_name == "parent_student_mobile":
        return "Mobile-friendly parent/student card stack with polished components, carousel patterns, and restrained motion."
    if stack_name == "miho_design_intelligence_reference":
        return "Reference-only design intelligence stack for Miho UI judgment, WikiGraph, and Self-Harness candidates."
    return "Frontend stack recommendation."


def _write_frontend_tool_pages(*, summary: dict[str, int], category_counts: Counter[str], adoption_counts: Counter[str]) -> None:
    paths = wg.system_paths()
    base = paths.wiki_dir / "frontend-tools"
    base.mkdir(parents=True, exist_ok=True)
    rows = [
        "| {priority} | [{repo}]({url}) | {adoption} | {license} | {stars:,} | {pushed} | {fit} |".format(priority=tool.priority, repo=tool.repo, url=tool.url, adoption=tool.adoption, license=tool.license or "unknown", stars=tool.stars, pushed=tool.pushed, fit=tool.korea_fit.replace("|", "/"))
        for tool in sorted(FRONTEND_TOOLS, key=lambda item: item.priority)
    ]
    (base / "recommended-frontend-tools.md").write_text("\n".join(["# Recommended Frontend Tools for Miho/MAX", "", f"Generated: {wg.utc_now()}", "", "This page records vetted public frontend tool metadata and Miho adoption guidance. It is reference-only: no package is installed until a target project/app is explicit.", "", "## Primary recommendation", "", "Use `shadcn/ui + Tailwind + Motion + Auto Animate + Storybook` as the default owned React/Next design-system path, then add `Toss Suspensive`, `Toss overlay-kit`, and `Naver egjs-flicking` for Korean product UX patterns where the project needs them.", "", "## Tool table", "", "| Priority | Tool | Adoption | License | Stars | Recent push | Korea/MAX fit |", "| ---: | --- | --- | --- | ---: | --- | --- |", *rows, "", "## Category counts", "", *[f"- `{key}`: {value}" for key, value in sorted(category_counts.items())], "", "## Adoption policy counts", "", *[f"- `{key}`: {value}" for key, value in sorted(adoption_counts.items())], "", "## Safety boundary", "", "- Do not install or mutate product dependencies from this corpus alone.", "- Ask for or infer an explicit target project before package installation.", "- Keep reference-only tools such as StyleSeed as WikiGraph/corpus metadata until a separate security and workflow review passes.", "- Every product UI adoption must cover loading, empty, error, disabled, mobile, keyboard, and accessibility states."]) + "\n", encoding="utf-8")
    lines = ["# MAX/Miho Frontend Stack Recommendations", "", f"Generated: {wg.utc_now()}", ""]
    for stack_name, repos in STACK_POLICY.items():
        lines.extend([f"## {stack_name}", "", _stack_summary(stack_name), ""])
        for repo in repos:
            tool = next((item for item in FRONTEND_TOOLS if item.repo == repo), None)
            if tool:
                lines.append(f"- [{tool.repo}]({tool.url}) — {tool.recommendation}")
        lines.append("")
    (base / "max-frontend-stack.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    drill_lines = ["# UI Self-Harness Candidate Drills", "", f"Generated: {wg.utc_now()}", "", "These are candidate-only UI quality drills derived from vetted frontend tools and the product-ui-design skill. They are not active runtime rules until implemented, tested, validated, and promoted through Evolution OS.", ""]
    for item in build_ui_self_harness_candidates():
        drill_lines.extend([f"## {item['id']}", "", f"- Intent: {item['intent']}", f"- Source: {item['source']}", f"- Target test: `{item['target_test']}`", f"- Activation: `{item['activation_policy']}`", ""])
    (base / "ui-self-harness-candidates.md").write_text("\n".join(drill_lines), encoding="utf-8")
    policy_page = paths.wiki_dir / "policies" / "frontend-tool-adoption-boundary.md"
    policy_page.parent.mkdir(parents=True, exist_ok=True)
    policy_page.write_text("\n".join(["# Frontend Tool Adoption Boundary", "", f"Generated: {wg.utc_now()}", "", "Miho may recommend frontend tools from the vetted corpus, but must not install or wire them into an app unless the target project is explicit.", "", "## Required before installation", "", "1. Target project/app/folder is explicit.", "2. Existing stack and instructions are inspected.", "3. License and dependency footprint are checked.", "4. UI states and accessibility expectations are named.", "5. Focused tests/build/lint/browser smoke are planned for that project.", "", "## Reference-only tools", "", "StyleSeed and similar AI design rule corpora should first enter Miho as metadata/reference/WikiGraph material, not runtime dependencies."]) + "\n", encoding="utf-8")