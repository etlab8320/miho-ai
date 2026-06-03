from __future__ import annotations

from .mixin_deps import *
from .voice_receiver import VoiceReceiver



class DiscordChannelConfigMixin:

    def _resolve_channel_skills(self, channel_id: str, parent_id: str | None = None) -> list[str] | None:
        """Look up auto-skill bindings for a Discord channel/forum thread.

        Config format (in platform extra):
            channel_skill_bindings:
              - id: "123456"
                skills: ["skill-a", "skill-b"]
        Also checks parent_id so forum threads inherit the forum's bindings.
        """
        from gateway.platforms.base import resolve_channel_skills
        return resolve_channel_skills(self.config.extra, channel_id, parent_id)


    def _resolve_channel_prompt(self, channel_id: str, parent_id: str | None = None) -> str | None:
        """Resolve a Discord per-channel prompt, preferring the exact channel over its parent."""
        from gateway.platforms.base import resolve_channel_prompt
        return resolve_channel_prompt(self.config.extra, channel_id, parent_id)


    def _discord_require_mention(self) -> bool:
        """Return whether Discord channel messages require a bot mention."""
        configured = self.config.extra.get("require_mention")
        if configured is not None:
            if isinstance(configured, str):
                return configured.lower() not in {"false", "0", "no", "off"}
            return bool(configured)
        return os.getenv("DISCORD_REQUIRE_MENTION", "true").lower() not in {"false", "0", "no", "off"}


    def _discord_allow_any_attachment(self) -> bool:
        """Return whether Discord attachments bypass the SUPPORTED_DOCUMENT_TYPES allowlist.

        When True, any uploaded file is cached to disk and surfaced to the
        agent as a local path so it can be inspected via terminal / read_file
        / ffprobe / etc. Default False preserves the historical behaviour of
        dropping unsupported types with a warning log.
        """
        configured = self.config.extra.get("allow_any_attachment")
        if configured is not None:
            if isinstance(configured, str):
                return configured.lower() not in {"false", "0", "no", "off", ""}
            return bool(configured)
        return os.getenv("DISCORD_ALLOW_ANY_ATTACHMENT", "false").lower() in {"true", "1", "yes", "on"}


    def _discord_max_attachment_bytes(self) -> int:
        """Return the per-attachment byte cap. 0 means unlimited.

        The whole attachment is held in memory while being written to the
        cache, so unlimited carries a real memory cost. Default 32 MiB
        matches the historical hardcoded value.
        """
        configured = self.config.extra.get("max_attachment_bytes")
        if configured is None:
            configured = os.getenv("DISCORD_MAX_ATTACHMENT_BYTES")
        if configured is None or configured == "":
            return 32 * 1024 * 1024
        try:
            value = int(configured)
        except (TypeError, ValueError):
            logger.warning(
                "[Discord] Invalid max_attachment_bytes value %r, falling back to 32 MiB",
                configured,
            )
            return 32 * 1024 * 1024
        return max(0, value)


    @staticmethod
    def _is_discord_voice_message_attachment(att: Any) -> bool:
        """Return True when a Discord audio attachment is a native voice note."""
        marker = getattr(att, "is_voice_message", None)
        if marker is not None:
            if callable(marker):
                try:
                    return bool(marker())
                except Exception as exc:
                    logger.debug("[Discord] is_voice_message() failed for attachment: %s", exc)
                    return False
            return bool(marker)

        return (
            getattr(att, "duration", None) is not None
            and getattr(att, "waveform", None) is not None
        )


    def _discord_free_response_channels(self) -> set:
        """Return Discord channel IDs where no bot mention is required.

        A single ``"*"`` entry (either from a list or a comma-separated
        string) is preserved in the returned set so callers can short-circuit
        on wildcard membership, consistent with ``allowed_channels``.
        """
        raw = self.config.extra.get("free_response_channels")
        if raw is None:
            raw = os.getenv("DISCORD_FREE_RESPONSE_CHANNELS", "")
        if isinstance(raw, list):
            return {str(part).strip() for part in raw if str(part).strip()}
        # Coerce non-list scalars (str/int/float) to str before splitting.
        # YAML parses a bare numeric value such as
        # `free_response_channels: 1491973769726791812` as int, which was
        # previously falling through the isinstance(str) branch and silently
        # returning an empty set.  str() here accepts whatever scalar the YAML
        # loader hands us without changing existing string/CSV semantics.
        s = str(raw).strip() if raw is not None else ""
        if s:
            return {part.strip() for part in s.split(",") if part.strip()}
        return set()


    def _discord_thread_require_mention(self) -> bool:
        """Return whether thread participation requires @mention to follow up.

        When ``False`` (default), once the bot has participated in a thread it
        keeps responding to every message in that thread without needing to be
        mentioned again — useful for one-on-one conversations.

        When ``True``, the @mention requirement is enforced inside threads as
        well.  Set this when multiple bots share a thread and you want each
        one to only fire on explicit @mention, avoiding bot-to-bot loops or
        unwanted cross-replies.
        """
        configured = self.config.extra.get("thread_require_mention")
        if configured is not None:
            if isinstance(configured, str):
                return configured.lower() not in {"false", "0", "no", "off"}
            return bool(configured)
        return os.getenv("DISCORD_THREAD_REQUIRE_MENTION", "false").lower() in {"true", "1", "yes", "on"}


    def _discord_history_backfill(self) -> bool:
        """Return whether history backfill is enabled for shared sessions."""
        configured = self.config.extra.get("history_backfill")
        if configured is not None:
            if isinstance(configured, str):
                return configured.lower() not in {"false", "0", "no", "off"}
            return bool(configured)
        return os.getenv("DISCORD_HISTORY_BACKFILL", "true").lower() in {"true", "1", "yes"}


    def _discord_history_backfill_limit(self) -> int:
        """Return the max number of messages to scan backwards for context.

        In practice the scan usually stops much earlier — at the bot's own
        last message in the channel (the natural partition point).  This
        limit is a safety cap for cold starts and long gaps where no prior
        bot message exists in recent history.
        """
        configured = self.config.extra.get("history_backfill_limit")
        if configured is not None:
            try:
                return int(configured)
            except (ValueError, TypeError):
                pass
        raw = os.getenv("DISCORD_HISTORY_BACKFILL_LIMIT", "50")
        try:
            return int(raw)
        except (ValueError, TypeError):
            return 50


    async def _fetch_channel_context(
        self,
        channel: Any,
        before: "DiscordMessage",
    ) -> str:
        """Fetch recent channel messages for conversational context.

        Scans backwards from *before* and collects messages until it hits
        a message sent by this bot (the natural partition point between
        bot turns) or reaches ``history_backfill_limit``.

        Returns a formatted block like::

            [Recent channel messages]
            [Alice] some message
            [Bob [bot]] another message

        Returns an empty string if no context is available.
        """
        limit = self._discord_history_backfill_limit()
        if limit <= 0:
            return ""

        # Determine which bot messages to include in context
        allow_bots_raw = os.getenv("DISCORD_ALLOW_BOTS", "none").lower().strip()
        include_other_bots = allow_bots_raw != "none"

        # Use the in-memory cache to narrow the fetch window on hot paths.
        # If we know our last message ID in this channel, pass it as `after`
        # to avoid scanning the full limit.  Falls back to scanning on cache
        # miss (cold start / restart).
        # Guard: only use the cache when it's chronologically before the
        # trigger — Discord snowflake IDs are monotonically increasing, so
        # a simple int comparison suffices.
        channel_id = str(getattr(channel, "id", ""))
        _cached_id = self._last_self_message_id.get(channel_id)
        _after_obj = None
        try:
            if _cached_id and int(_cached_id) < int(before.id):
                _after_obj = discord.Object(id=int(_cached_id))
        except (ValueError, TypeError):
            pass  # Malformed cache entry — fall back to cold-start scan

        try:
            collected = []
            # IMPORTANT: pass oldest_first=False explicitly.  discord.py 2.x
            # silently flips the default to True when `after=` is supplied,
            # which would select the *earliest* N messages after our last
            # response instead of the *latest* N before the trigger.  In
            # high-traffic windows that returns stale tool traces and drops
            # the actual final answer.  See the regression test
            # `test_fetch_channel_context_cache_uses_latest_window_when_after_set`.
            async for msg in channel.history(
                limit=limit,
                before=before,
                after=_after_obj,
                oldest_first=False,
            ):
                # Stop at our own message — this is the partition point.
                # Everything before this is already in the session transcript.
                # (Redundant when _after_obj is set, but needed for cold start.)
                if msg.author == self._client.user:
                    break

                # Skip system messages (pins, joins, thread renames, etc.)
                if msg.type not in {discord.MessageType.default, discord.MessageType.reply}:
                    continue

                # Respect DISCORD_ALLOW_BOTS for other bots.
                # For history context, "mentions" is treated as "all" — we are
                # deciding what context to show, not whether to respond.
                if getattr(msg.author, "bot", False) and not include_other_bots:
                    continue

                content = getattr(msg, "clean_content", msg.content) or ""
                if not content and msg.attachments:
                    content = "(attachment)"
                if not content:
                    continue

                name = msg.author.display_name
                if getattr(msg.author, "bot", False):
                    name = f"{name} [bot]"
                collected.append(f"[{name}] {content}")

            if not collected:
                return ""

            # channel.history returns newest-first (oldest_first=False); reverse for chronological order
            collected.reverse()
            return "[Recent channel messages]\n" + "\n".join(collected)

        except discord.Forbidden:
            logger.debug("[%s] Missing permissions to fetch channel history", self.name)
            return ""
        except Exception as e:
            logger.warning("[%s] Failed to fetch channel history: %s", self.name, e)
            return ""


    def _thread_parent_channel(self, channel: Any) -> Any:
        """Return the parent text channel when invoked from a thread."""
        return getattr(channel, "parent", None) or channel


    async def _resolve_interaction_channel(self, interaction: discord.Interaction) -> Optional[Any]:
        """Return the interaction channel, fetching it if the payload is partial."""
        channel = getattr(interaction, "channel", None)
        if channel is not None:
            return channel
        if not self._client:
            return None
        channel_id = getattr(interaction, "channel_id", None)
        if channel_id is None:
            return None
        channel = self._client.get_channel(int(channel_id))
        if channel is not None:
            return channel
        try:
            return await self._client.fetch_channel(int(channel_id))
        except Exception:
            return None
