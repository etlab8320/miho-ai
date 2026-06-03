from __future__ import annotations

from .mixin_deps import *
from .voice_receiver import VoiceReceiver



class DiscordSlashCommandsMixin:

    def format_message(self, content: str) -> str:
        """
        Format message for Discord.

        Discord uses its own markdown variant.
        """
        # Discord markdown is fairly standard, no special escaping needed
        return content


    async def _run_simple_slash(
        self,
        interaction: discord.Interaction,
        command_text: str,
        followup_msg: str | None = None,
    ) -> None:
        """Common handler for simple slash commands that dispatch a command string.

        Defers the interaction (shows "thinking..."), dispatches the command,
        then cleans up the deferred response.  If *followup_msg* is provided
        the "thinking..." indicator is replaced with that text; otherwise it
        is deleted so the channel isn't cluttered.
        """
        # Log the invoker so ghost-command reports can be triaged.  Discord
        # native slash invocations are always user-initiated (no bot can fire
        # them), but mobile autocomplete / keyboard shortcuts / other users
        # in the same channel are easy to miss in post-mortems.
        try:
            _user = interaction.user
            _chan_id = getattr(interaction.channel, "id", None) or getattr(interaction, "channel_id", None)
            logger.info(
                "[Discord] slash '%s' invoked by user=%s id=%s channel=%s guild=%s",
                command_text,
                getattr(_user, "name", "?"),
                getattr(_user, "id", "?"),
                _chan_id,
                getattr(interaction, "guild_id", None),
            )
        except Exception:
            pass  # logging must never block command dispatch

        # Auth gate — must run before defer() so an ephemeral rejection can
        # be delivered on the still-unresponded interaction.
        if not await self._check_slash_authorization(interaction, command_text):
            return

        await interaction.response.defer(ephemeral=True)
        event = self._build_slash_event(interaction, command_text)
        await self.handle_message(event)
        try:
            if followup_msg:
                await interaction.edit_original_response(content=followup_msg)
            else:
                await interaction.delete_original_response()
        except Exception as e:
            logger.debug("Discord interaction cleanup failed: %s", e)


    def _register_slash_commands(self) -> None:
        """Register Discord slash commands on the command tree."""
        if not self._client:
            return

        tree = self._client.tree
        brand = _discord_brand()

        @tree.command(name="new", description="Start a new conversation")
        async def slash_new(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/reset", "New conversation started~")

        @tree.command(name="reset", description=f"Reset your {brand.short_name} session")
        async def slash_reset(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/reset", "Session reset~")

        @tree.command(name="model", description="Show or change the model")
        @discord.app_commands.describe(name="Model name (e.g. anthropic/claude-sonnet-4). Leave empty to see current.")
        async def slash_model(interaction: discord.Interaction, name: str = ""):
            await self._run_simple_slash(interaction, f"/model {name}".strip())

        @tree.command(name="reasoning", description="Show or change reasoning effort")
        @discord.app_commands.describe(effort="Reasoning effort: none, minimal, low, medium, high, or xhigh.")
        async def slash_reasoning(interaction: discord.Interaction, effort: str = ""):
            await self._run_simple_slash(interaction, f"/reasoning {effort}".strip())

        @tree.command(name="personality", description="Set a personality")
        @discord.app_commands.describe(name="Personality name. Leave empty to list available.")
        async def slash_personality(interaction: discord.Interaction, name: str = ""):
            await self._run_simple_slash(interaction, f"/personality {name}".strip())

        @tree.command(name="retry", description="Retry your last message")
        async def slash_retry(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/retry", "Retrying~")

        @tree.command(name="undo", description="Remove the last exchange")
        async def slash_undo(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/undo")

        @tree.command(name="status", description=f"Show {brand.short_name} session status")
        async def slash_status(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/status", "Status sent~")

        @tree.command(name="memory", description="Search or inspect this Discord workspace memory")
        @discord.app_commands.describe(
            action="status, search, or rebuild",
            query="Search query when action is search",
        )
        @discord.app_commands.choices(action=[
            discord.app_commands.Choice(name="status — show workspace memory state", value="status"),
            discord.app_commands.Choice(name="search — search relevant memories", value="search"),
            discord.app_commands.Choice(name="rebuild — rebuild vector index", value="rebuild"),
        ])
        async def slash_memory(
            interaction: discord.Interaction,
            action: str = "status",
            query: str = "",
        ):
            await self._run_simple_slash(interaction, f"/memory {action} {query}".strip())

        @tree.command(name="sethome", description="Set this chat as the home channel")
        async def slash_sethome(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/sethome")

        @tree.command(name="stop", description=f"Stop the running {brand.short_name} agent")
        async def slash_stop(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/stop", "Stop requested~")

        @tree.command(name="steer", description="Inject a message after the next tool call (no interrupt)")
        @discord.app_commands.describe(prompt="Text to inject into the agent's next tool result")
        async def slash_steer(interaction: discord.Interaction, prompt: str):
            await self._run_simple_slash(interaction, f"/steer {prompt}".strip())

        @tree.command(name="compress", description="Compress conversation context")
        async def slash_compress(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/compress")

        @tree.command(name="title", description="Set or show the session title")
        @discord.app_commands.describe(name="Session title. Leave empty to show current.")
        async def slash_title(interaction: discord.Interaction, name: str = ""):
            await self._run_simple_slash(interaction, f"/title {name}".strip())

        @tree.command(name="resume", description="Resume a previously-named session")
        @discord.app_commands.describe(name="Session name to resume. Leave empty to list sessions.")
        async def slash_resume(interaction: discord.Interaction, name: str = ""):
            await self._run_simple_slash(interaction, f"/resume {name}".strip())

        @tree.command(name="usage", description="Show token usage for this session")
        async def slash_usage(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/usage")

        @tree.command(name="help", description="Show available commands")
        async def slash_help(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/help")

        @tree.command(name="insights", description="Show usage insights and analytics")
        @discord.app_commands.describe(days="Number of days to analyze (default: 7)")
        async def slash_insights(interaction: discord.Interaction, days: int = 7):
            await self._run_simple_slash(interaction, f"/insights {days}")

        @tree.command(name="reload-mcp", description="Reload MCP servers from config")
        async def slash_reload_mcp(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/reload-mcp")

        @tree.command(name="reload-skills", description="Re-scan ~/.miho/skills/ for new or removed skills")
        async def slash_reload_skills(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/reload-skills")

        @tree.command(name="voice", description="Toggle voice reply mode")
        @discord.app_commands.describe(mode="Voice mode: join, channel, leave, on, tts, off, or status")
        @discord.app_commands.choices(mode=[
            # `join` and `channel` both route to _handle_voice_channel_join in
            # gateway/run.py — expose both in the slash UI so autocomplete
            # matches what the docs advertise and what the runner accepts when
            # the command is typed as plain text.
            discord.app_commands.Choice(name="join — join your voice channel", value="join"),
            discord.app_commands.Choice(name="channel — join your voice channel (alias)", value="channel"),
            discord.app_commands.Choice(name="leave — leave voice channel", value="leave"),
            discord.app_commands.Choice(name="on — voice reply to voice messages", value="on"),
            discord.app_commands.Choice(name="tts — voice reply to all messages", value="tts"),
            discord.app_commands.Choice(name="off — text only", value="off"),
            discord.app_commands.Choice(name="status — show current mode", value="status"),
        ])
        async def slash_voice(interaction: discord.Interaction, mode: str = ""):
            await self._run_simple_slash(interaction, f"/voice {mode}".strip())

        @tree.command(name="update", description=f"Update {brand.product_name} to the latest version")
        async def slash_update(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/update", "Update initiated~")

        @tree.command(name="restart", description=f"Gracefully restart the {brand.short_name} gateway")
        async def slash_restart(interaction: discord.Interaction):
            await self._run_simple_slash(interaction, "/restart", "Restart requested~")

        @tree.command(name="approve", description="Approve a pending dangerous command")
        @discord.app_commands.describe(scope="Optional: 'all', 'session', 'always', 'all session', 'all always'")
        async def slash_approve(interaction: discord.Interaction, scope: str = ""):
            await self._run_simple_slash(interaction, f"/approve {scope}".strip())

        @tree.command(name="deny", description="Deny a pending dangerous command")
        @discord.app_commands.describe(scope="Optional: 'all' to deny all pending commands")
        async def slash_deny(interaction: discord.Interaction, scope: str = ""):
            await self._run_simple_slash(interaction, f"/deny {scope}".strip())

        @tree.command(name="thread", description=f"Create a new thread and start a {brand.short_name} session in it")
        @discord.app_commands.describe(
            name="Thread name",
            message=f"Optional first message to send to {brand.short_name} in the thread",
            auto_archive_duration="Auto-archive in minutes (60, 1440, 4320, 10080)",
        )
        async def slash_thread(
            interaction: discord.Interaction,
            name: str,
            message: str = "",
            auto_archive_duration: int = 1440,
        ):
            # defer() is performed inside the handler *after* the auth gate
            # so a rejected invoker can receive an ephemeral rejection.
            await self._handle_thread_create_slash(interaction, name, message, auto_archive_duration)

        @tree.command(name="queue", description="Queue a prompt for the next turn (doesn't interrupt)")
        @discord.app_commands.describe(prompt="The prompt to queue")
        async def slash_queue(interaction: discord.Interaction, prompt: str):
            await self._run_simple_slash(interaction, f"/queue {prompt}", "Queued for the next turn.")

        @tree.command(name="background", description="Run a prompt in the background")
        @discord.app_commands.describe(prompt="The prompt to run in the background")
        async def slash_background(interaction: discord.Interaction, prompt: str):
            await self._run_simple_slash(interaction, f"/background {prompt}", "Background task started~")

        # ── Auto-register any gateway-available commands not yet on the tree ──
        # This ensures new commands added to COMMAND_REGISTRY in
        # miho_cli/commands.py automatically appear as Discord slash
        # commands without needing a manual entry here.
        def _build_auto_slash_command(_name: str, _description: str, _args_hint: str = ""):
            """Build a discord.app_commands.Command that proxies to _run_simple_slash."""
            discord_name = _name.lower()[:32]
            desc = (_description or f"Run /{_name}")[:100]
            has_args = bool(_args_hint)

            if has_args:
                def _make_args_handler(__name: str, __hint: str):
                    @discord.app_commands.describe(args=f"Arguments: {__hint}"[:100])
                    async def _handler(interaction: discord.Interaction, args: str = ""):
                        await self._run_simple_slash(
                            interaction, f"/{__name} {args}".strip()
                        )
                    _handler.__name__ = f"auto_slash_{__name.replace('-', '_')}"
                    return _handler

                handler = _make_args_handler(_name, _args_hint)
            else:
                def _make_simple_handler(__name: str):
                    async def _handler(interaction: discord.Interaction):
                        await self._run_simple_slash(interaction, f"/{__name}")
                    _handler.__name__ = f"auto_slash_{__name.replace('-', '_')}"
                    return _handler

                handler = _make_simple_handler(_name)

            return discord.app_commands.Command(
                name=discord_name,
                description=desc,
                callback=handler,
            )

        already_registered: set[str] = set()
        try:
            from miho_cli.commands import COMMAND_REGISTRY, _is_gateway_available, _resolve_config_gates

            try:
                already_registered = {cmd.name for cmd in tree.get_commands()}
            except Exception:
                pass

            config_overrides = _resolve_config_gates()

            for cmd_def in COMMAND_REGISTRY:
                if not _is_gateway_available(cmd_def, config_overrides):
                    continue
                # Discord command names: lowercase, hyphens OK, max 32 chars.
                discord_name = cmd_def.name.lower()[:32]
                if discord_name in already_registered:
                    continue
                auto_cmd = _build_auto_slash_command(
                    cmd_def.name,
                    cmd_def.description,
                    cmd_def.args_hint,
                )
                try:
                    tree.add_command(auto_cmd)
                    already_registered.add(discord_name)
                except Exception:
                    # Silently skip commands that fail registration (e.g.
                    # name conflict with a subcommand group).
                    pass

            logger.debug(
                "Discord auto-registered %d commands from COMMAND_REGISTRY",
                len(already_registered),
            )
        except Exception as e:
            logger.warning("Discord auto-register from COMMAND_REGISTRY failed: %s", e)

        # ── Plugin-registered slash commands ──
        # Plugins register via PluginContext.register_command(); we mirror
        # those into Discord's native slash picker so users get the same
        # autocomplete UX as for built-in commands. No per-platform plugin
        # API needed — plugin commands are platform-agnostic.
        try:
            from miho_cli.commands import _iter_plugin_command_entries

            for plugin_name, plugin_desc, plugin_args_hint in _iter_plugin_command_entries():
                discord_name = plugin_name.lower()[:32]
                if discord_name in already_registered:
                    continue
                auto_cmd = _build_auto_slash_command(
                    plugin_name,
                    plugin_desc,
                    plugin_args_hint,
                )
                try:
                    tree.add_command(auto_cmd)
                    already_registered.add(discord_name)
                except Exception:
                    # Silently skip commands that fail registration (e.g.
                    # name conflict with a subcommand group).
                    pass
        except Exception as e:
            logger.warning(
                "Discord auto-register from plugin commands failed: %s", e
            )

        # Register skills under a single /skill command group with category
        # subcommand groups.  This uses 1 top-level slot instead of N,
        # supporting up to 25 categories × 25 skills = 625 skills.
        self._register_skill_group(tree)

        # Optional defense-in-depth: hide every slash command from non-admin
        # guild members in Discord's slash picker. Server-side authorization
        # (``_check_slash_authorization``) is the actual gate; this is purely
        # UX so users don't see commands they can't invoke. Off by default
        # to preserve the slash UX for deployments that intentionally allow
        # everyone in the guild.
        if os.getenv("DISCORD_HIDE_SLASH_COMMANDS", "false").strip().lower() in {
            "true", "1", "yes", "on",
        }:
            self._apply_owner_only_visibility(tree)


    def _apply_owner_only_visibility(self, tree) -> None:
        """Set default_member_permissions=0 on every registered slash command.

        Discord interprets ``Permissions(0)`` as "requires no permissions",
        which paradoxically means the command is hidden from every guild
        member except those with the Administrator permission. Server admins
        can re-grant per user/role via Server Settings → Integrations →
        <bot> → Permissions.

        Authoritative gate is ``_check_slash_authorization`` on every
        invocation, which catches stale clients, role grants made by
        mistake, and direct API calls bypassing Discord's UI hide.
        """
        try:
            no_perms = discord.Permissions(0)
        except Exception as e:
            logger.warning(
                "[Discord] _apply_owner_only_visibility: cannot build Permissions(0): %s",
                e,
            )
            return
        applied = 0
        for cmd in tree.get_commands():
            try:
                cmd.default_permissions = no_perms
                applied += 1
            except Exception as e:
                logger.debug(
                    "[Discord] Could not set default_permissions on %r: %s",
                    getattr(cmd, "name", "?"), e,
                )
        logger.info(
            "[Discord] Hid %d slash command(s) from non-admin guild members "
            "(opt-in defense in depth via DISCORD_HIDE_SLASH_COMMANDS).",
            applied,
        )
