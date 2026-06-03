from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import struct
import subprocess
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path as _Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    MessageEvent,
    MessageType,
    ProcessingOutcome,
    SendResult,
    SUPPORTED_DOCUMENT_TYPES,
    SUPPORTED_VIDEO_TYPES,
    cache_audio_from_bytes,
    cache_audio_from_url,
    cache_document_from_bytes,
    cache_image_from_bytes,
    cache_image_from_url,
    cache_video_from_bytes,
)
from gateway.platforms.helpers import MessageDeduplicator, ThreadParticipationTracker
from tools.url_safety import is_safe_url
from utils import atomic_json_write

from .helpers import (
    VALID_THREAD_AUTO_ARCHIVE_MINUTES,
    _DISCORD_COMMAND_SYNC_MAX_RATE_LIMIT_SLEEP_SECONDS,
    _DISCORD_COMMAND_SYNC_MUTATION_INTERVAL_SECONDS,
    _DISCORD_COMMAND_SYNC_POLICIES,
    _DISCORD_COMMAND_SYNC_STATE_FILENAME,
    _DISCORD_COMMAND_SYNC_STATE_SUBDIR,
    _clean_discord_id,
    _derive_forum_thread_name,
    _discord_brand,
    _is_unknown_discord_channel_error,
    _probe_is_forum_cached,
    _read_dm_role_auth_guild,
    _remember_channel_is_forum,
    _thread_created_message,
)

logger = logging.getLogger("miho_plugins.discord_platform.adapter")

try:
    import discord
    from discord import Message as DiscordMessage, Intents
    from discord.ext import commands

    DISCORD_AVAILABLE = True
except ImportError:
    discord = None
    DiscordMessage = Any
    Intents = Any
    commands = None
    DISCORD_AVAILABLE = False


def _build_allowed_mentions():
    if not DISCORD_AVAILABLE:
        return None

    def _b(name: str, default: bool) -> bool:
        raw = os.getenv(name, "").strip().lower()
        if not raw:
            return default
        return raw in {"true", "1", "yes", "on"}

    return discord.AllowedMentions(
        everyone=_b("DISCORD_ALLOW_MENTION_EVERYONE", False),
        roles=_b("DISCORD_ALLOW_MENTION_ROLES", False),
        users=_b("DISCORD_ALLOW_MENTION_USERS", True),
        replied_user=_b("DISCORD_ALLOW_MENTION_REPLIED_USER", True),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
