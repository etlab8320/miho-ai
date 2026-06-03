from __future__ import annotations

from typing import List, Optional

from .view_base import DISCORD_AVAILABLE, _component_check_auth, discord, logger


if DISCORD_AVAILABLE:

    class UpdatePromptView(discord.ui.View):
        """Interactive Yes/No buttons for ``miho update`` prompts.

        Clicking a button writes the answer to ``.update_response`` so the
        detached update process can pick it up.  Only authorized users can
        click.  Times out after 5 minutes (the update process also has a
        5-minute timeout on its side).
        """

        def __init__(
            self,
            session_key: str,
            allowed_user_ids: set,
            allowed_role_ids: Optional[set] = None,
        ):
            super().__init__(timeout=300)
            self.session_key = session_key
            self.allowed_user_ids = allowed_user_ids
            self.allowed_role_ids = allowed_role_ids or set()
            self.resolved = False

        def _check_auth(self, interaction: discord.Interaction) -> bool:
            return _component_check_auth(
                interaction, self.allowed_user_ids, self.allowed_role_ids,
            )

        async def _respond(
            self, interaction: discord.Interaction, answer: str,
            color: discord.Color, label: str,
        ):
            if self.resolved:
                await interaction.response.send_message(
                    "Already answered~", ephemeral=True
                )
                return
            if not self._check_auth(interaction):
                await interaction.response.send_message(
                    "You're not authorized~", ephemeral=True
                )
                return

            self.resolved = True

            # Update embed
            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed:
                embed.color = color
                embed.set_footer(text=f"{label} by {interaction.user.display_name}")

            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)

            # Write response file
            try:
                from miho_constants import get_miho_home
                home = get_miho_home()
                response_path = home / ".update_response"
                tmp = response_path.with_suffix(".tmp")
                tmp.write_text(answer)
                tmp.replace(response_path)
                logger.info(
                    "Discord update prompt answered '%s' by %s",
                    answer, interaction.user.display_name,
                )
            except Exception as exc:
                logger.error("Failed to write update response: %s", exc)

        @discord.ui.button(label="Yes", style=discord.ButtonStyle.green, emoji="✓")
        async def yes_btn(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            await self._respond(interaction, "y", discord.Color.green(), "Yes")

        @discord.ui.button(label="No", style=discord.ButtonStyle.red, emoji="✗")
        async def no_btn(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            await self._respond(interaction, "n", discord.Color.red(), "No")

        async def on_timeout(self):
            self.resolved = True
            for child in self.children:
                child.disabled = True


    class UpdateAvailableView(discord.ui.View):
        """Two-button prompt for starting a detected Miho update."""

        def __init__(
            self,
            session_key: str,
            confirm_id: str,
            allowed_user_ids: set,
            allowed_role_ids: Optional[set] = None,
        ):
            super().__init__(timeout=300)
            self.session_key = session_key
            self.confirm_id = confirm_id
            self.allowed_user_ids = allowed_user_ids
            self.allowed_role_ids = allowed_role_ids or set()
            self.resolved = False

        def _check_auth(self, interaction: discord.Interaction) -> bool:
            return _component_check_auth(
                interaction, self.allowed_user_ids, self.allowed_role_ids,
            )

        async def _resolve(
            self,
            interaction: discord.Interaction,
            choice: str,
            color: discord.Color,
            label: str,
        ):
            if self.resolved:
                await interaction.response.send_message(
                    "이미 처리된 업데이트 알림이야.", ephemeral=True,
                )
                return
            if not self._check_auth(interaction):
                await interaction.response.send_message(
                    "이 업데이트를 실행할 권한이 없어.", ephemeral=True,
                )
                return

            self.resolved = True
            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed:
                embed.color = color
                embed.set_footer(text=f"{label} · {interaction.user.display_name}")

            for child in self.children:
                child.disabled = True

            await interaction.response.edit_message(embed=embed, view=self)

            try:
                from tools import slash_confirm as _slash_confirm_mod
                result_text = await _slash_confirm_mod.resolve(
                    self.session_key,
                    self.confirm_id,
                    choice,
                )
                if result_text:
                    await interaction.followup.send(result_text)
            except Exception as exc:
                logger.error("Discord update-available resolve failed: %s", exc, exc_info=True)

        @discord.ui.button(label="업데이트 하기", style=discord.ButtonStyle.green)
        async def update_now(
            self, interaction: discord.Interaction, button: discord.ui.Button,
        ):
            await self._resolve(interaction, "once", discord.Color.green(), "업데이트 시작")

        @discord.ui.button(label="나중에", style=discord.ButtonStyle.grey)
        async def later(
            self, interaction: discord.Interaction, button: discord.ui.Button,
        ):
            await self._resolve(interaction, "cancel", discord.Color.blue(), "나중에")

        async def on_timeout(self):
            self.resolved = True
            for child in self.children:
                child.disabled = True


else:

    UpdatePromptView = None

    UpdateAvailableView = None
