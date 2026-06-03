from __future__ import annotations

from .mixin_deps import *
from .voice_receiver import VoiceReceiver



class DiscordSkillSlashMixin:

    def _register_skill_group(self, tree) -> None:
        """Register a single ``/skill`` command with autocomplete on the name.

        Discord enforces an ~8000-byte per-command payload limit. The older
        nested layout (``/skill <category> <name>``) registered one giant
        command whose serialized payload grew linearly with the skill
        catalog — with the default ~75 skills the payload was ~14 KB and
        ``tree.sync()`` rejected the entire slash-command batch (issues
        #11321, #10259, #11385, #10261, #10214).

        Autocomplete options are fetched dynamically by Discord when the
        user types — they do NOT count against the per-command registration
        budget. So we register ONE flat ``/skill`` command with
        ``name: str`` (autocompleted) and ``args: str = ""``. This scales
        to thousands of skills with no size math, no splitting, and no
        hidden skills. The slash picker also becomes more discoverable —
        Discord live-filters by the user's typed prefix against both the
        skill name and its description.

        The entries list and lookup dict are stored on ``self`` rather
        than captured in closure variables so :meth:`refresh_skill_group`
        can repopulate them when the user runs ``/reload-skills`` without
        needing to touch the Discord slash-command tree or trigger a
        ``tree.sync()`` call.
        """
        try:
            existing_names = set()
            try:
                existing_names = {cmd.name for cmd in tree.get_commands()}
            except Exception:
                pass

            # Populate the instance-level entries/lookup so the
            # autocomplete + handler callbacks below always read the
            # freshest state. refresh_skill_group() re-runs the same
            # collector and mutates these two attributes in place.
            self._skill_entries: list[tuple[str, str, str]] = []
            self._skill_lookup: dict[str, tuple[str, str]] = {}
            self._skill_group_reserved_names: set[str] = set(existing_names)
            self._refresh_skill_catalog_state()

            if not self._skill_entries:
                return

            async def _autocomplete_name(
                interaction: "discord.Interaction", current: str,
            ) -> list:
                """Filter skills by the user's typed prefix.

                Matches both the skill name and its description so
                "/skill pdf" surfaces skills whose description mentions
                PDFs even if the name doesn't. Discord caps this list at
                25 entries per query.

                Authorization: a quiet pre-check evaluates the slash
                allowlists and returns ``[]`` for unauthorized users so
                the installed skill catalog is not leaked to anyone who
                can see the command in the picker. Returning a generic
                empty list here is intentional — sending a per-keystroke
                ephemeral rejection would produce a barrage of error
                popups during typing.

                Reads ``self._skill_entries`` so a ``/reload-skills`` run
                since process start shows up on the very next keystroke.
                """
                try:
                    allowed, _reason = self._evaluate_slash_authorization(interaction)
                except Exception:
                    # Defensive: never raise from autocomplete. Fail
                    # closed by returning an empty suggestion list.
                    return []
                if not allowed:
                    return []
                q = (current or "").strip().lower()
                choices: list = []
                for name, desc, _key in self._skill_entries:
                    if not q or q in name.lower() or (desc and q in desc.lower()):
                        if desc:
                            label = f"{name} — {desc}"
                        else:
                            label = name
                        # Discord's Choice.name is capped at 100 chars.
                        if len(label) > 100:
                            label = label[:97] + "..."
                        choices.append(
                            discord.app_commands.Choice(name=label, value=name)
                        )
                        if len(choices) >= 25:
                            break
                return choices

            @discord.app_commands.describe(
                name="Which skill to run",
                args="Optional arguments for the skill",
            )
            @discord.app_commands.autocomplete(name=_autocomplete_name)
            async def _skill_handler(
                interaction: "discord.Interaction", name: str, args: str = "",
            ):
                # Authorize BEFORE any skill lookup so that known and
                # unknown skill names produce identical rejections for
                # unauthorized users (no probing the installed catalog
                # via "Unknown skill: <name>" responses).
                if not await self._check_slash_authorization(interaction, "/skill"):
                    return
                entry = self._skill_lookup.get(name)
                if not entry:
                    await interaction.response.send_message(
                        f"Unknown skill: `{name}`. Start typing for "
                        f"autocomplete suggestions.",
                        ephemeral=True,
                    )
                    return
                _desc, cmd_key = entry
                await self._run_simple_slash(
                    interaction, f"{cmd_key} {args}".strip()
                )

            cmd = discord.app_commands.Command(
                name="skill",
                description="Run a Miho skill",
                callback=_skill_handler,
            )
            tree.add_command(cmd)

            logger.info(
                "[%s] Registered /skill command with %d skill(s) via autocomplete",
                self.name, len(self._skill_entries),
            )
            if self._skill_group_hidden_count:
                logger.info(
                    "[%s] %d skill(s) filtered out of /skill (name clamp / reserved)",
                    self.name, self._skill_group_hidden_count,
                )
        except Exception as exc:
            logger.warning("[%s] Failed to register /skill command: %s", self.name, exc)


    def _refresh_skill_catalog_state(self) -> None:
        """Re-scan disk for skills and repopulate ``self._skill_entries``.

        Called once from :meth:`_register_skill_group` at startup and
        again from :meth:`refresh_skill_group` whenever the user runs
        ``/reload-skills``. No Discord API calls are made — autocomplete
        and the handler both read from these instance attributes
        directly, so an in-place mutation is sufficient.
        """
        from miho_cli.commands import discord_skill_commands_by_category

        reserved = getattr(self, "_skill_group_reserved_names", set())
        categories, uncategorized, hidden = discord_skill_commands_by_category(
            reserved_names=set(reserved),
        )
        entries: list[tuple[str, str, str]] = list(uncategorized)
        for cat_skills in categories.values():
            entries.extend(cat_skills)
        # Stable alphabetical order so the autocomplete suggestion
        # list is predictable across restarts.
        entries.sort(key=lambda t: t[0])

        self._skill_entries = entries
        self._skill_lookup = {n: (d, k) for n, d, k in entries}
        self._skill_group_hidden_count = hidden


    def refresh_skill_group(self) -> tuple[int, int]:
        """Rescan skills and update the live ``/skill`` autocomplete state.

        Invoked by :meth:`gateway.run.GatewayOrchestrator._handle_reload_skills_command`
        after :func:`agent.skill_commands.reload_skills` has refreshed
        the in-process skill-command registry. Without this call, the
        ``/skill`` autocomplete dropdown keeps showing the list captured
        at process start — new skills stay invisible and deleted skills
        return an "Unknown skill" error when clicked.

        Because autocomplete options are fetched dynamically by Discord,
        we only need to mutate the entries/lookup attributes read by the
        callbacks — no ``tree.sync()`` is required.

        Returns ``(new_count, hidden_count)``.
        """
        try:
            self._refresh_skill_catalog_state()
        except Exception as exc:
            logger.warning(
                "[%s] Failed to refresh /skill autocomplete after reload: %s",
                self.name, exc,
            )
            return (len(getattr(self, "_skill_entries", [])), 0)
        logger.info(
            "[%s] Refreshed /skill autocomplete: %d skill(s) available (%d filtered)",
            self.name,
            len(self._skill_entries),
            self._skill_group_hidden_count,
        )
        return (len(self._skill_entries), self._skill_group_hidden_count)


    def _build_slash_event(self, interaction: discord.Interaction, text: str) -> MessageEvent:
        """Build a MessageEvent from a Discord slash command interaction."""
        is_dm = isinstance(interaction.channel, discord.DMChannel)
        is_thread = isinstance(interaction.channel, discord.Thread)
        thread_id = None

        if is_dm:
            chat_type = "dm"
        elif is_thread:
            chat_type = "thread"
            thread_id = str(interaction.channel_id)
        else:
            chat_type = "group"

        chat_name = ""
        if not is_dm and hasattr(interaction.channel, "name"):
            chat_name = interaction.channel.name
            if hasattr(interaction.channel, "guild") and interaction.channel.guild:
                chat_name = f"{interaction.channel.guild.name} / #{chat_name}"

        # Get channel topic (if available).
        # For forum threads, inherit the parent forum's topic.
        chat_topic = self._get_effective_topic(interaction.channel, is_thread=is_thread)

        source = self.build_source(
            chat_id=str(interaction.channel_id),
            chat_name=chat_name,
            chat_type=chat_type,
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
            thread_id=thread_id,
            chat_topic=chat_topic,
        )

        msg_type = MessageType.COMMAND if text.startswith("/") else MessageType.TEXT
        channel_id = str(interaction.channel_id)
        parent_id = str(getattr(getattr(interaction, "channel", None), "parent_id", "") or "")
        return MessageEvent(
            text=text,
            message_type=msg_type,
            source=source,
            raw_message=interaction,
            channel_prompt=self._resolve_channel_prompt(channel_id, parent_id or None),
        )
