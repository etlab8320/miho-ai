from __future__ import annotations

from .mixin_deps import *
from .voice_receiver import VoiceReceiver



class DiscordAuthMixin:

    def _is_allowed_user(
        self,
        user_id: str,
        author=None,
        *,
        guild=None,
        is_dm: bool = False,
    ) -> bool:
        """Check if user is allowed via DISCORD_ALLOWED_USERS or DISCORD_ALLOWED_ROLES.

        Uses OR semantics: if the user matches EITHER allowlist, they're allowed.
        If both allowlists are empty, everyone is allowed (backwards compatible).

        Role checks are **scoped to the guild the message originated from**.
        For DMs (no guild context), role-based auth is disabled by default and
        only user-ID allowlist applies. Set ``discord.dm_role_auth_guild``
        in config.yaml to a specific guild ID to opt-in: role membership in
        that one guild will authorize DMs. This prevents cross-guild
        privilege escalation where a user with the configured role in any
        shared public server could DM the bot and pass the allowlist.

        Args:
            user_id: Author ID as a string.
            author: Optional Member/User object for in-guild role lookup.
            guild: The guild the message arrived in (None for DMs).
            is_dm: True if the message came from a DM channel.
        """
        # ``getattr`` fallbacks here guard against test fixtures that build
        # an adapter via ``object.__new__(DiscordAdapter)`` and skip __init__
        # (see AGENTS.md pitfall #17 — same pattern as gateway.run).
        allowed_users = getattr(self, "_allowed_user_ids", set())
        allowed_roles = getattr(self, "_allowed_role_ids", set())
        has_users = bool(allowed_users)
        has_roles = bool(allowed_roles)
        if not has_users and not has_roles:
            return True
        # Check user ID allowlist (works for both DMs and guild messages)
        if has_users and user_id in allowed_users:
            return True
        # Role allowlist is only consulted when configured.
        if not has_roles:
            return False

        # DM path: roles require explicit opt-in via
        # ``discord.dm_role_auth_guild`` in config.yaml. Without this, a
        # user with the configured role in ANY mutual guild could DM the
        # bot and bypass the allowlist (cross-guild leakage).
        if is_dm or guild is None:
            dm_guild_id = _read_dm_role_auth_guild()
            if dm_guild_id is None:
                return False
            if self._client is None:
                return False
            dm_guild = self._client.get_guild(dm_guild_id)
            if dm_guild is None:
                return False
            try:
                uid_int = int(user_id)
            except (TypeError, ValueError):
                return False
            m = dm_guild.get_member(uid_int)
            if m is None:
                return False
            m_roles = getattr(m, "roles", None) or []
            return any(getattr(r, "id", None) in allowed_roles for r in m_roles)

        # Guild path: role check is scoped to THIS guild only.
        # 1) Prefer the direct Member object passed in (correct guild by construction).
        direct_roles = getattr(author, "roles", None) if author is not None else None
        author_guild = getattr(author, "guild", None)
        if direct_roles and (author_guild is None or author_guild.id == guild.id):
            if any(getattr(r, "id", None) in allowed_roles for r in direct_roles):
                return True
        # 2) Fallback: resolve the Member in the message's guild only — NEVER
        #    scan other mutual guilds (that is the cross-guild bypass bug).
        try:
            uid_int = int(user_id)
        except (TypeError, ValueError):
            return False
        m = guild.get_member(uid_int)
        if m is None:
            return False
        m_roles = getattr(m, "roles", None) or []
        return any(getattr(r, "id", None) in allowed_roles for r in m_roles)


    def _evaluate_slash_authorization(
        self, interaction: "discord.Interaction",
    ) -> Tuple[bool, Optional[str]]:
        """Evaluate slash authorization without producing any response.

        Returns ``(allowed, reason)``. ``reason`` is populated only when
        ``allowed`` is False. This is the shared core used by both the
        responding wrapper (``_check_slash_authorization``) and side-effect-
        free callers like the ``/skill`` autocomplete callback, which must
        return an empty list for unauthorized users instead of leaking an
        ephemeral rejection per-keystroke.

        Fail-closed semantics for malformed payloads: when an allowlist is
        configured but the interaction is missing the data needed to
        evaluate it (no channel id with channel policy active, no user
        with user/role policy active), the gate REJECTS rather than
        falling through. Without these guards a guild interaction that
        happens to deserialize without a channel id would silently bypass
        ``DISCORD_ALLOWED_CHANNELS`` and a payload missing ``user`` would
        raise ``AttributeError`` in the user check below, surfacing as
        an opaque interaction failure rather than a clean rejection.
        """
        chan_obj = getattr(interaction, "channel", None)
        in_dm = isinstance(chan_obj, discord.DMChannel) if chan_obj is not None else False

        # ── Channel scope (mirrors on_message lines 3374-3388) ──
        # DMs aren't channel-gated — DMs follow on_message's DM lockdown
        # path which has its own user-allowlist enforcement.
        if not in_dm:
            chan_id_raw = getattr(interaction, "channel_id", None) or getattr(
                chan_obj, "id", None,
            )
            channel_ids: set = set()
            if chan_id_raw is not None:
                channel_ids.add(str(chan_id_raw))
                # Mirror on_message: also test the parent channel for threads
                # so per-channel allow/deny lists work consistently.
                if isinstance(chan_obj, discord.Thread):
                    parent_id = self._get_parent_channel_id(chan_obj)
                    if parent_id:
                        channel_ids.add(str(parent_id))

            allowed_raw = os.getenv("DISCORD_ALLOWED_CHANNELS", "")
            if allowed_raw:
                allowed = {c.strip() for c in allowed_raw.split(",") if c.strip()}
                if "*" not in allowed:
                    if not channel_ids:
                        # Channel policy is configured but the interaction
                        # has no resolvable channel id. Fail closed.
                        return (
                            False,
                            "channel id missing with DISCORD_ALLOWED_CHANNELS configured",
                        )
                    if not (channel_ids & allowed):
                        return (False, "channel not in DISCORD_ALLOWED_CHANNELS")

            # Ignored beats allowed: even when a thread's parent channel
            # is on the allowlist, an explicit DISCORD_IGNORED_CHANNELS
            # entry on the thread or its parent rejects the interaction.
            ignored_raw = os.getenv("DISCORD_IGNORED_CHANNELS", "")
            if ignored_raw and channel_ids:
                ignored = {c.strip() for c in ignored_raw.split(",") if c.strip()}
                if "*" in ignored or (channel_ids & ignored):
                    return (False, "channel in DISCORD_IGNORED_CHANNELS")

        # ── User / role allowlist (mirrors on_message line 681) ──
        user = getattr(interaction, "user", None)
        allowed_users = getattr(self, "_allowed_user_ids", set()) or set()
        allowed_roles = getattr(self, "_allowed_role_ids", set()) or set()
        if user is None or getattr(user, "id", None) is None:
            # No identifiable user. With any user/role allowlist
            # configured, fail closed rather than raise AttributeError
            # on ``interaction.user.id`` below. With no allowlist this
            # is the existing "no allowlist = everyone" backwards-compat.
            if allowed_users or allowed_roles:
                return (False, "missing interaction.user with allowlist configured")
            return (True, None)

        user_id = str(user.id)
        # Pass guild + is_dm so role check is scoped to the originating
        # guild and cross-guild DM bypass (#12136) can't land via the
        # slash surface either.
        interaction_guild = getattr(interaction, "guild", None)
        if not self._is_allowed_user(
            user_id,
            author=user,
            guild=interaction_guild,
            is_dm=in_dm,
        ):
            return (
                False,
                "user not in DISCORD_ALLOWED_USERS / DISCORD_ALLOWED_ROLES",
            )

        return (True, None)


    async def _check_slash_authorization(
        self, interaction: "discord.Interaction", command_text: str,
    ) -> bool:
        """Mirror on_message's user/role/channel gates onto a slash invocation.

        Returns True to proceed. Returns False *after* sending an ephemeral
        rejection, logging a warning, and scheduling a cross-platform admin
        alert — the caller must stop on False (the interaction has already
        been responded to).
        """
        allowed, reason = self._evaluate_slash_authorization(interaction)
        if allowed:
            return True
        return await self._reject_slash(
            interaction, command_text, reason=reason or "unauthorized",
        )


    async def _reject_slash(
        self, interaction: "discord.Interaction", command_text: str, *, reason: str,
    ) -> bool:
        """Send ephemeral reject + log warning + schedule admin alert. Returns False.

        Tolerates a missing ``interaction.user`` -- the fail-closed branch
        in ``_evaluate_slash_authorization`` deliberately routes here for
        malformed payloads (no user) when an allowlist is configured, and
        ``str(interaction.user.id)`` would raise AttributeError before the
        ephemeral rejection could be sent.
        """
        user = getattr(interaction, "user", None)
        if user is not None:
            user_id = str(getattr(user, "id", "?"))
            user_name = getattr(user, "name", "?")
        else:
            user_id = "?"
            user_name = "?"
        chan_id = getattr(interaction, "channel_id", None) or getattr(
            getattr(interaction, "channel", None), "id", None,
        )
        guild_id = getattr(interaction, "guild_id", None)

        logger.warning(
            "[Discord] Unauthorized slash attempt: user=%s id=%s channel=%s "
            "guild=%s cmd=%r reason=%r",
            user_name, user_id, chan_id, guild_id, command_text, reason,
        )

        try:
            await interaction.response.send_message(
                "You're not authorized to use this command.",
                ephemeral=True,
            )
        except Exception as e:
            # Interaction may already be responded to (e.g. caller deferred
            # before the auth check, or Discord retried). Best-effort only.
            logger.debug("[Discord] Could not send unauthorized ephemeral: %s", e)

        # Fire-and-forget: don't block the interaction handler on Telegram I/O.
        try:
            asyncio.create_task(self._notify_unauthorized_slash(
                user_name, user_id, chan_id, guild_id, command_text, reason,
            ))
        except Exception as e:
            logger.debug("[Discord] Could not schedule admin notify task: %s", e)

        return False


    async def _notify_unauthorized_slash(
        self, user_name: str, user_id: str, chan_id, guild_id,
        command_text: str, reason: str,
    ) -> None:
        """Best-effort cross-platform alert to the gateway operator.

        Tries TELEGRAM first (most operators set TELEGRAM_HOME_CHANNEL),
        then SLACK. Silently no-ops if no other platform is configured
        with a home channel.

        A soft send failure -- adapter.send() returning a result with
        ``success=False`` rather than raising -- continues the fallback
        chain. Treating a SendResult(success=False) as delivered would
        mean a Telegram outage that the adapter politely surfaces (e.g.
        rate-limit, auth failure) silently swallows the alert without
        attempting Slack. Hard exceptions still take the same path via
        the except branch below.
        """
        runner = getattr(self, "gateway_runner", None)
        if not runner:
            return
        for target in (Platform.TELEGRAM, Platform.SLACK):
            try:
                adapter = runner.adapters.get(target)
                if not adapter:
                    continue
                home = runner.config.get_home_channel(target)
                if not home or not getattr(home, "chat_id", None):
                    continue
                msg = (
                    "⚠️ Unauthorized Discord slash attempt\n"
                    f"User: {user_name} ({user_id})\n"
                    f"Channel: {chan_id} (guild {guild_id})\n"
                    f"Command: {command_text}\n"
                    f"Reason: {reason}"
                )
                result = await adapter.send(str(home.chat_id), msg)
                # Only return on confirmed delivery. SendResult(success=False)
                # -> continue to the next platform.
                if getattr(result, "success", None) is False:
                    logger.debug(
                        "[Discord] Admin notify via %s returned success=False"
                        " (error=%r); falling through",
                        target, getattr(result, "error", None),
                    )
                    continue
                return
            except Exception as e:
                logger.debug("[Discord] Admin notify via %s failed: %s", target, e)


    async def _resolve_allowed_usernames(self) -> None:
        """
        Resolve non-numeric entries in DISCORD_ALLOWED_USERS to Discord user IDs.

        Users can specify usernames (e.g. "teknium") or display names instead of
        raw numeric IDs.  After resolution, the env var and internal set are updated
        so authorization checks work with IDs only.
        """
        if not self._allowed_user_ids or not self._client:
            return

        numeric_ids = set()
        to_resolve = set()

        for entry in self._allowed_user_ids:
            if entry.isdigit():
                numeric_ids.add(entry)
            else:
                to_resolve.add(entry.lower())

        if not to_resolve:
            return

        print(f"[{self.name}] Resolving {len(to_resolve)} username(s): {', '.join(to_resolve)}")
        resolved_count = 0

        for guild in self._client.guilds:
            # Fetch full member list (requires members intent)
            try:
                members = guild.members
                if len(members) < guild.member_count:
                    members = [m async for m in guild.fetch_members(limit=None)]
            except Exception as e:
                logger.warning("Failed to fetch members for guild %s: %s", guild.name, e)
                continue

            for member in members:
                name_lower = member.name.lower()
                display_lower = member.display_name.lower()
                global_lower = (member.global_name or "").lower()

                matched = name_lower in to_resolve or display_lower in to_resolve or global_lower in to_resolve
                if matched:
                    uid = str(member.id)
                    numeric_ids.add(uid)
                    resolved_count += 1
                    matched_name = name_lower if name_lower in to_resolve else (
                        display_lower if display_lower in to_resolve else global_lower
                    )
                    to_resolve.discard(matched_name)
                    print(f"[{self.name}] Resolved '{matched_name}' -> {uid} ({member.name}#{member.discriminator})")

            if not to_resolve:
                break

        if to_resolve:
            print(f"[{self.name}] Could not resolve usernames: {', '.join(to_resolve)}")

        # Update internal set and env var so gateway auth checks use IDs
        self._allowed_user_ids = numeric_ids
        os.environ["DISCORD_ALLOWED_USERS"] = ",".join(sorted(numeric_ids))
        if resolved_count:
            print(f"[{self.name}] Updated DISCORD_ALLOWED_USERS with {resolved_count} resolved ID(s)")
