"""Tool for saving the current Discord user's onboarding profile."""

from __future__ import annotations

from typing import Any

from gateway.discord_user_profile import load_discord_user_profile, upsert_discord_user_profile
from gateway.session_context import get_session_env
from tools.registry import registry, tool_result


DISCORD_PROFILE_SCHEMA = {
    "name": "discord_profile",
    "description": (
        "Save or read the current Discord user's personal profile from onboarding answers. "
        "Use only when MIHO_SESSION_PLATFORM is discord. Save only facts the user explicitly "
        "provided, such as preferred name, main use cases, response style, or boundaries. "
        "Do not store one Discord user's profile in owner_profile or shared USER.md."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["upsert", "read"],
                "description": "Use upsert to save profile fields, read to inspect the current profile.",
            },
            "preferred_name": {
                "type": "string",
                "description": "What the current Discord user wants to be called.",
            },
            "main_use_cases": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Main jobs the user wants Miho to help with.",
            },
            "response_style": {
                "type": "string",
                "description": "Preferred answer style, e.g. concise, detailed, friendly.",
            },
            "important_boundaries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Things the user explicitly asks Miho to avoid or respect.",
            },
            "notes": {
                "type": "string",
                "description": "Other compact profile notes explicitly provided by the user.",
            },
        },
        "required": ["action"],
    },
}


def discord_profile_tool(args: dict[str, Any]) -> str:
    platform = get_session_env("MIHO_SESSION_PLATFORM", "")
    user_id = get_session_env("MIHO_SESSION_USER_ID", "")
    if platform != "discord" or not user_id:
        return tool_result(success=False, error="discord_context_required")

    action = str(args.get("action") or "").strip()
    if action == "read":
        return tool_result(success=True, profile=load_discord_user_profile(user_id))
    if action != "upsert":
        return tool_result(success=False, error="unknown_action")

    profile = upsert_discord_user_profile(
        user_id,
        preferred_name=str(args.get("preferred_name") or ""),
        main_use_cases=_string_list(args.get("main_use_cases")),
        response_style=str(args.get("response_style") or ""),
        important_boundaries=_string_list(args.get("important_boundaries")),
        notes=str(args.get("notes") or ""),
    )
    return tool_result(success=True, profile=profile)


def _string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    text = str(value or "").strip()
    return [text] if text else []


registry.register(
    name="discord_profile",
    toolset="memory",
    schema=DISCORD_PROFILE_SCHEMA,
    handler=lambda args, **_: discord_profile_tool(args),
)
