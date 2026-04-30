import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore
from google_services import GoogleServices
from scoring import evaluate_set, build_result_embed
import asyncio
import logging

logger = logging.getLogger('octobot')


class ConfirmSeals(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(
        name="confirm-seals",
        description="Admin: Evaluate all Spotlight forms, determine Seal pass/fail, and write sealed sets to the database."
    )
    @app_commands.default_permissions(manage_messages=True)
    async def confirm_seals(self, interaction: discord.Interaction):
        logger.info(
            f"Admin Action: confirm-seals initiated by "
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

        if not spotlights:
            await interaction.followup.send(
                f"❌ No Spotlight roster found for Cycle {cycle_number}. "
                "Run `/confirm-spotlight` first.",
                ephemeral=True
            )
            return

        sets_with_forms = [s for s in spotlights if s.get("form_id")]
        if not sets_with_forms:
            await interaction.followup.send(
                "❌ No Google Form IDs found on the Spotlight roster. "
                "Forms must be generated before seals can be confirmed.",
                ephemeral=True
            )
            return

        await interaction.followup.send(
            f"⏳ Fetching form responses for {len(sets_with_forms)} set(s). "
            "This may take a moment…",
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

        # --- evaluate each set ---
        results = []
        fetch_errors = []

        for entry in sets_with_forms:
            form_id = entry["form_id"]
            set_name = entry.get("set_name", form_id)
            try:
                result = await asyncio.to_thread(evaluate_set, form_id, entry, gs)
                results.append(result)
            except Exception as e:
                logger.error(f"confirm-seals: failed to evaluate '{set_name}': {e}")
                fetch_errors.append(f"• **{set_name}**: {e}")

        if not results:
            await interaction.followup.send(
                "❌ Could not fetch responses for any set.\n" + "\n".join(fetch_errors),
                ephemeral=True
            )
            return

        # --- transactional DB writes ---
        sealed_results = [r for r in results if r["sealed"]]
        failed_results = [r for r in results if not r["sealed"]]

        db_error = None
        try:
            if sealed_results:
                sealed_for_db = []
                for r in sealed_results:
                    original = next(
                        (s for s in spotlights if s.get("set_name") == r["set_name"]),
                        {}
                    )
                    sealed_for_db.append({**original, "sealed": True})
                self.db.copy_to_sealed_sets(cycle_number, sealed_for_db)

            sealed_names = {r["set_name"] for r in sealed_results}
            updated_spotlights = [
                {**entry, "sealed": entry.get("set_name") in sealed_names}
                for entry in spotlights
            ]
            self.db.save_spotlight_roster(cycle_number, updated_spotlights)

        except Exception as e:
            logger.error(f"confirm-seals: DB write failed: {e}")
            db_error = e

        # --- build report ---
        summary_lines = [
            f"## 🏅 Cycle {cycle_number} — Seal Results\n",
            f"**{len(sealed_results)} / {len(results)} set(s) earned the Community Seal.**\n",
        ]
        if fetch_errors:
            summary_lines.append("⚠️ **Fetch errors (these sets were skipped):**")
            summary_lines.extend(fetch_errors)
            summary_lines.append("")
        if db_error:
            summary_lines.append(
                f"⚠️ **Database write failed — results above are correct but were NOT saved:** {db_error}"
            )

        await interaction.followup.send("\n".join(summary_lines), ephemeral=True)

        for result in (sealed_results + failed_results):
            embed = build_result_embed(result, cycle_number, show_seal_status=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

        if db_error is None:
            await interaction.followup.send(
                f"✅ Database updated. {len(sealed_results)} set(s) written to `sealed_sets`. "
                "Spotlight roster `sealed` flags updated.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ The evaluation is correct, but the database write failed. "
                "Please check the logs and re-run after resolving the issue.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(ConfirmSeals(bot))
