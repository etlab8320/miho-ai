"""Discord URL button sender for academy login links."""

from __future__ import annotations

import logging
from typing import Any

from tools.url_safety import is_safe_url

logger = logging.getLogger(__name__)


async def send_discord_link_button(
    *,
    adapter: Any,
    chat_id: str,
    content: str,
    button_label: str,
    url: str,
    title: str,
    metadata: dict[str, str] | None = None,
) -> bool:
    if not is_safe_url(url):
        return False

    try:
        from plugins.platforms.discord import adapter as discord_adapter

        discord = discord_adapter.discord
        if not discord_adapter.DISCORD_AVAILABLE or discord is None:
            return False
        client = getattr(adapter, "_client", None)
        if client is None:
            return False

        target_id = (metadata or {}).get("thread_id") or chat_id
        channel = client.get_channel(int(target_id))
        if not channel:
            channel = await client.fetch_channel(int(target_id))

        body = str(content or "").strip()
        if len(body) > 4088:
            body = body[:4085] + "..."
        embed = discord.Embed(
            title=title,
            description=body,
            color=discord.Color.blue(),
        )
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                label=str(button_label or "Open")[:80],
                style=discord.ButtonStyle.link,
                url=url,
            )
        )
        await channel.send(embed=embed, view=view)
        return True
    except Exception as exc:
        logger.warning("Academy Discord link button send failed: %s", exc)
        return False
