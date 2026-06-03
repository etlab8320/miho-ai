from __future__ import annotations

from .mixin_deps import *
from .voice_receiver import VoiceReceiver



class DiscordLifecycleMixin:

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.DISCORD)
        self._client: Optional[commands.Bot] = None
        self._ready_event = asyncio.Event()
        self._allowed_user_ids: set = set()  # For button approval authorization
        self._allowed_role_ids: set = set()  # For DISCORD_ALLOWED_ROLES filtering
        self.gateway_runner = None  # Set by gateway/run.py for cross-platform delivery
        # Voice channel state (per-guild)
        self._voice_clients: Dict[int, Any] = {}  # guild_id -> VoiceClient
        self._voice_locks: Dict[int, asyncio.Lock] = {}  # guild_id -> serialize join/leave
        # Text batching: merge rapid successive messages (Telegram-style)
        self._text_batch_delay_seconds = float(os.getenv("MIHO_DISCORD_TEXT_BATCH_DELAY_SECONDS", "0.6"))
        self._text_batch_split_delay_seconds = float(os.getenv("MIHO_DISCORD_TEXT_BATCH_SPLIT_DELAY_SECONDS", "2.0"))
        self._pending_text_batches: Dict[str, MessageEvent] = {}
        self._pending_text_batch_tasks: Dict[str, asyncio.Task] = {}
        self._voice_text_channels: Dict[int, int] = {}  # guild_id -> text_channel_id
        self._voice_sources: Dict[int, Dict[str, Any]] = {}  # guild_id -> linked text channel source metadata
        self._voice_timeout_tasks: Dict[int, asyncio.Task] = {}  # guild_id -> timeout task
        # Phase 2: voice listening
        self._voice_receivers: Dict[int, VoiceReceiver] = {}  # guild_id -> VoiceReceiver
        self._voice_listen_tasks: Dict[int, asyncio.Task] = {}  # guild_id -> listen loop
        self._voice_input_callback: Optional[Callable] = None  # set by run.py
        self._on_voice_disconnect: Optional[Callable] = None  # set by run.py
        # Track threads where the bot has participated so follow-up messages
        # in those threads don't require @mention.  Persisted to disk so the
        # set survives gateway restarts.
        self._threads = ThreadParticipationTracker("discord")
        # Persistent typing indicator loops per channel (DMs don't reliably
        # show the standard typing gateway event for bots)
        self._typing_tasks: Dict[str, asyncio.Task] = {}
        self._bot_task: Optional[asyncio.Task] = None
        self._post_connect_task: Optional[asyncio.Task] = None
        # Dedup cache: prevents duplicate bot responses when Discord
        # RESUME replays events after reconnects.
        self._dedup = MessageDeduplicator()
        # Reply threading mode: "off" (no replies), "first" (reply on first
        # chunk only, default), "all" (reply-reference on every chunk).
        self._reply_to_mode: str = getattr(config, 'reply_to_mode', 'first') or 'first'
        self._slash_commands: bool = self.config.extra.get("slash_commands", True)
        # In-memory cache of the bot's last message ID per channel, used by
        # history backfill to skip the full scan on hot paths.  Falls back to
        # scanning channel.history() on cache miss (cold start / restart).
        self._last_self_message_id: Dict[str, str] = {}


    async def _apply_brand_presence(self) -> None:
        if not self._client or not DISCORD_AVAILABLE:
            return
        change_presence = getattr(self._client, "change_presence", None)
        activity_cls = getattr(discord, "Activity", None)
        activity_type = getattr(getattr(discord, "ActivityType", None), "watching", None)
        if not change_presence or not activity_cls or activity_type is None:
            return
        status_text = (
            self.config.extra.get("status_text")
            or os.getenv("DISCORD_STATUS_TEXT")
            or _discord_brand().discord_status
        )
        if not str(status_text).strip():
            return
        try:
            await change_presence(activity=activity_cls(type=activity_type, name=str(status_text).strip()))
        except Exception:
            logger.debug("[%s] Failed to update Discord presence", self.name, exc_info=True)


    async def connect(self) -> bool:
        """Connect to Discord and start receiving events."""
        if not DISCORD_AVAILABLE:
            logger.error("[%s] discord.py not installed. Run: pip install discord.py", self.name)
            return False

        # Load opus codec for voice channel support
        if not discord.opus.is_loaded():
            import ctypes.util
            opus_path = ctypes.util.find_library("opus")
            # ctypes.util.find_library fails on macOS with Homebrew-installed libs,
            # so fall back to known Homebrew paths if needed.
            if not opus_path:
                _homebrew_paths = (
                    "/opt/homebrew/lib/libopus.dylib",  # Apple Silicon
                    "/usr/local/lib/libopus.dylib",     # Intel Mac
                )
                if sys.platform == "darwin":
                    for _hp in _homebrew_paths:
                        if os.path.isfile(_hp):
                            opus_path = _hp
                            break
            if opus_path:
                try:
                    discord.opus.load_opus(opus_path)
                except Exception:
                    logger.warning("Opus codec found at %s but failed to load", opus_path)
            if not discord.opus.is_loaded():
                logger.warning("Opus codec not found — voice channel playback disabled")

        if not self.config.token:
            logger.error("[%s] No bot token configured", self.name)
            return False

        try:
            if not self._acquire_platform_lock('discord-bot-token', self.config.token, 'Discord bot token'):
                return False

            # Parse allowed user entries (may contain usernames or IDs)
            allowed_env = os.getenv("DISCORD_ALLOWED_USERS", "")
            if allowed_env:
                self._allowed_user_ids = {
                    _clean_discord_id(uid) for uid in allowed_env.split(",")
                    if uid.strip()
                }

            # Parse DISCORD_ALLOWED_ROLES — comma-separated role IDs.
            # Users with ANY of these roles can interact with the bot.
            roles_env = os.getenv("DISCORD_ALLOWED_ROLES", "")
            if roles_env:
                self._allowed_role_ids = {
                    int(rid.strip()) for rid in roles_env.split(",")
                    if rid.strip().isdigit()
                }

            # Set up intents.
            # Message Content is required for normal text replies.
            # Server Members is only needed when the allowlist contains usernames
            # that must be resolved to numeric IDs. Requesting privileged intents
            # that aren't enabled in the Discord Developer Portal can prevent the
            # bot from coming online at all, so avoid requesting members intent
            # unless it is actually necessary.
            intents = Intents.default()
            intents.message_content = True
            intents.dm_messages = True
            intents.guild_messages = True
            intents.members = (
                any(not entry.isdigit() for entry in self._allowed_user_ids)
                or bool(self._allowed_role_ids)  # Need members intent for role lookup
            )
            intents.voice_states = True

            # Resolve proxy (DISCORD_PROXY > generic env vars > macOS system proxy)
            from gateway.platforms.base import resolve_proxy_url, proxy_kwargs_for_bot
            proxy_url = resolve_proxy_url(platform_env_var="DISCORD_PROXY")
            if proxy_url:
                logger.info("[%s] Using proxy for Discord: %s", self.name, proxy_url)

            # Create bot — proxy= for HTTP, connector= for SOCKS.
            # allowed_mentions is set with safe defaults (no @everyone/roles)
            # so LLM output or echoed user content can't ping the whole
            # server; override per DISCORD_ALLOW_MENTION_* env vars or the
            # discord.allow_mentions.* block in config.yaml.

            # Close any existing client to prevent zombie websocket connections
            # on reconnect (see #18187). Without this, the old client remains
            # connected to Discord gateway and both fire on_message, causing
            # double responses.
            if self._client is not None:
                try:
                    if not self._client.is_closed():
                        await self._client.close()
                except Exception:
                    logger.debug("[%s] Failed to close previous Discord client", self.name)
                finally:
                    self._client = None
                    self._ready_event.clear()

            self._client = commands.Bot(
                command_prefix="!",  # Not really used, we handle raw messages
                intents=intents,
                allowed_mentions=_build_allowed_mentions(),
                **proxy_kwargs_for_bot(proxy_url),
            )
            adapter_self = self  # capture for closure

            # Register event handlers
            @self._client.event
            async def on_ready():
                logger.info("[%s] Connected as %s", adapter_self.name, adapter_self._client.user)
                await adapter_self._apply_brand_presence()

                # Resolve any usernames in the allowed list to numeric IDs
                await adapter_self._resolve_allowed_usernames()
                adapter_self._ready_event.set()

                if adapter_self._post_connect_task and not adapter_self._post_connect_task.done():
                    adapter_self._post_connect_task.cancel()
                adapter_self._post_connect_task = asyncio.create_task(
                    adapter_self._run_post_connect_initialization()
                )

            @self._client.event
            async def on_message(message: DiscordMessage):
                # Block until _resolve_allowed_usernames has swapped
                # any raw usernames in DISCORD_ALLOWED_USERS for numeric
                # IDs (otherwise on_message's author.id lookup can miss).
                if not adapter_self._ready_event.is_set():
                    try:
                        await asyncio.wait_for(adapter_self._ready_event.wait(), timeout=30.0)
                    except asyncio.TimeoutError:
                        pass

                # Dedup: Discord RESUME replays events after reconnects (#4777)
                if adapter_self._dedup.is_duplicate(str(message.id)):
                    return

                # Always ignore our own messages
                if message.author == self._client.user:
                    return

                # Ignore Discord system messages (thread renames, pins, member joins, etc.)
                # Allow both default and reply types — replies have a distinct MessageType.
                if message.type not in {discord.MessageType.default, discord.MessageType.reply}:
                    return

                # Bot message filtering (DISCORD_ALLOW_BOTS):
                #   "none"     — ignore all other bots (default)
                #   "mentions" — accept bot messages only when they @mention us
                #   "all"      — accept all bot messages
                # Must run BEFORE the user allowlist check so that bots
                # permitted by DISCORD_ALLOW_BOTS are not rejected for
                # not being in DISCORD_ALLOWED_USERS (fixes #4466).
                if getattr(message.author, "bot", False):
                    allow_bots = os.getenv("DISCORD_ALLOW_BOTS", "none").lower().strip()
                    if allow_bots == "none":
                        return
                    elif allow_bots == "mentions":
                        if not self._client.user or self._client.user not in message.mentions:
                            return
                    # "all" falls through; bot is permitted — skip the
                    # human-user allowlist below (bots aren't in it).
                else:
                    # Non-bot: enforce the configured user/role allowlists.
                    # Pass guild + is_dm so role checks are scoped to the
                    # originating guild (prevents cross-guild DM bypass, see
                    # _is_allowed_user docstring).
                    _msg_guild = getattr(message, "guild", None)
                    _is_dm = isinstance(message.channel, discord.DMChannel) or _msg_guild is None
                    if not self._is_allowed_user(
                        str(message.author.id),
                        message.author,
                        guild=_msg_guild,
                        is_dm=_is_dm,
                    ):
                        return
                
                # Multi-agent filtering: if the message mentions specific bots
                # but NOT this bot, the sender is talking to another agent —
                # stay silent.  Messages with no bot mentions (general chat)
                # still fall through to _handle_message for the existing
                # DISCORD_REQUIRE_MENTION check.
                #
                # This replaces the older DISCORD_IGNORE_NO_MENTION logic
                # with bot-aware filtering that works correctly when multiple
                # agents share a channel.
                if not isinstance(message.channel, discord.DMChannel) and message.mentions:
                    _self_mentioned = (
                        self._client.user is not None
                        and self._client.user in message.mentions
                    )
                    _other_bots_mentioned = any(
                        m.bot and m != self._client.user
                        for m in message.mentions
                    )
                    # If other bots are mentioned but we're not → not for us
                    if _other_bots_mentioned and not _self_mentioned:
                        return
                    # If humans are mentioned but we're not → not for us
                    # (preserves old DISCORD_IGNORE_NO_MENTION=true behavior)
                    # EXCEPT in free-response channels where the bot should
                    # answer regardless of who is mentioned.
                    _ignore_no_mention = os.getenv(
                        "DISCORD_IGNORE_NO_MENTION", "true"
                    ).lower() in {"true", "1", "yes"}
                    if _ignore_no_mention and not _self_mentioned and not _other_bots_mentioned:
                        _channel_id = str(message.channel.id)
                        _parent_id = None
                        if hasattr(message.channel, "parent_id") and message.channel.parent_id:
                            _parent_id = str(message.channel.parent_id)
                        _free_channels = adapter_self._discord_free_response_channels()
                        _channel_ids = {_channel_id}
                        if _parent_id:
                            _channel_ids.add(_parent_id)
                        if "*" not in _free_channels and not (_channel_ids & _free_channels):
                            return

                await self._handle_message(message)

            @self._client.event
            async def on_guild_channel_create(channel):
                try:
                    from gateway.discord_workspace import ensure_workspace_for_channel
                    ensure_workspace_for_channel(channel)
                except Exception as exc:
                    logger.debug("[%s] Discord channel workspace init failed: %s", self.name, exc)

            @self._client.event
            async def on_thread_create(thread):
                try:
                    from gateway.discord_workspace import ensure_workspace_for_thread
                    ensure_workspace_for_thread(thread)
                except Exception as exc:
                    logger.debug("[%s] Discord thread workspace init failed: %s", self.name, exc)

            @self._client.event
            async def on_guild_channel_delete(channel):
                try:
                    from gateway.discord_workspace import archive_workspace_for_channel
                    archive_workspace_for_channel(channel)
                except Exception as exc:
                    logger.debug("[%s] Discord channel workspace archive failed: %s", self.name, exc)

            @self._client.event
            async def on_thread_delete(thread):
                try:
                    from gateway.discord_workspace import archive_workspace_for_thread
                    archive_workspace_for_thread(thread)
                except Exception as exc:
                    logger.debug("[%s] Discord thread workspace archive failed: %s", self.name, exc)

            @self._client.event
            async def on_voice_state_update(member, before, after):
                """Track voice channel join/leave events."""
                # Only track channels where the bot is connected
                bot_guild_ids = set(adapter_self._voice_clients.keys())
                if not bot_guild_ids:
                    return
                guild_id = member.guild.id
                if guild_id not in bot_guild_ids:
                    return
                # Ignore the bot itself
                if member == adapter_self._client.user:
                    return

                joined = before.channel is None and after.channel is not None
                left = before.channel is not None and after.channel is None
                switched = (
                    before.channel is not None
                    and after.channel is not None
                    and before.channel != after.channel
                )

                if joined or left or switched:
                    logger.info(
                        "Voice state: %s (%d) %s (guild %d)",
                        member.display_name,
                        member.id,
                        "joined " + after.channel.name if joined
                        else "left " + before.channel.name if left
                        else f"moved {before.channel.name} -> {after.channel.name}",
                        guild_id,
                    )

            # Register slash commands
            if self._slash_commands:
                self._register_slash_commands()

            # Start the bot in background
            self._bot_task = asyncio.create_task(self._client.start(self.config.token))

            # Wait for ready
            await asyncio.wait_for(self._ready_event.wait(), timeout=30)

            self._running = True
            return True

        except asyncio.TimeoutError:
            logger.error("[%s] Timeout waiting for connection to Discord", self.name, exc_info=True)
            self._release_platform_lock()
            return False
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error("[%s] Failed to connect to Discord: %s", self.name, e, exc_info=True)
            self._release_platform_lock()
            return False


    async def disconnect(self) -> None:
        """Disconnect from Discord."""
        # Clean up all active voice connections before closing the client
        for guild_id in list(self._voice_clients.keys()):
            try:
                await self.leave_voice_channel(guild_id)
            except Exception as e:  # pragma: no cover - defensive logging
                logger.debug("[%s] Error leaving voice channel %s: %s", self.name, guild_id, e)

        if self._client:
            try:
                await self._client.close()
            except Exception as e:  # pragma: no cover - defensive logging
                logger.warning("[%s] Error during disconnect: %s", self.name, e, exc_info=True)

        if self._post_connect_task and not self._post_connect_task.done():
            self._post_connect_task.cancel()
            try:
                await self._post_connect_task
            except asyncio.CancelledError:
                pass

        self._running = False
        self._client = None
        self._ready_event.clear()
        self._post_connect_task = None

        self._release_platform_lock()

        logger.info("[%s] Disconnected", self.name)
