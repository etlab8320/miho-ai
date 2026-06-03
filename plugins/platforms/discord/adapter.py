from __future__ import annotations

"""
Discord platform adapter.

Uses discord.py library for:
- Receiving messages from servers and DMs
- Sending responses back
- Handling threads and channels
"""

import asyncio
import hashlib
import json
import logging
import os
import struct
import subprocess
import tempfile
import threading
import time
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

VALID_THREAD_AUTO_ARCHIVE_MINUTES = {60, 1440, 4320, 10080}
_DISCORD_COMMAND_SYNC_POLICIES = {"safe", "bulk", "off"}
_DISCORD_COMMAND_SYNC_STATE_SUBDIR = "gateway"
_DISCORD_COMMAND_SYNC_STATE_FILENAME = "discord_command_sync_state.json"
_DISCORD_COMMAND_SYNC_MUTATION_INTERVAL_SECONDS = 4.5
_DISCORD_COMMAND_SYNC_MAX_RATE_LIMIT_SLEEP_SECONDS = 30.0

try:
    import discord
    from discord import Message as DiscordMessage, Intents
    from discord.ext import commands
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    discord = None
    DiscordMessage = Any
    Intents = Any
    commands = None

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

from gateway.config import Platform, PlatformConfig
from miho_cli.brand import current_brand
import re

from gateway.platforms.helpers import MessageDeduplicator, ThreadParticipationTracker
from utils import atomic_json_write
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    ProcessingOutcome,
    SendResult,
    cache_image_from_url,
    cache_image_from_bytes,
    cache_audio_from_url,
    cache_audio_from_bytes,
    cache_document_from_bytes,
    cache_video_from_bytes,
    SUPPORTED_DOCUMENT_TYPES,
    SUPPORTED_VIDEO_TYPES,
)
from tools.url_safety import is_safe_url
from .attachment_mixin import DiscordAttachmentMixin
from .audio_typing_mixin import DiscordAudioTypingMixin
from .auth_mixin import DiscordAuthMixin
from .channel_config_mixin import DiscordChannelConfigMixin
from .command_sync_mixin import DiscordCommandSyncMixin
from .lifecycle_mixin import DiscordLifecycleMixin
from .media_mixin import DiscordMediaMixin
from .message_mixin import DiscordMessageMixin
from .send_mixin import DiscordSendMixin
from .skill_slash_mixin import DiscordSkillSlashMixin
from .slash_commands_mixin import DiscordSlashCommandsMixin
from .text_batch_mixin import DiscordTextBatchMixin
from .thread_mixin import DiscordThreadMixin
from .ui_prompt_mixin import DiscordUiPromptMixin
from .voice_mixin import DiscordVoiceMixin
from .views import (
    VIEW_NAMES,
    _component_check_auth,
    define_discord_view_classes,
)
from .helpers import (
    _clean_discord_id,
    _clean_discord_user_ids,
    _derive_forum_thread_name,
    _discord_brand,
    _is_unknown_discord_channel_error,
    _probe_is_forum_cached,
    _read_dm_role_auth_guild,
    _remember_channel_is_forum,
    _standalone_sanitize_error,
    _thread_created_message,
)
from .setup_config import _apply_yaml_config, _is_connected, interactive_setup
from .standalone import _standalone_send
from .voice_receiver import VoiceReceiver










def check_discord_requirements() -> bool:
    """Check if Discord dependencies are available.

    Lazy-installs discord.py via ``tools.lazy_deps.ensure("platform.discord")``
    on first call if not present. After successful install, re-binds module
    globals so ``DISCORD_AVAILABLE`` becomes True.
    """
    global DISCORD_AVAILABLE, discord, DiscordMessage, Intents, commands
    if DISCORD_AVAILABLE:
        return True
    try:
        from tools.lazy_deps import ensure as _lazy_ensure
        _lazy_ensure("platform.discord", prompt=False)
    except Exception:
        return False
    try:
        import discord as _discord
        from discord import Message as _DM, Intents as _Intents
        from discord.ext import commands as _commands
    except ImportError:
        return False
    discord = _discord
    DiscordMessage = _DM
    Intents = _Intents
    commands = _commands
    DISCORD_AVAILABLE = True
    _define_discord_view_classes()
    return True


def _build_allowed_mentions():
    """Build Discord ``AllowedMentions`` with safe defaults, overridable via env.

    Discord bots default to parsing ``@everyone``, ``@here``, role pings, and
    user pings when ``allowed_mentions`` is unset on the client — any LLM
    output or echoed user content that contains ``@everyone`` would therefore
    ping the whole server. We explicitly deny ``@everyone`` and role pings
    by default and keep user / replied-user pings enabled so normal
    conversation still works.

    Override via environment variables (or ``discord.allow_mentions.*`` in
    config.yaml):

        DISCORD_ALLOW_MENTION_EVERYONE      default false  — @everyone + @here
        DISCORD_ALLOW_MENTION_ROLES         default false  — @role pings
        DISCORD_ALLOW_MENTION_USERS         default true   — @user pings
        DISCORD_ALLOW_MENTION_REPLIED_USER  default true   — reply-ping author
    """
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






class DiscordAdapter(
    DiscordLifecycleMixin,
    DiscordCommandSyncMixin,
    DiscordSendMixin,
    DiscordMediaMixin,
    DiscordAudioTypingMixin,
    DiscordVoiceMixin,
    DiscordAuthMixin,
    DiscordSlashCommandsMixin,
    DiscordSkillSlashMixin,
    DiscordChannelConfigMixin,
    DiscordThreadMixin,
    DiscordUiPromptMixin,
    DiscordAttachmentMixin,
    DiscordMessageMixin,
    DiscordTextBatchMixin,
    BasePlatformAdapter,
):
    """
    Discord bot adapter.

    Handles:
    - Receiving messages from servers and DMs
    - Sending responses with Discord markdown
    - Thread support
    - Native slash commands (/ask, /reset, /status, /stop)
    - Button-based exec approvals
    - Auto-threading for long conversations
    - Reaction-based feedback
    """

    # Discord message limits
    MAX_MESSAGE_LENGTH = 2000
    _SPLIT_THRESHOLD = 1900  # near the 2000-char split point

    # Auto-disconnect from voice channel after this many seconds of inactivity
    VOICE_TIMEOUT = 300





















    # ------------------------------------------------------------------
    # Voice channel methods (join / leave / play)
    # ------------------------------------------------------------------



    # Maximum seconds to wait for voice playback before giving up
    PLAYBACK_TIMEOUT = 120








    # ------------------------------------------------------------------
    # Voice listening (Phase 2)
    # ------------------------------------------------------------------

    # UDP keepalive interval in seconds — prevents Discord from dropping
    # the UDP route after ~60s of silence.
    _KEEPALIVE_INTERVAL = 15




    # ── Slash command authorization ─────────────────────────────────────
    # Slash commands (``_run_simple_slash`` and ``_handle_thread_create_slash``)
    # are a separate Discord interaction surface from regular messages and
    # historically ran with NO authorization check — bypassing every gate
    # ``on_message`` enforces (DISCORD_ALLOWED_USERS, DISCORD_ALLOWED_ROLES,
    # DISCORD_ALLOWED_CHANNELS, DISCORD_IGNORED_CHANNELS). Any guild member
    # could invoke ``/background``, ``/restart``, ``/sethome``, etc. as the
    # operator. ``_check_slash_authorization`` mirrors the on_message gates
    # one-for-one so the slash surface honors the same trust boundary.
    #
    # By design, this is a no-op for deployments with no allowlist env vars
    # set — ``_is_allowed_user`` returns True and the channel checks early-out
    # — preserving the existing "single-tenant, all guild members trusted"
    # default. Deployments that DO set any DISCORD_ALLOWED_* var get slash
    # parity with on_message.






















    # ------------------------------------------------------------------
    # Thread creation helpers
    # ------------------------------------------------------------------









    # ------------------------------------------------------------------
    # Auto-thread helpers
    # ------------------------------------------------------------------













    # ------------------------------------------------------------------
    # Attachment download helpers
    #
    # Discord attachments (images / audio / documents) are fetched via the
    # authenticated bot session whenever the Attachment object exposes
    # ``read()``. That sidesteps two classes of bug that hit the older
    # plain-HTTP path:
    #
    #   1. ``cdn.discordapp.com`` URLs increasingly require bot auth on
    #      download — unauthenticated httpx sees 403 Forbidden.
    #      (issue #8242)
    #   2. Some user environments (VPNs, corporate DNS, tunnels) resolve
    #      ``cdn.discordapp.com`` to private-looking IPs that our
    #      ``is_safe_url`` guard classifies as SSRF risks. Routing the
    #      fetch through discord.py's own HTTP client handles DNS
    #      internally so our guard isn't consulted for the attachment
    #      path. (issue #6587)
    #
    # If ``att.read()`` is unavailable (unexpected object shape / test
    # stub) or the bot session fetch fails, we fall back to the existing
    # SSRF-gated URL downloaders. The fallback keeps defense-in-depth
    # against any future Discord payload-schema drift that could slip a
    # non-CDN URL into the ``att.url`` field. (issue #11345)
    # ------------------------------------------------------------------






    # ------------------------------------------------------------------
    # Text message aggregation (handles Discord client-side splits)
    # ------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Discord UI Components (outside the adapter class)
# ---------------------------------------------------------------------------


def _define_discord_view_classes() -> None:
    define_discord_view_classes()
    from . import views as _discord_views
    for name in VIEW_NAMES:
        globals()[name] = getattr(_discord_views, name)


for _view_name in VIEW_NAMES:
    globals().setdefault(_view_name, None)


if DISCORD_AVAILABLE:
    _define_discord_view_classes()


# ── Standalone (out-of-process) sender ────────────────────────────────────────
# Used by ``tools/send_message_tool._send_via_adapter`` when the gateway runner
# is not in this process (e.g. ``miho cron`` running standalone) and no live
# DiscordAdapter instance is available.  Implements the same forum/thread/
# multipart logic the live adapter would use, via Discord's REST API directly.
#
# This block was previously hosted in ``tools/send_message_tool.py`` as
# ``_send_discord``.  It moved into the plugin so all Discord-specific HTTP
# logic lives next to the adapter — same shape as Teams' ``_standalone_send``.

# Process-local cache for Discord channel-type probes.  Avoids re-probing the
# same channel on every send when the directory cache has no entry (e.g. fresh
# install, or channel created after the last directory build).
_DISCORD_CHANNEL_TYPE_PROBE_CACHE: Dict[str, bool] = {}












# ── Plugin entry point ────────────────────────────────────────────────────────










def _build_adapter(config):
    """Factory wrapper that constructs DiscordAdapter from a PlatformConfig."""
    return DiscordAdapter(config)


def register(ctx) -> None:
    """Plugin entry point — called by the Miho plugin system."""
    ctx.register_platform(
        name="discord",
        label="Discord",
        adapter_factory=_build_adapter,
        check_fn=check_discord_requirements,
        is_connected=_is_connected,
        required_env=["DISCORD_BOT_TOKEN"],
        install_hint="pip install 'miho-agent[discord]'",
        # Interactive setup wizard — replaces the central
        # miho_cli/setup.py::_setup_discord function.  Same shape as Teams.
        setup_fn=interactive_setup,
        # YAML→env config bridge — owns the translation of ``config.yaml``
        # ``discord:`` keys (require_mention, free_response_channels,
        # auto_thread, reactions, ignored_channels, allowed_channels,
        # no_thread_channels, allow_mentions.*, reply_to_mode,
        # thread_require_mention) into ``DISCORD_*`` env vars that the
        # adapter reads via ``os.getenv()``.  Replaces the hardcoded block
        # that used to live in ``gateway/config.py``.  Hook contract: #24836.
        apply_yaml_config_fn=_apply_yaml_config,
        # Auth env vars for _is_user_authorized() integration
        allowed_users_env="DISCORD_ALLOWED_USERS",
        allow_all_env="DISCORD_ALLOW_ALL_USERS",
        # Cron home-channel delivery
        cron_deliver_env_var="DISCORD_HOME_CHANNEL",
        # Out-of-process cron delivery via Discord REST API.  Without this
        # hook, ``deliver=discord`` cron jobs fail with "No live adapter"
        # when cron runs separately from the gateway.  Mirrors Teams pattern.
        standalone_sender_fn=_standalone_send,
        # Discord hard limit per message
        max_message_length=2000,
        # Display
        emoji="🎮",
        allow_update_command=True,
    )
