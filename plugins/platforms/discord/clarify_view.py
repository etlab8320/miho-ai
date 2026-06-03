from __future__ import annotations

from typing import List, Optional

from .view_base import DISCORD_AVAILABLE, _component_check_auth, discord, logger


if DISCORD_AVAILABLE:

    class ClarifyChoiceView(discord.ui.View):
        """Interactive button view for the clarify tool's multiple-choice prompts.

        Renders one button per choice (max 24) plus a final ``✏️ Other`` button.
        Picking a numeric choice resolves the gateway clarify entry immediately;
        picking ``Other`` flips the entry into text-capture mode so the next
        user message in the session becomes the response (the gateway's
        text-intercept handles the resolution).

        Auth gating mirrors ``ExecApprovalView`` — only users/roles in the
        Discord adapter's allowlist may answer. Single-use: after the first
        valid click all buttons disable and the embed updates to show who
        answered and what they chose.
        """

        def __init__(
            self,
            choices: List[str],
            clarify_id: str,
            allowed_user_ids: set,
            allowed_role_ids: Optional[set] = None,
        ):
            super().__init__(timeout=300)  # 5-minute timeout
            self.choices = list(choices)[:24]
            self.clarify_id = clarify_id
            self.allowed_user_ids = allowed_user_ids
            self.allowed_role_ids = allowed_role_ids or set()
            self.resolved = False

            for index, choice in enumerate(self.choices):
                # Discord button labels are capped at 80 chars.
                label_body = choice if len(choice) <= 75 else choice[:72] + "..."
                button = discord.ui.Button(
                    label=f"{index + 1}. {label_body}",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"clarify:{clarify_id}:{index}",
                )
                button.callback = self._make_choice_callback(index, choice)
                self.add_item(button)

            other_btn = discord.ui.Button(
                label="✏️ Other (type answer)",
                style=discord.ButtonStyle.secondary,
                custom_id=f"clarify:{clarify_id}:other",
            )
            other_btn.callback = self._on_other
            self.add_item(other_btn)

        def _check_auth(self, interaction: "discord.Interaction") -> bool:
            return _component_check_auth(
                interaction, self.allowed_user_ids, self.allowed_role_ids,
            )

        def _make_choice_callback(self, index: int, choice: str):
            async def _callback(interaction: "discord.Interaction"):
                await self._resolve_choice(interaction, index, choice)
            return _callback

        async def _resolve_choice(
            self,
            interaction: "discord.Interaction",
            index: int,
            choice: str,
        ) -> None:
            """Resolve the clarify with a chosen option."""
            if self.resolved:
                await interaction.response.send_message(
                    "This prompt has already been answered~", ephemeral=True,
                )
                return
            if not self._check_auth(interaction):
                await interaction.response.send_message(
                    "You're not authorized to answer this prompt~", ephemeral=True,
                )
                return

            self.resolved = True
            for child in self.children:
                child.disabled = True

            embed = interaction.message.embeds[0] if (
                interaction.message and interaction.message.embeds
            ) else None
            if embed:
                user = getattr(interaction, "user", None)
                display_name = getattr(user, "display_name", "user")
                embed.color = discord.Color.green()
                embed.set_footer(text=f"Answered by {display_name}: {choice}")

            try:
                await interaction.response.edit_message(embed=embed, view=self)
            except Exception:
                logger.debug(
                    "Discord clarify edit_message failed for %s",
                    self.clarify_id,
                    exc_info=True,
                )
                try:
                    await interaction.response.defer()
                except Exception:
                    pass

            # Resolve via the gateway clarify primitive — same mechanism as
            # Telegram. Look up the canonical choice text from the entry so
            # we round-trip the original value, not a button-label variant.
            resolved_text: Optional[str] = None
            try:
                from tools.clarify_gateway import _entries as _clarify_entries  # type: ignore
                entry = _clarify_entries.get(self.clarify_id)
                if entry and entry.choices and 0 <= index < len(entry.choices):
                    resolved_text = entry.choices[index]
            except Exception:
                resolved_text = None
            if resolved_text is None:
                resolved_text = choice

            try:
                from tools.clarify_gateway import resolve_gateway_clarify
                resolved = resolve_gateway_clarify(self.clarify_id, resolved_text)
                logger.info(
                    "Discord clarify button resolved (id=%s, choice=%r, user=%s, ok=%s)",
                    self.clarify_id, resolved_text,
                    getattr(getattr(interaction, "user", None), "display_name", "?"),
                    resolved,
                )
            except Exception as exc:
                logger.error(
                    "Discord clarify resolve_gateway_clarify failed (id=%s): %s",
                    self.clarify_id, exc,
                )

        async def _on_other(self, interaction: "discord.Interaction") -> None:
            """Flip the clarify entry into text-capture mode."""
            if self.resolved:
                await interaction.response.send_message(
                    "This prompt has already been answered~", ephemeral=True,
                )
                return
            if not self._check_auth(interaction):
                await interaction.response.send_message(
                    "You're not authorized to answer this prompt~", ephemeral=True,
                )
                return

            # Don't pop the entry — the gateway's text-intercept needs it
            # until the user actually types. Just mark it as awaiting text
            # and disable the buttons so the user can't double-click.
            try:
                from tools.clarify_gateway import mark_awaiting_text
                mark_awaiting_text(self.clarify_id)
            except Exception as exc:
                logger.warning(
                    "Discord clarify mark_awaiting_text failed (id=%s): %s",
                    self.clarify_id, exc,
                )

            self.resolved = True
            for child in self.children:
                child.disabled = True

            embed = interaction.message.embeds[0] if (
                interaction.message and interaction.message.embeds
            ) else None
            if embed:
                user = getattr(interaction, "user", None)
                display_name = getattr(user, "display_name", "user")
                embed.color = discord.Color.blue()
                embed.set_footer(
                    text=f"Awaiting typed response from {display_name}…",
                )

            try:
                await interaction.response.edit_message(embed=embed, view=self)
            except Exception:
                try:
                    await interaction.response.defer()
                except Exception:
                    pass

        async def on_timeout(self):
            self.resolved = True
            for child in self.children:
                child.disabled = True


else:

    ClarifyChoiceView = None
