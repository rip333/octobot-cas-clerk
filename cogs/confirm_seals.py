import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore
from google_services import GoogleServices
from scoring import evaluate_set, build_result_embed
import asyncio
import logging

logger = logging.getLogger('octobot')


class ConfirmSealView(discord.ui.View):
    """Confirm/Cancel prompt shown after displaying seal results, before writing to the DB."""
    def __init__(self):
        super().__init__(timeout=300)
        self._decision: asyncio.Future = asyncio.get_event_loop().create_future()

    @property
    def decision(self) -> asyncio.Future:
        return self._decision

    def _disable_all(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Confirm & Save to Database", style=discord.ButtonStyle.success)
    async def btn_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._disable_all()
        await interaction.response.edit_message(content="✅ Confirmed. Writing seal results to the database…", view=self)
        if not self._decision.done():
            self._decision.set_result(True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._disable_all()
        await interaction.response.edit_message(content="❌ Cancelled. No changes were made to the database.", view=self)
        if not self._decision.done():
            self._decision.set_result(False)


class ConfirmSeals(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(
        name="confirm-seals",
        description="Admin: Evaluate Spotlight forms, determine Seal pass/fail, and write results to the database."
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

        # --- display results for review ---
        sealed_results = [r for r in results if r["sealed"]]
        failed_results = [r for r in results if not r["sealed"]]

        summary_lines = [
            f"## 🏅 Cycle {cycle_number} — Seal Results Preview\n",
            f"**{len(sealed_results)} / {len(results)} set(s) would earn the Community Seal.**\n",
        ]
        if fetch_errors:
            summary_lines.append("⚠️ **Fetch errors (these sets were skipped):**")
            summary_lines.extend(fetch_errors)
            summary_lines.append("")

        await interaction.followup.send("\n".join(summary_lines), ephemeral=True)

        for result in (sealed_results + failed_results):
            embed = build_result_embed(result, cycle_number, show_seal_status=True)
            await interaction.followup.send(embed=embed, ephemeral=True)

        # --- confirmation prompt ---
        confirm_view = ConfirmSealView()
        await interaction.followup.send(
            f"**Review the results above.** Confirming will write {len(sealed_results)} sealed set(s) "
            "to the database and update spotlight roster flags. This cannot be undone.",
            view=confirm_view,
            ephemeral=True,
        )

        proceed = await confirm_view.decision
        if not proceed:
            await interaction.followup.send("❌ Aborted. No database changes were made.", ephemeral=True)
            return

        # --- transactional DB writes ---
        db_error = None
        try:
            logger.info(f"confirm-seals: {len(sealed_results)} sealed, {len(failed_results)} failed out of {len(results)} total")
            if sealed_results:
                sealed_for_db = []
                for r in sealed_results:
                    original = next(
                        (s for s in spotlights if s.get("set_name") == r["set_name"]),
                        {}
                    )
                    sealed_for_db.append({**original, "sealed": True})
                logger.info(f"confirm-seals: Writing {len(sealed_for_db)} entries to sealed_sets")
                self.db.copy_to_sealed_sets(cycle_number, sealed_for_db)
            else:
                logger.info("confirm-seals: No sealed results — skipping sealed_sets write.")

            # Update the sealed flag on each individual spotlight entry
            for result in results:
                self.db.update_spotlight_entry(
                    cycle_number,
                    result["set_name"],
                    {"sealed": result["sealed"]}
                )

            # Transition cycle state to complete
            self.db.update_cycle(cycle_number, {"state": "complete", "is_active": False})

        except Exception as e:
            logger.error(f"confirm-seals: DB write failed: {e}")
            db_error = e

        if db_error is None:
            await interaction.followup.send(
                f"✅ Database updated. {len(sealed_results)} set(s) written to `sealed_sets`. "
                "Spotlight roster flags updated. Cycle state set to **complete**.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ The evaluation is correct, but the database write failed: {db_error}\n"
                "Please check the logs and re-run after resolving the issue.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(ConfirmSeals(bot))

