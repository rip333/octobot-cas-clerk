import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore
from google_services import GoogleServices
from scoring import evaluate_set, build_result_embed
import asyncio
import logging

logger = logging.getLogger('octobot')


class ViewSealProgress(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(
        name="view-seal-progress",
        description="Admin: View live scoring progress for all Spotlight sets in the current review cycle."
    )
    @app_commands.default_permissions(manage_messages=True)
    async def view_seal_progress(self, interaction: discord.Interaction):
        logger.info(
            f"Admin Action: view-seal-progress initiated by "
            f"{interaction.user.name} ({interaction.user.id})"
        )
        await interaction.response.defer(ephemeral=True)

        # --- state gate ---
        metadata = self.db.get_cycle_metadata()
        if metadata.get("state") != "review":
            await interaction.followup.send(
                "❌ **Invalid state.** This command can only be run during the `review` phase.",
                ephemeral=True
            )
            return

        cycle_number = int(metadata.get("number", 0))

        # --- fetch roster ---
        roster_data = self.db.get_spotlight_roster(cycle_number)
        spotlights = roster_data.get("spotlights", [])

        sets_with_forms = [s for s in spotlights if s.get("form_id")]
        if not sets_with_forms:
            await interaction.followup.send(
                f"❌ No Google Forms found for Cycle {cycle_number}.",
                ephemeral=True
            )
            return

        await interaction.followup.send(
            f"⏳ Fetching live scores for {len(sets_with_forms)} set(s)…",
            ephemeral=True
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


async def setup(bot):
    await bot.add_cog(ViewSealProgress(bot))
