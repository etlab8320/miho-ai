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
from typing import Any

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
