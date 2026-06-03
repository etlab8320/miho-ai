from __future__ import annotations

from .mixin_deps import *
from .views import (
    ClarifyChoiceView,
    ExecApprovalView,
    ModelPickerView,
    SlashConfirmView,
    UpdateAvailableView,
    UpdatePromptView,
)



class DiscordUiPromptMixin:

    async def send_exec_approval(
        self, chat_id: str, command: str, session_key: str,
        description: str = "dangerous command",
        metadata: Optional[dict] = None,
    ) -> SendResult:
        """
        Send a button-based exec approval prompt for a dangerous command.

        The buttons call ``resolve_gateway_approval()`` to unblock the waiting
        agent thread — this replaces the text-based ``/approve`` flow on Discord.
        """
        if not self._client or not DISCORD_AVAILABLE:
            return SendResult(success=False, error="Not connected")

        try:
            # Resolve channel — use thread_id from metadata if present
            target_id = chat_id
            if metadata and metadata.get("thread_id"):
                target_id = metadata["thread_id"]

            channel = self._client.get_channel(int(target_id))
            if not channel:
                channel = await self._client.fetch_channel(int(target_id))

            # Discord embed description limit is 4096; show full command up to that
            max_desc = 4088
            cmd_display = command if len(command) <= max_desc else command[: max_desc - 3] + "..."
            embed = discord.Embed(
                title="⚠️ Command Approval Required",
                description=f"```\n{cmd_display}\n```",
                color=discord.Color.orange(),
            )
            embed.add_field(name="Reason", value=description, inline=False)

            view = ExecApprovalView(
                session_key=session_key,
                allowed_user_ids=self._allowed_user_ids,
                allowed_role_ids=self._allowed_role_ids,
            )

            msg = await channel.send(embed=embed, view=view)
            return SendResult(success=True, message_id=str(msg.id))

        except Exception as e:
            return SendResult(success=False, error=str(e))


    async def send_slash_confirm(
        self, chat_id: str, title: str, message: str, session_key: str,
        confirm_id: str, metadata: Optional[dict] = None,
    ) -> SendResult:
        """Send a three-button slash-command confirmation prompt."""
        if not self._client or not DISCORD_AVAILABLE:
            return SendResult(success=False, error="Not connected")

        try:
            target_id = chat_id
            if metadata and metadata.get("thread_id"):
                target_id = metadata["thread_id"]

            channel = self._client.get_channel(int(target_id))
            if not channel:
                channel = await self._client.fetch_channel(int(target_id))

            # Embed description limit is 4096; message usually fits easily.
            max_desc = 4088
            body = message if len(message) <= max_desc else message[: max_desc - 3] + "..."
            embed = discord.Embed(
                title=title or "Confirm",
                description=body,
                color=discord.Color.orange(),
            )

            view = SlashConfirmView(
                session_key=session_key,
                confirm_id=confirm_id,
                allowed_user_ids=self._allowed_user_ids,
                allowed_role_ids=self._allowed_role_ids,
            )

            msg = await channel.send(embed=embed, view=view)
            return SendResult(success=True, message_id=str(msg.id))
        except Exception as e:
            return SendResult(success=False, error=str(e))


    async def send_clarify(
        self,
        chat_id: str,
        question: str,
        choices: Optional[list],
        clarify_id: str,
        session_key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Render a clarify prompt with one Discord button per choice.

        Multi-choice mode (``choices`` non-empty): renders a button per option
        plus a final "✏️ Other (type answer)" button. Picking "Other" flips
        the clarify entry into text-capture mode so the next user message in
        the session becomes the response. Numeric clicks resolve immediately
        via ``resolve_gateway_clarify(clarify_id, choice_text)``.

        Open-ended mode (``choices`` empty/None): renders the question as
        plain embed text — no buttons. The gateway's text-intercept captures
        the next message in this session and resolves the clarify.
        """
        if not self._client or not DISCORD_AVAILABLE:
            return SendResult(success=False, error="Not connected")

        try:
            target_id = chat_id
            if metadata and metadata.get("thread_id"):
                target_id = metadata["thread_id"]

            channel = self._client.get_channel(int(target_id))
            if not channel:
                channel = await self._client.fetch_channel(int(target_id))

            # Discord embed description limit is 4096; trim conservatively.
            max_desc = 4088
            body = str(question or "").strip()
            if len(body) > max_desc:
                body = body[: max_desc - 3] + "..."

            embed = discord.Embed(
                title=f"❓ {_discord_brand().short_name} needs your input",
                description=body,
                color=discord.Color.orange(),
            )

            clean_choices = [
                str(c).strip() for c in (choices or []) if c is not None and str(c).strip()
            ]
            # Discord allows up to 5 buttons per row, 5 rows per view = 25.
            # We reserve one slot for the "Other" button, so cap at 24 choices.
            clean_choices = clean_choices[:24]

            if clean_choices:
                embed.add_field(
                    name="Choices",
                    value="Pick one below, or click ✏️ Other to type a custom answer.",
                    inline=False,
                )
                view = ClarifyChoiceView(
                    choices=clean_choices,
                    clarify_id=clarify_id,
                    allowed_user_ids=self._allowed_user_ids,
                    allowed_role_ids=self._allowed_role_ids,
                )
            else:
                embed.add_field(
                    name="Reply",
                    value="Reply in this channel with your answer.",
                    inline=False,
                )
                view = None

            msg = await channel.send(embed=embed, view=view) if view else await channel.send(embed=embed)
            return SendResult(success=True, message_id=str(msg.id))
        except Exception as e:
            logger.warning("[%s] send_clarify failed: %s", self.name, e)
            return SendResult(success=False, error=str(e))


    async def send_update_prompt(
        self, chat_id: str, prompt: str, default: str = "",
        session_key: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an interactive button-based update prompt (Yes / No).

        Used by the gateway ``/update`` watcher when ``miho update --gateway``
        needs user input (stash restore, config migration).
        """
        if not self._client or not DISCORD_AVAILABLE:
            return SendResult(success=False, error="Not connected")
        try:
            target_id = metadata.get("thread_id") if metadata and metadata.get("thread_id") else chat_id
            channel = self._client.get_channel(int(target_id))
            if not channel:
                channel = await self._client.fetch_channel(int(target_id))

            default_hint = f" (default: {default})" if default else ""
            embed = discord.Embed(
                title="⚕ Update Needs Your Input",
                description=f"{prompt}{default_hint}",
                color=discord.Color.gold(),
            )
            view = UpdatePromptView(
                session_key=session_key,
                allowed_user_ids=self._allowed_user_ids,
                allowed_role_ids=self._allowed_role_ids,
            )
            msg = await channel.send(embed=embed, view=view)
            return SendResult(success=True, message_id=str(msg.id))
        except Exception as e:
            return SendResult(success=False, error=str(e))


    async def send_update_available(
        self,
        chat_id: str,
        current_version: str,
        behind: int,
        session_key: str,
        confirm_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a Discord button prompt when a Miho update is available."""
        if not self._client or not DISCORD_AVAILABLE:
            return SendResult(success=False, error="Not connected")
        try:
            target_id = metadata.get("thread_id") if metadata and metadata.get("thread_id") else chat_id
            channel = self._client.get_channel(int(target_id))
            if not channel:
                channel = await self._client.fetch_channel(int(target_id))

            embed = discord.Embed(
                title="Miho 업데이트가 있어",
                description=(
                    f"현재 버전은 `{current_version}`이고, 최신 main보다 "
                    f"`{int(behind)}`개 커밋 뒤에 있어.\n\n"
                    "지금 업데이트하면 게이트웨이가 잠깐 재시작될 수 있어."
                ),
                color=discord.Color.blue(),
            )
            view = UpdateAvailableView(
                session_key=session_key,
                confirm_id=confirm_id,
                allowed_user_ids=self._allowed_user_ids,
                allowed_role_ids=self._allowed_role_ids,
            )
            msg = await channel.send(embed=embed, view=view)
            return SendResult(success=True, message_id=str(msg.id))
        except Exception as e:
            return SendResult(success=False, error=str(e))


    async def send_model_picker(
        self,
        chat_id: str,
        providers: list,
        current_model: str,
        current_provider: str,
        session_key: str,
        on_model_selected,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an interactive select-menu model picker.

        Two-step drill-down: provider dropdown → model dropdown.
        Uses Discord embeds + Select menus via ``ModelPickerView``.
        """
        if not self._client or not DISCORD_AVAILABLE:
            return SendResult(success=False, error="Not connected")

        try:
            # Resolve target channel (use thread_id if present)
            target_id = chat_id
            if metadata and metadata.get("thread_id"):
                target_id = metadata["thread_id"]

            channel = self._client.get_channel(int(target_id))
            if not channel:
                channel = await self._client.fetch_channel(int(target_id))

            try:
                from miho_cli.providers import get_label
                provider_label = get_label(current_provider)
            except Exception:
                provider_label = current_provider

            embed = discord.Embed(
                title="⚙ Model Configuration",
                description=(
                    f"Current model: `{current_model or 'unknown'}`\n"
                    f"Provider: {provider_label}\n\n"
                    f"Select a provider:"
                ),
                color=discord.Color.blue(),
            )

            view = ModelPickerView(
                providers=providers,
                current_model=current_model,
                current_provider=current_provider,
                session_key=session_key,
                on_model_selected=on_model_selected,
                allowed_user_ids=self._allowed_user_ids,
                allowed_role_ids=self._allowed_role_ids,
            )

            msg = await channel.send(embed=embed, view=view)
            return SendResult(success=True, message_id=str(msg.id))

        except Exception as e:
            logger.warning("[%s] send_model_picker failed: %s", self.name, e)
            return SendResult(success=False, error=str(e))
