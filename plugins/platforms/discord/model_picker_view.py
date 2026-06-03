from __future__ import annotations

from typing import List, Optional

from .view_base import DISCORD_AVAILABLE, _component_check_auth, discord, logger


if DISCORD_AVAILABLE:

    class ModelPickerView(discord.ui.View):
        """Interactive select-menu view for model switching.

        Two-step drill-down: provider dropdown → model dropdown.
        Edits the original message in-place as the user navigates.
        Times out after 2 minutes.
        """

        def __init__(
            self,
            providers: list,
            current_model: str,
            current_provider: str,
            session_key: str,
            on_model_selected,
            allowed_user_ids: set,
            allowed_role_ids: Optional[set] = None,
        ):
            super().__init__(timeout=120)
            self.providers = providers
            self.current_model = current_model
            self.current_provider = current_provider
            self.session_key = session_key
            self.on_model_selected = on_model_selected
            self.allowed_user_ids = allowed_user_ids
            self.allowed_role_ids = allowed_role_ids or set()
            self.resolved = False
            self._selected_provider: str = ""

            self._build_provider_select()

        def _check_auth(self, interaction: discord.Interaction) -> bool:
            return _component_check_auth(
                interaction, self.allowed_user_ids, self.allowed_role_ids,
            )

        def _build_provider_select(self):
            """Build the provider dropdown menu."""
            self.clear_items()
            options = []
            for p in self.providers:
                count = p.get("total_models", len(p.get("models", [])))
                label = f"{p['name']} ({count} models)"
                desc = "current" if p.get("is_current") else None
                options.append(
                    discord.SelectOption(
                        label=label[:100],
                        value=p["slug"],
                        description=desc,
                    )
                )
            if not options:
                return

            select = discord.ui.Select(
                placeholder="Choose a provider...",
                options=options[:25],
                custom_id="model_provider_select",
            )
            select.callback = self._on_provider_selected
            self.add_item(select)

            cancel_btn = discord.ui.Button(
                label="Cancel", style=discord.ButtonStyle.red, custom_id="model_cancel"
            )
            cancel_btn.callback = self._on_cancel
            self.add_item(cancel_btn)

        def _build_model_select(self, provider_slug: str):
            """Build the model dropdown for a specific provider."""
            self.clear_items()
            provider = next(
                (p for p in self.providers if p["slug"] == provider_slug), None
            )
            if not provider:
                return

            models = provider.get("models", [])
            options = []
            for model_id in models[:25]:
                short = model_id.split("/")[-1] if "/" in model_id else model_id
                options.append(
                    discord.SelectOption(
                        label=short[:100],
                        value=model_id[:100],
                    )
                )
            if not options:
                return

            select = discord.ui.Select(
                placeholder=f"Choose a model from {provider.get('name', provider_slug)}...",
                options=options,
                custom_id="model_model_select",
            )
            select.callback = self._on_model_selected
            self.add_item(select)

            back_btn = discord.ui.Button(
                label="◀ Back", style=discord.ButtonStyle.grey, custom_id="model_back"
            )
            back_btn.callback = self._on_back
            self.add_item(back_btn)

            cancel_btn = discord.ui.Button(
                label="Cancel", style=discord.ButtonStyle.red, custom_id="model_cancel2"
            )
            cancel_btn.callback = self._on_cancel
            self.add_item(cancel_btn)

        async def _on_provider_selected(self, interaction: discord.Interaction):
            if not self._check_auth(interaction):
                await interaction.response.send_message(
                    "You're not authorized~", ephemeral=True
                )
                return

            provider_slug = interaction.data["values"][0]
            self._selected_provider = provider_slug
            provider = next(
                (p for p in self.providers if p["slug"] == provider_slug), None
            )
            pname = provider.get("name", provider_slug) if provider else provider_slug

            self._build_model_select(provider_slug)

            total = provider.get("total_models", 0) if provider else 0
            shown = min(len(provider.get("models", [])), 25) if provider else 0
            extra = f"\n*{total - shown} more available — type `/model <name>` directly*" if total > shown else ""

            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="⚙ Model Configuration",
                    description=f"Provider: **{pname}**\nSelect a model:{extra}",
                    color=discord.Color.blue(),
                ),
                view=self,
            )

        async def _on_model_selected(self, interaction: discord.Interaction):
            if self.resolved:
                await interaction.response.send_message(
                    "Already resolved~", ephemeral=True
                )
                return
            if not self._check_auth(interaction):
                await interaction.response.send_message(
                    "You're not authorized~", ephemeral=True
                )
                return

            self.resolved = True
            model_id = interaction.data["values"][0]
            self.clear_items()
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="⚙ Switching Model",
                    description=f"Switching to `{model_id}`...",
                    color=discord.Color.blue(),
                ),
                view=None,
            )

            try:
                result_text = await self.on_model_selected(
                    str(interaction.channel_id),
                    model_id,
                    self._selected_provider,
                )
            except Exception as exc:
                result_text = f"Error switching model: {exc}"

            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="⚙ Model Switched",
                    description=result_text,
                    color=discord.Color.green(),
                ),
                view=None,
            )

        async def _on_back(self, interaction: discord.Interaction):
            if not self._check_auth(interaction):
                await interaction.response.send_message(
                    "You're not authorized~", ephemeral=True
                )
                return

            self._build_provider_select()

            try:
                from miho_cli.providers import get_label
                provider_label = get_label(self.current_provider)
            except Exception:
                provider_label = self.current_provider

            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="⚙ Model Configuration",
                    description=(
                        f"Current model: `{self.current_model or 'unknown'}`\n"
                        f"Provider: {provider_label}\n\n"
                        f"Select a provider:"
                    ),
                    color=discord.Color.blue(),
                ),
                view=self,
            )

        async def _on_cancel(self, interaction: discord.Interaction):
            self.resolved = True
            self.clear_items()
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="⚙ Model Configuration",
                    description="Model selection cancelled.",
                    color=discord.Color.greyple(),
                ),
                view=self,
            )

        async def on_timeout(self):
            self.resolved = True
            self.clear_items()


else:

    ModelPickerView = None
