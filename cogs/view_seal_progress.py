import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore
from google_services import GoogleServices
from scoring import evaluate_set, build_result_embed
import asyncio
import logging

logger = logging.getLogger('octobot')


class SealProgressCycleSelectView(discord.ui.View):
    """First step: pick a cycle to view seal progress for."""
    def __init__(self, db):
        super().__init__(timeout=300)
        self.db = db

        cycles = self.db.get_all_cycles()
        current_cycle = self.db.get_current_cycle_number()
        self.selected_cycle = current_cycle

        options = []
        for c in cycles:
            is_current = (c == current_cycle)
            label = f"Cycle {c} (current)" if is_current else f"Cycle {c}"
            options.append(discord.SelectOption(label=label, value=str(c), default=is_current))

        if len(options) > 25:
            options = options[:25]

        self.select = discord.ui.Select(
            placeholder="Select a cycle to view seal progress...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

        self.submit_button = discord.ui.Button(label="Submit", style=discord.ButtonStyle.primary)
        self.submit_button.callback = self.submit_callback
        self.add_item(self.submit_button)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_cycle = int(self.select.values[0])
        await interaction.response.defer()

    async def submit_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cycle_number = self.selected_cycle

        # --- fetch roster ---
        roster_data = self.db.get_spotlight_roster(cycle_number)
        spotlights = roster_data.get("spotlights", [])

        sets_with_forms = [s for s in spotlights if s.get("form_id")]
        if not sets_with_forms:
            await interaction.followup.send(
                f"No scorecard forms found for Cycle {cycle_number}.",
                ephemeral=True
            )
            return

        await interaction.edit_original_response(
            content=f"⏳ Fetching live scores for {len(sets_with_forms)} set(s)…",
            view=None,
        )

        # --- initialise Google Services ---
        try:
            gs = GoogleServices()
        except Exception as e:
            await interaction.followup.send(
                f"❌ Failed to initialise Google Services: {e}",
                ephemeral=True
            )
            return

        # --- evaluate each set (read-only, no DB writes) ---
        results = []
        fetch_errors = []

        for entry in sets_with_forms:
            form_id = entry["form_id"]
            set_name = entry.get("set_name", form_id)
            try:
                result = await asyncio.to_thread(evaluate_set, form_id, entry, gs)
                results.append(result)
            except Exception as e:
                logger.error(f"view-seal-progress: failed to fetch '{set_name}': {e}")
                fetch_errors.append(f"• **{set_name}**: {e}")

        if not results:
            await interaction.followup.send(
                "❌ Could not fetch responses for any set.\n" + "\n".join(fetch_errors),
                ephemeral=True
            )
            return

        # --- summary header ---
        on_track = [r for r in results if r["sealed"]]
        summary_lines = [
            f"## 📈 Cycle {cycle_number} — Live Seal Progress\n",
            f"**{len(on_track)} / {len(results)} set(s) currently on track to pass.**",
            f"*(Based on {sum(r['num_reviews'] for r in results)} total reviews so far.)*\n",
        ]
        if fetch_errors:
            summary_lines.append("⚠️ **Could not fetch data for:**")
            summary_lines.extend(fetch_errors)

        await interaction.followup.send("\n".join(summary_lines), ephemeral=True)

        # --- one embed per set, sorted: on-track first ---
        off_track = [r for r in results if not r["sealed"]]
        for result in (on_track + off_track):
            embed = build_result_embed(result, cycle_number, show_seal_status=False)
            await interaction.followup.send(embed=embed, ephemeral=True)


class ViewSealProgress(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(
        name="view-seal-progress",
        description="View live scoring progress for all Spotlight sets in a cycle."
    )
    @app_commands.default_permissions(manage_messages=True)
    async def view_seal_progress(self, interaction: discord.Interaction):
        logger.info(
            f"Admin Action: view-seal-progress initiated by "
            f"{interaction.user.name} ({interaction.user.id})"
        )
        await interaction.response.defer(ephemeral=True)

        cycles = self.db.get_all_cycles()
        if not cycles:
            await interaction.followup.send("No cycles found in the database.", ephemeral=True)
            return

        view = SealProgressCycleSelectView(self.db)
        await interaction.followup.send(
            "Select a cycle to view its seal progress:",
            view=view,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(ViewSealProgress(bot))
