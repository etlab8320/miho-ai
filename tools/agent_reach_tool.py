"""Agent Reach routing helpers for Miho.

This module intentionally does not execute platform searches or login setup.
It exposes Agent Reach as a safe routing/status surface so the model can pick
the right existing Miho tool or terminal command with accurate backend state.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any, cast

from tools.registry import registry


AGENT_REACH_BIN_ENV = "MIHO_AGENT_REACH_BIN"
DOCTOR_TIMEOUT_SECONDS = 10


CHANNEL_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "youtube",
        (r"youtube\.com", r"youtu\.be", r"\byt\b", r"유튜브", r"영상", r"자막"),
        "Video or subtitle request",
    ),
    (
        "github",
        (r"github\.com", r"\bgithub\b", r"\bgh\b", r"repo", r"repository", r"깃허브"),
        "Repository or code search",
    ),
    (
        "rss",
        (r"\brss\b", r"\batom\b", r"feed", r"피드"),
        "Feed or subscription source",
    ),
    (
        "bilibili",
        (r"bilibili", r"\bb\s*站\b", r"비리비리", r"哔哩哔哩"),
        "Bilibili content",
    ),
    ("v2ex", (r"\bv2ex\b",), "V2EX public community data"),
    ("reddit", (r"\breddit\b", r"레딧"), "Reddit discussion"),
    (
        "twitter",
        (r"\btwitter\b", r"\bx\.com\b", r"\b트위터\b", r"\bX\b"),
        "Twitter/X discussion",
    ),
    (
        "xiaohongshu",
        (r"xiaohongshu", r"\bxhs\b", r"小红书", r"샤오홍슈"),
        "Xiaohongshu notes",
    ),
    (
        "linkedin",
        (r"linkedin", r"링크드인", r"채용", r"job", r"recruit"),
        "Career or LinkedIn data",
    ),
    ("xueqiu", (r"xueqiu", r"雪球", r"주식", r"stock", r"行情"), "Xueqiu market data"),
    (
        "exa_search",
        (r"전수", r"deep research", r"research", r"리서치", r"조사"),
        "Broad semantic web research",
    ),
    (
        "web",
        (r"https?://", r"웹", r"사이트", r"article", r"페이지", r"검색"),
        "General web page or search",
    ),
)


COMMAND_EXAMPLES: dict[str, list[str]] = {
    "youtube": [
        "yt-dlp --write-sub --write-auto-sub --skip-download -o '/tmp/%(id)s' '<url>'"
    ],
    "github": ["gh search repos '<query>' --sort stars --limit 10"],
    "rss": ["python -m feedparser '<rss-url>'"],
    "bilibili": ["bili search '<query>' --type video -n 5"],
    "v2ex": ["curl -s 'https://www.v2ex.com/api/topics/hot.json'"],
    "reddit": ["opencli reddit search '<query>' -f yaml", "rdt search '<query>' --limit 10"],
    "twitter": ["twitter search '<query>' -n 10"],
    "xiaohongshu": ["opencli xiaohongshu search '<query>' -f yaml"],
    "linkedin": [
        "curl -s 'https://r.jina.ai/https://www.linkedin.com/search/results/all/?keywords=<query>'"
    ],
    "xueqiu": ["agent-reach doctor --json"],
    "exa_search": ["mcporter call 'exa.web_search_exa(query: \"<query>\", numResults: 5)'"],
    "web": ["curl -s 'https://r.jina.ai/<url>'"],
}


AGENT_REACH_STATUS_SCHEMA = {
    "name": "agent_reach_status",
    "description": (
        "Check Agent Reach availability and normalize its doctor channel map. "
        "Use this before internet, YouTube, GitHub, RSS, or social research tasks."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "run_doctor": {
                "type": "boolean",
                "description": "Run `agent-reach doctor --json` when the CLI is installed.",
                "default": True,
            },
            "include_raw": {
                "type": "boolean",
                "description": "Include the raw parsed doctor payload for debugging.",
                "default": False,
            },
        },
    },
}


AGENT_REACH_ROUTE_SCHEMA = {
    "name": "agent_reach_route",
    "description": (
        "Map a user request to Agent Reach channels and show which backend is "
        "available. This is a safe planner; it does not execute searches."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": "The natural-language request or URL to route.",
            },
            "include_status": {
                "type": "boolean",
                "description": "Include current doctor status for detected channels.",
                "default": True,
            },
        },
        "required": ["request"],
    },
}

RESEARCH_ROUTER_SCHEMA = {
    "name": "research_router",
    "description": (
        "Single safe entry point for public research/search routing. The assistant must provide "
        "its LLM-derived mapping in llm_intent; this tool only checks live Agent Reach status, "
        "applies deterministic safety boundaries, and returns a backend plan. It does not execute "
        "web searches, social searches, account actions, installs, cookie imports, or writes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": "The user's original research/search request.",
            },
            "llm_intent": {
                "type": "object",
                "description": (
                    "LLM mapping result. Required. Suggested keys: task_type, source_type, "
                    "desired_output, candidate_channels, requires_login, may_write, uses_private_or_internal_data, "
                    "needs_current_broad_search, needs_youtube_summary_card, rationale."
                ),
            },
            "run_doctor": {
                "type": "boolean",
                "description": "Run agent-reach doctor to check live channel availability.",
                "default": True,
            },
        },
        "required": ["request", "llm_intent"],
    },
}


def _agent_reach_bin() -> str | None:
    configured = os.environ.get(AGENT_REACH_BIN_ENV)
    if configured:
        return configured
    return shutil.which("agent-reach")


def _normalize_channels(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}

    source = payload.get("channels") if isinstance(payload.get("channels"), dict) else payload
    channels: dict[str, dict[str, Any]] = {}
    for name, value in source.items():
        if not isinstance(name, str) or not isinstance(value, dict):
            continue
        if not ({"status", "active_backend", "backends", "tier"} & set(value.keys())):
            continue
        channels[name] = {
            "status": value.get("status", "unknown"),
            "active_backend": value.get("active_backend"),
            "tier": value.get("tier"),
            "backends": value.get("backends", []),
            "message": value.get("message", ""),
        }
    return channels


def _run_doctor() -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None, str | None]:
    binary = _agent_reach_bin()
    if not binary:
        return {}, None, "agent-reach CLI is not installed or not on PATH"

    try:
        completed = subprocess.run(
            [binary, "doctor", "--json"],
            capture_output=True,
            text=True,
            timeout=DOCTOR_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {}, None, f"agent-reach doctor timed out after {DOCTOR_TIMEOUT_SECONDS}s"
    except OSError as exc:
        return {}, None, f"agent-reach doctor could not start: {exc}"
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "agent-reach doctor failed"
        return {}, None, message

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {}, None, f"agent-reach doctor returned invalid JSON: {exc}"

    return _normalize_channels(payload), payload if isinstance(payload, dict) else None, None


def _channel_summary(channels: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "status": data.get("status", "unknown"),
            "active_backend": data.get("active_backend"),
            "tier": data.get("tier"),
            "backends": data.get("backends", []),
        }
        for name, data in sorted(channels.items())
    }


def _detect_channels(request: str) -> list[dict[str, str]]:
    text = request or ""
    detected: list[dict[str, str]] = []
    seen: set[str] = set()

    for channel, patterns, reason in CHANNEL_RULES:
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
            detected.append({"channel": channel, "reason": reason})
            seen.add(channel)

    if not detected:
        detected.append({
            "channel": "web",
            "reason": "Fallback for general internet lookup",
        })
        seen.add("web")

    if "exa_search" in seen and "web" not in seen:
        detected.append({
            "channel": "web",
            "reason": "Fallback when semantic search is unavailable",
        })

    return detected


def agent_reach_status_tool(args: dict[str, Any] | None = None, **_: Any) -> str:
    args = args or {}
    binary = _agent_reach_bin()
    result: dict[str, Any] = {
        "success": True,
        "installed": bool(binary),
        "binary": binary,
        "doctor_ran": False,
        "channels": {},
        "safety": "Read-only status check. No installs, login imports, or platform writes are performed.",
    }

    if not binary:
        result["message"] = "agent-reach CLI is not installed or not on PATH"
        return json.dumps(result, ensure_ascii=True)

    if args.get("run_doctor", True):
        channels, raw_payload, error = _run_doctor()
        result["doctor_ran"] = True
        if error:
            result["success"] = False
            result["error"] = error
        result["channels"] = _channel_summary(channels)
        if args.get("include_raw", False):
            result["raw"] = raw_payload

    return json.dumps(result, ensure_ascii=True)


def agent_reach_route_tool(args: dict[str, Any] | None = None, **_: Any) -> str:
    args = args or {}
    request = str(args.get("request", "")).strip()
    if not request:
        return json.dumps({"error": "request is required"}, ensure_ascii=True)

    channels: dict[str, dict[str, Any]] = {}
    status_error: str | None = None
    if args.get("include_status", True):
        channels, _, status_error = _run_doctor()

    routes = []
    for item in _detect_channels(request):
        channel = item["channel"]
        status = channels.get(channel, {})
        status_value = status.get("status", "unknown")
        routes.append({
            "channel": channel,
            "reason": item["reason"],
            "status": status_value,
            "active_backend": status.get("active_backend"),
            "setup_needed": bool(status_error) or status_value in {"off", "warn"},
            "command_examples": COMMAND_EXAMPLES.get(channel, []),
        })

    primary = next(
        (route["channel"] for route in routes if route["status"] == "ok"),
        routes[0]["channel"],
    )
    return json.dumps({
        "success": True,
        "request": request,
        "primary_channel": primary,
        "routes": routes,
        "status_error": status_error,
        "safety": "Planner only. It does not execute searches, installs, cookie imports, or write actions.",
    }, ensure_ascii=True)


INTERNAL_DOMAIN_MARKERS = frozenset({
    "academy",
    "paca",
    "peak",
    "life_record",
    "student_record",
    "susi",
    "susi27",
    "susi26",
    "jungsi",
    "sports_motion",
    "sports_max",
    "student_private",
    "internal_db",
})

AGENT_REACH_PUBLIC_CHANNELS = frozenset({
    "web",
    "youtube",
    "github",
    "rss",
    "bilibili",
    "v2ex",
})

SOCIAL_OR_LOGIN_CHANNELS = frozenset({
    "twitter",
    "x",
    "reddit",
    "linkedin",
    "xiaohongshu",
    "xueqiu",
    "xiaoyuzhou",
})

LEGACY_BACKENDS: dict[str, list[str]] = {
    "web": ["web_extract", "web_search"],
    "exa_search": ["web_search"],
    "youtube": ["youtube_analyze_video"],
    "github": ["web_search", "terminal:gh"],
    "rss": ["web_extract", "terminal:feedparser"],
    "twitter": ["x_search"],
    "x": ["x_search"],
    "reddit": ["web_search"],
    "linkedin": ["web_search", "web_extract"],
}

SPECIALIZED_DOMAIN_BACKENDS: dict[str, list[str]] = {
    "academy": ["academy_*", "academy_api_query"],
    "paca": ["academy_*", "academy_api_query"],
    "peak": ["academy_*", "academy_api_query"],
    "life_record": ["life_record_*"],
    "student_record": ["life_record_*", "academy_student_*"],
    "susi": ["susi27_*", "susi26_rule_lookup"],
    "susi27": ["susi27_*"],
    "jungsi": ["jungsi_*"],
    "sports_motion": ["sports_motion_*", "sports_max_analysis_variables"],
    "sports_max": ["sports_max_analysis_variables", "sports_motion_*"],
}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


def _normalize_channel(channel: str) -> str:
    value = (channel or "").strip().lower().replace("-", "_")
    if value in {"x", "x_search"}:
        return "twitter"
    if value in {"url", "page", "reader", "jina"}:
        return "web"
    if value in {"yt", "video"}:
        return "youtube"
    return value


def _domain_markers(intent: dict[str, Any]) -> set[str]:
    markers: set[str] = set()
    for key in ("domain", "source_type", "task_type", "data_domain"):
        for item in _as_list(intent.get(key)):
            normalized = item.strip().lower().replace("-", "_")
            if normalized:
                markers.add(normalized)
    return markers


def _candidate_channels(intent: dict[str, Any]) -> list[str]:
    raw = intent.get("candidate_channels") or intent.get("channels") or intent.get("channel")
    channels = [_normalize_channel(item) for item in _as_list(raw)]
    seen: set[str] = set()
    out: list[str] = []
    for channel in channels:
        if channel and channel not in seen:
            out.append(channel)
            seen.add(channel)
    return out


def research_router_tool(args: dict[str, Any] | None = None, **_: Any) -> str:
    """LLM-mapped, status-checked research router.

    The router intentionally refuses to infer meaning from keywords. The caller
    must provide an LLM mapping in ``llm_intent``. This lets the model decide the
    source/output mapping while deterministic code only enforces safety and live
    availability.
    """
    args = args or {}
    request = str(args.get("request") or "").strip()
    intent = args.get("llm_intent")
    if not request:
        return json.dumps({"success": False, "error": "request is required"}, ensure_ascii=True)
    if not isinstance(intent, dict) or not intent:
        return json.dumps({
            "success": False,
            "error": "llm_intent is required; research_router does not perform Python keyword fallback semantic routing",
            "policy": "LLM maps intent/source/output; deterministic code only checks safety/status.",
        }, ensure_ascii=True)

    channels: dict[str, dict[str, Any]] = {}
    status_error: str | None = None
    if args.get("run_doctor", True):
        doctor_channels, _, status_error = _run_doctor()
        channels = cast(dict[str, dict[str, Any]], doctor_channels)

    markers = _domain_markers(intent)
    private_or_internal = _as_bool(intent.get("uses_private_or_internal_data")) or bool(markers & INTERNAL_DOMAIN_MARKERS)
    may_write = _as_bool(intent.get("may_write")) or _as_bool(intent.get("requires_write")) or _as_bool(intent.get("account_action"))
    requires_login = _as_bool(intent.get("requires_login")) or _as_bool(intent.get("requires_cookie"))
    needs_summary_card = _as_bool(intent.get("needs_youtube_summary_card")) or str(intent.get("desired_output", "")).lower() in {"youtube_summary_card", "youtube_rag_summary"}

    if private_or_internal:
        specialized = sorted({backend for marker in markers for backend in SPECIALIZED_DOMAIN_BACKENDS.get(marker, [])})
        return json.dumps({
            "success": True,
            "decision": "blocked_from_agent_reach",
            "request": request,
            "selected_backend": specialized[0] if specialized else "specialized_domain_tool",
            "backend_family": "specialized_internal_tool",
            "specialized_backends": specialized,
            "reason": "Internal/private academy, admissions, student, sports, or DB data must use dedicated Miho tools, not public research backends.",
            "safety": "No search executed. No account action. No private data exported.",
        }, ensure_ascii=True)

    if may_write or requires_login:
        return json.dumps({
            "success": True,
            "decision": "blocked",
            "request": request,
            "selected_backend": None,
            "reason": "Research Router is read-only and must not perform login, cookie import, posting, DM, comment, follow, or other account/write actions.",
            "safety": "No search executed. No platform/account action performed.",
        }, ensure_ascii=True)

    candidates = _candidate_channels(intent)
    if not candidates:
        return json.dumps({
            "success": False,
            "decision": "unroutable",
            "request": request,
            "error": "LLM mapping did not provide candidate_channels; refusing Python semantic fallback.",
        }, ensure_ascii=True)

    plans: list[dict[str, Any]] = []
    for channel in candidates:
        status = channels.get(channel, {})
        status_value = status.get("status", "unknown")
        agent_reach_allowed = channel in AGENT_REACH_PUBLIC_CHANNELS and status_value == "ok" and not needs_summary_card
        legacy = LEGACY_BACKENDS.get(channel, [])
        if channel == "youtube" and needs_summary_card:
            legacy = ["youtube_analyze_video"] + [b for b in legacy if b != "youtube_analyze_video"]
        if channel in SOCIAL_OR_LOGIN_CHANNELS and status_value != "ok":
            backend = legacy[0] if legacy else None
            family = "legacy_or_unavailable"
            allowed = bool(backend)
            reason = "Agent Reach channel is social/login-sensitive or unavailable; use guarded legacy read-only backend only if appropriate."
        elif agent_reach_allowed:
            backend = f"agent_reach:{channel}"
            family = "agent_reach"
            allowed = True
            reason = "Agent Reach public read-only channel is available."
        else:
            backend = legacy[0] if legacy else None
            family = "legacy"
            allowed = bool(backend)
            reason = "Agent Reach unavailable/unsuitable for this output; use existing Miho backend."
        plans.append({
            "channel": channel,
            "status": status_value,
            "active_backend": status.get("active_backend"),
            "selected_backend": backend,
            "backend_family": family,
            "allowed": allowed,
            "reason": reason,
            "legacy_fallbacks": legacy,
        })

    selected = next((plan for plan in plans if plan.get("allowed") and plan.get("selected_backend")), None)
    decision = "planned" if selected else "unroutable"
    return json.dumps({
        "success": True,
        "decision": decision,
        "request": request,
        "llm_intent": intent,
        "selected_backend": selected.get("selected_backend") if selected else None,
        "backend_family": selected.get("backend_family") if selected else None,
        "plans": plans,
        "status_error": status_error,
        "policy": {
            "llm_mapping_required": True,
            "python_semantic_fallback": False,
            "agent_reach_scope": "public read-only channel collection only",
            "internal_domain_tools_protected": True,
        },
        "safety": "Planner only. It does not execute searches, installs, cookie imports, login, writes, or platform actions.",
    }, ensure_ascii=True)


registry.register(
    name="agent_reach_status",
    toolset="agent_reach",
    schema=AGENT_REACH_STATUS_SCHEMA,
    handler=agent_reach_status_tool,
    emoji="AR",
    max_result_size_chars=60_000,
)

registry.register(
    name="agent_reach_route",
    toolset="agent_reach",
    schema=AGENT_REACH_ROUTE_SCHEMA,
    handler=agent_reach_route_tool,
    emoji="AR",
    max_result_size_chars=60_000,
)

registry.register(
    name="research_router",
    toolset="web",
    schema=RESEARCH_ROUTER_SCHEMA,
    handler=research_router_tool,
    emoji="RR",
    max_result_size_chars=60_000,
)
