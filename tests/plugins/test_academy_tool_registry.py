"""Tests for academy tool registration metadata consistency."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins import academy_ops


class _ToolRegistryContext:
    def __init__(self) -> None:
        self.tools: list[str] = []

    def register_tool(self, *, name: str, **_: Any) -> None:
        self.tools.append(name)

    def register_command(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def register_hook(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def register_auxiliary_task(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _plugin_yaml_tools() -> list[str]:
    lines = Path("plugins/academy_ops/plugin.yaml").read_text(encoding="utf-8").splitlines()
    tools: list[str] = []
    in_tools = False
    for line in lines:
        stripped = line.strip()
        if stripped == "tools:":
            in_tools = True
            continue
        if in_tools and line and not line.startswith(" ") and not line.startswith("-"):
            break
        if in_tools and stripped.startswith("- "):
            tools.append(stripped[2:])
    return tools


def test_academy_plugin_yaml_matches_runtime_registered_tools() -> None:
    ctx = _ToolRegistryContext()

    academy_ops.register(ctx)

    assert _plugin_yaml_tools() == ctx.tools
    assert "academy_staff_attendance_range" in ctx.tools
