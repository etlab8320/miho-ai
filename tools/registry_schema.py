"""Model-facing schema normalization for registered tools."""

from __future__ import annotations

from typing import Any


def function_schema_from_entry(
    *,
    name: str,
    schema: dict[str, Any],
    description: str = "",
    dynamic_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an OpenAI function schema for built-in and plugin-style tools."""
    raw = dict(schema or {})
    if dynamic_overrides:
        raw.update(dynamic_overrides)
    if isinstance(raw.get("parameters"), dict):
        function_schema = dict(raw)
        function_schema["name"] = str(function_schema.get("name") or name)
        if description and not function_schema.get("description"):
            function_schema["description"] = description
        return function_schema

    parameters = dict(raw)
    parameters.pop("name", None)
    schema_description = str(parameters.pop("description", "") or "")
    return {
        "name": name,
        "description": description or schema_description,
        "parameters": parameters,
    }
