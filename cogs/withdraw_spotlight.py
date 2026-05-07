import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore
import logging

logger = logging.getLogger('octobot')

class WithdrawConfirmView(discord.ui.View):
    """Confirm/Cancel prompt to withdraw a spotlight set."""
    def __init__(self, db: MCPFirestore, cycle_number: int, set_name: str):
        super().__init__(timeout=300)
        self.db = db
        self.cycle_number = cycle_number
        self.set_name = set_name

    def _disable_all(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Yes, Withdraw", style=discord.ButtonStyle.danger)
    async def btn_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._disable_all()
        try:
            self.db.update_spotlight_entry(self.cycle_number, self.set_name, {"withdrawn": True})
            env_prefix = "[TEST] " if self.db.collection_prefix else ""
            logger.info(f"{env_prefix}withdraw-spotlight: '{self.set_name}' in Cycle {self.cycle_number} marked as withdrawn by {interaction.user.name}.")
            await interaction.response.edit_message(content=f"✅ '{self.set_name}' has been marked as withdrawn.", view=self)
        except Exception as e:
            logger.error(f"Failed to withdraw '{self.set_name}': {e}")
            await interaction.response.edit_message(content=f"❌ Failed to update the database: {e}", view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._disable_all()
        await interaction.response.edit_message(content="❌ Cancelled. The set was not withdrawn.", view=self)

class SpotlightSelectView(discord.ui.View):
    """Dropdown to select which spotlight set to withdraw."""
    def __init__(self, db: MCPFirestore, cycle_number: int, spotlights: list):
        super().__init__(timeout=300)
        self.db = db
        self.cycle_number = cycle_number
        self.selected_set = None

        options = []
        for s in spotlights:
            name = s.get("set_name", "Unknown")
            is_withdrawn = s.get("withdrawn", False)
            label = f"{name} (Withdrawn)" if is_withdrawn else name
            options.append(discord.SelectOption(label=label, value=name))

        if len(options) > 25:
            options = options[:25]

        self.select = discord.ui.Select(
            placeholder="Select a spotlight set to withdraw...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

        self.submit_button = discord.ui.Button(label="Select", style=discord.ButtonStyle.primary)
        self.submit_button.callback = self.submit_callback
        self.add_item(self.submit_button)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_set = self.select.values[0]
        await interaction.response.defer()

    async def submit_callback(self, interaction: discord.Interaction):
        if not self.selected_set:
            await interaction.response.send_message("Please select a set first.", ephemeral=True)
            return

        confirm_view = WithdrawConfirmView(self.db, self.cycle_number, self.selected_set)
        await interaction.response.edit_message(
            content=f"Are you sure you want to withdraw **{self.selected_set}**? It will automatically fail the Seal criteria.",
            view=confirm_view
        )

class WithdrawSpotlight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(
        name="withdraw-spotlight",
        description="Admin: Mark a current spotlight set as withdrawn, automatically failing its seal."
    )
    @app_commands.default_permissions(manage_messages=True)
    async def withdraw_spotlight(self, interaction: discord.Interaction):
        env_prefix = "[TEST] " if self.db.collection_prefix else ""
        logger.info(
            f"{env_prefix}Admin Action: withdraw-spotlight initiated by "
            f"{interaction.user.name} ({interaction.user.id})"
        )
        await interaction.response.defer(ephemeral=True)

        cycle_number = self.db.get_current_cycle_number()
        roster_data = self.db.get_spotlight_roster(cycle_number)
        spotlights = roster_data.get("spotlights", [])

        if not spotlights:
            await interaction.followup.send(
                f"❌ No Spotlight roster found for Cycle {cycle_number}.",
                ephemeral=True
            )
            return

        view = SpotlightSelectView(self.db, cycle_number, spotlights)
        await interaction.followup.send(
            f"Select a set from Cycle {cycle_number} to withdraw:",
            view=view,
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(WithdrawSpotlight(bot))
