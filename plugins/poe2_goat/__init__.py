"""PoE2 GOAT Builder Discord/tool integration."""

from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path("/Users/etlab/projects/poe2-goat-builder")
PYTHON_BIN = PROJECT_ROOT / ".venv" / "bin" / "python"
POE2_ROUTE_PRIORITY = 46


def _parse_poe2_request(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    lower = raw.lower()
    if "poe2" not in lower and "poe 2" not in lower and "패오엑2" not in lower:
        return None
    if not any(token in lower for token in ["딥", "div", "빌드", "소환", "minion", "summoner", "인퍼", "infernal", "lich", "리치"]):
        return None

    budget = 50.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:딥|div|divine)", lower)
    if m:
        budget = float(m.group(1))

    ascendancy = None
    if any(token in lower for token in ["인퍼", "infernal", "infernalist"]):
        ascendancy = "Infernalist"
    elif any(token in lower for token in ["리치", "lich"]):
        ascendancy = "Lich"
    elif "blood" in lower or "블러드" in lower:
        ascendancy = "Blood Mage"

    archetype = "summoner" if any(token in lower for token in ["소환", "minion", "summoner"]) else "summoner"

    core_item = None
    known_cores = ["The Raven's Flock", "Dark Defiler", "Font of Power", "Enfolding Dawn"]
    for item in known_cores:
        if item.lower() in lower:
            core_item = item
            break

    return {
        "archetype": archetype,
        "ascendancy": ascendancy,
        "core_item": core_item,
        "budget_div": budget,
        "format": "markdown",
    }


def _tool_handler(args: dict[str, Any]) -> str:
    budget = float(args.get("budget_div") or 50)
    output_format = str(args.get("format") or "markdown")
    cmd = [
        str(PYTHON_BIN if PYTHON_BIN.exists() else "python3"),
        "-m",
        "poe2goat.cli",
        "build",
        "--archetype",
        str(args.get("archetype") or "summoner"),
        "--budget-div",
        str(budget),
        "--format",
        output_format,
    ]
    if args.get("ascendancy"):
        cmd.extend(["--ascendancy", str(args["ascendancy"])])
    if args.get("core_item"):
        cmd.extend(["--core-item", str(args["core_item"])])
    if args.get("league"):
        cmd.extend(["--league", str(args["league"])])

    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=240)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or ["unknown error"]
        return "PoE2 빌드 리포트 생성 중 문제가 생겼어. " + detail[0]
    return proc.stdout


async def _poe2_pre_gateway_dispatch(event: Any = None, **_: Any) -> dict[str, object]:
    text = str(getattr(event, "text", "") or "")
    args = _parse_poe2_request(text)
    if args is None:
        return {"action": "allow"}
    try:
        response = await asyncio.wait_for(asyncio.to_thread(_tool_handler, args), timeout=260)
    except TimeoutError:
        response = "PoE2 빌드 리포트 생성이 오래 걸리고 있어. 잠시 후 다시 시도해줘."
    except Exception as exc:  # noqa: BLE001 - Discord preflight should fail soft
        response = f"PoE2 빌드 리포트 생성 중 문제가 생겼어: {exc}"
    return {
        "action": "respond",
        "text": response,
        "route": "poe2_goat",
        "reason": "poe2_goat_preflight",
        "intent": "poe2.build_report",
        "confidence": 0.9,
        "evidence": ["poe2 build keywords"],
        "required_tool": "poe2_goat_build",
        "priority": POE2_ROUTE_PRIORITY,
    }


def register(ctx: Any) -> None:
    ctx.register_hook("pre_gateway_dispatch", _poe2_pre_gateway_dispatch)
    ctx.register_tool(
        name="poe2_goat_build",
        toolset="poe2_goat",
        schema={
            "type": "object",
            "properties": {
                "archetype": {"type": "string", "default": "summoner", "description": "Build archetype. Currently supports summoner/minion."},
                "ascendancy": {"type": "string", "description": "Ascendancy filter, e.g. Infernalist, Lich, Blood Mage."},
                "core_item": {"type": "string", "description": "Optional core item or concept, e.g. The Raven's Flock."},
                "budget_div": {"type": "number", "default": 50, "description": "Budget in divine orbs."},
                "league": {"type": "string", "description": "Optional PoE2 league override."},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
            "additionalProperties": False,
        },
        handler=_tool_handler,
        description="Generate a PoE2 GOAT budget build report from PoB2 data, trade2 market evidence, Scout prices, and the local oracle gate.",
    )


__all__ = ["_parse_poe2_request", "_poe2_pre_gateway_dispatch", "_tool_handler", "register"]
