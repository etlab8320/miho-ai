"""Tool for Miho's owner profile and autobiography timeline."""

from __future__ import annotations

from miho_cli.owner_profile import (
    append_profile_event,
    append_to_master_profile,
    ensure_daily_summary_job,
    list_profile_events,
    read_master_profile,
    replace_master_profile,
)
from tools.registry import registry, tool_error, tool_result


OWNER_PROFILE_SCHEMA = {
    "name": "owner_profile",
    "description": (
        "Read and maintain the owner's long-form profile. Use this proactively "
        "when the user shares durable personal history, identity, values, working "
        "style, business context, long-term goals, life events, recurring emotional "
        "context, or preferences that are richer than a compact USER.md fact. "
        "Use memory(target='user') for short stable facts; use owner_profile for "
        "deep context and dated autobiography-like timeline entries."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "read_master",
                    "replace_master",
                    "append_to_master",
                    "append_event",
                    "list_events",
                    "ensure_daily_summary",
                ],
                "description": "Profile action to perform.",
            },
            "title": {
                "type": "string",
                "description": "Short title for append_to_master or append_event.",
            },
            "category": {
                "type": "string",
                "description": "Timeline category such as identity, work, health, business, preference.",
            },
            "content": {
                "type": "string",
                "description": "Profile text for replace_master, append_to_master, or append_event.",
            },
            "source": {
                "type": "string",
                "description": "Source label, for example discord, cli, or manual.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum timeline rows for list_events.",
            },
            "schedule": {
                "type": "string",
                "description": "Cron expression for ensure_daily_summary. Defaults to 0 23 * * *.",
            },
        },
        "required": ["action"],
    },
}


def owner_profile_tool(args: dict) -> str:
    action = str(args.get("action") or "").strip()
    source = str(args.get("source") or "owner_profile").strip()

    if action == "read_master":
        return tool_result(success=True, content=read_master_profile(max_chars=12000))

    if action == "replace_master":
        content = args.get("content")
        if not content:
            return tool_error("content is required for replace_master", success=False)
        return tool_result(replace_master_profile(str(content), source=source))

    if action == "append_to_master":
        content = args.get("content")
        if not content:
            return tool_error("content is required for append_to_master", success=False)
        result = append_to_master_profile(
            title=str(args.get("title") or "Profile update"),
            content=str(content),
            source=source,
        )
        return tool_result(result)

    if action == "append_event":
        content = args.get("content")
        if not content:
            return tool_error("content is required for append_event", success=False)
        result = append_profile_event(
            category=str(args.get("category") or "general"),
            title=str(args.get("title") or "Profile event"),
            content=str(content),
            source=source,
        )
        return tool_result(result)

    if action == "list_events":
        events = list_profile_events(
            limit=int(args.get("limit") or 20),
            category=args.get("category"),
        )
        return tool_result(success=True, events=events)

    if action == "ensure_daily_summary":
        return tool_result(
            ensure_daily_summary_job(schedule=str(args.get("schedule") or "0 23 * * *"))
        )

    return tool_error(
        "Unknown action. Use read_master, replace_master, append_to_master, "
        "append_event, list_events, or ensure_daily_summary.",
        success=False,
    )


def check_owner_profile_requirements() -> bool:
    return True


registry.register(
    name="owner_profile",
    toolset="owner_profile",
    schema=OWNER_PROFILE_SCHEMA,
    handler=lambda args, **kw: owner_profile_tool(args),
    check_fn=check_owner_profile_requirements,
    emoji="🦊",
)
