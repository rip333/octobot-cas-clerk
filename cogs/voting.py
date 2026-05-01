import discord
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore
import logging

logger = logging.getLogger('octobot')

def get_filtered_results(db):
    votes = db.get_all_votes()
    noms = db.get_nominations()
    
    nom_map = {}
    for data in noms:
        set_name = data.get('set_name', data.get('nomineeName', 'Unknown'))
        nom_map[set_name] = data

    hero_counts = {}
    encounter_counts = {}
    total_voters = 0
    
    for data in votes:
        total_voters += 1
        for hero_obj in data.get('heroes', []):
            if isinstance(hero_obj, dict):
                set_name = hero_obj.get('set_name', hero_obj.get('nomineeName', 'Unknown'))
            else:
                set_name = hero_obj.split(' — ')[0]
            hero_counts[set_name] = hero_counts.get(set_name, 0) + 1
            
        for encounter_obj in data.get('encounters', []):
            if isinstance(encounter_obj, dict):
                set_name = encounter_obj.get('set_name', encounter_obj.get('nomineeName', 'Unknown'))
            else:
                set_name = encounter_obj.split(' — ')[0]
            encounter_counts[set_name] = encounter_counts.get(set_name, 0) + 1
            
    sorted_heroes = sorted(hero_counts.items(), key=lambda x: (-x[1], x[0]))
    sorted_encounters = sorted(encounter_counts.items(), key=lambda x: (-x[1], x[0]))
    
    def filter_by_creator(sorted_items):
        filtered = []
        ignored = []
        seen_creators = set()
        for item_name, count in sorted_items:
            nom_data = nom_map.get(item_name)
            creator = nom_data.get('creatorName', '') if nom_data else ''
            if creator:
                if creator in seen_creators:
                    ignored.append((item_name, count))
                    continue
                seen_creators.add(creator)
            filtered.append((item_name, count))
        return filtered, ignored

    filtered_heroes, ignored_heroes = filter_by_creator(sorted_heroes)
    filtered_encounters, ignored_encounters = filter_by_creator(sorted_encounters)

    return {
        'total_voters': total_voters,
        'heroes': filtered_heroes,
        'ignored_heroes': ignored_heroes,
        'encounters': filtered_encounters,
        'ignored_encounters': ignored_encounters,
        'nom_map': nom_map
    }

class VotingView(discord.ui.View):
    def __init__(self, db, hero_options, encounter_options):
        super().__init__(timeout=None)
        self.db = db
        self.add_selects(encounter_options, hero_options)
    async def select_callback(self, interaction: discord.Interaction):
        # Acknowledge the interaction so Discord doesn't show "This interaction failed"
        await interaction.response.defer()
        
    def add_selects(self, encounter_options, hero_options):
        # Add Encounter Select (Max 3)
        if encounter_options:
            self.encounter_select = discord.ui.Select(
                placeholder="Select up to 3 encounters...",
                min_values=0,
                max_values=min(3, len(encounter_options)),
                options=encounter_options,
                custom_id="voting_encounter_select"
            )
            self.encounter_select.callback = self.select_callback
            self.add_item(self.encounter_select)
        
        # Add Hero Selects (Max 10)
        # Handle Discord's 25 option limit per select menu
        self.hero_selects = []
        for i, chunk in enumerate(self.chunk_list(hero_options, 25)):
            max_v = min(10, len(chunk))
            
            # Label format e.g. "Select Heroes (A - M)" or just the first/last letters
            first_letter = chunk[0].label[0].upper()
            last_letter = chunk[-1].label[0].upper()
            label_suffix = f"({first_letter} - {last_letter})" if first_letter != last_letter else f"({first_letter})"
            
            select = discord.ui.Select(
                placeholder=f"Select Heroes {label_suffix}",
                min_values=0,
                max_values=max_v,
                options=chunk,
                custom_id=f"voting_hero_select_{i}"
            )
            select.callback = self.select_callback
            self.hero_selects.append(select)
            self.add_item(select)
            
        # Add Submit Button
        self.submit_button = discord.ui.Button(
            label="Submit Votes",
            style=discord.ButtonStyle.success,
            custom_id="voting_submit_button"
        )
        self.submit_button.callback = self.submit_callback
        self.add_item(self.submit_button)

    @staticmethod
    def chunk_list(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    async def submit_callback(self, interaction: discord.Interaction):
        # Gather all selected heroes and encounters
        selected_encounters = self.encounter_select.values if hasattr(self, 'encounter_select') else []
        
        selected_heroes = []
        for select in self.hero_selects:
            selected_heroes.extend(select.values)
            
        # Validate totals — defer first so the original voting UI stays visible,
        # then send the error as an ephemeral followup (dismissable popup).
        if len(selected_heroes) > 10:
            await interaction.response.defer()
            await interaction.followup.send("❌ **Error:** Hero maximum is 10.", ephemeral=True)
            return
        if len(selected_encounters) > 3:
            await interaction.response.defer()
            await interaction.followup.send("❌ **Error:** Encounter maximum is 3." , ephemeral=True)
            return
        if len(selected_heroes) == 0 and len(selected_encounters) == 0:
            await interaction.response.defer()
            await interaction.followup.send("❌ **Error:** Please make at least one selection before submitting.", ephemeral=True)
            return

        # Build objects from selected set_names
        noms = self.db.get_nominations()
        nom_map = {}
        for data in noms:
            set_name = data.get('set_name', data.get('nomineeName', 'Unknown'))
            nom_map[set_name] = {
                "set_name": set_name,
                "creatorName": data.get('creatorName', 'Unknown'),
                "category": data.get('category', 'Unknown'),
                "ip_category": data.get('ip_category', 'Other')
            }

        heroes_objs = [nom_map.get(sn, {"set_name": sn}) for sn in selected_heroes]
        encounters_objs = [nom_map.get(sn, {"set_name": sn}) for sn in selected_encounters]

        # Record to Firestore
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        logger.info(f"User Action: Vote submitted by {user_name} ({user_id}) - Heroes: {len(heroes_objs)}, Encounters: {len(encounters_objs)}")
        self.db.record_user_vote(user_id, user_name, heroes_objs, encounters_objs)
        
        content = f"**✅ votes_submitted**"
        await interaction.response.edit_message(content=content, view=None)

class ConfirmProceedView(discord.ui.View):
    """Yes/No prompt shown when an automatic re-tally fails before opening voting."""
    def __init__(self):
        super().__init__(timeout=300)
        self._decision: asyncio.Future = asyncio.get_event_loop().create_future()

    @property
    def decision(self) -> asyncio.Future:
        return self._decision

    def _disable_all(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Yes, proceed with existing data", style=discord.ButtonStyle.success)
    async def btn_proceed(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._disable_all()
        await interaction.response.edit_message(content="✅ Proceeding with existing nomination data…", view=self)
        if not self._decision.done():
            self._decision.set_result(True)

    @discord.ui.button(label="No, abort", style=discord.ButtonStyle.danger)
    async def btn_abort(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._disable_all()
        await interaction.response.edit_message(content="❌ Aborted. No changes were made.", view=self)
        if not self._decision.done():
            self._decision.set_result(False)


class Voting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(
        name="end-nominations-start-vote",
        description="Admin: Close nominations, verify tally is current, then open voting."
    )
    @app_commands.default_permissions(manage_messages=True)
    async def end_nominations_start_vote(self, interaction: discord.Interaction):
        logger.info(f"Admin Action: end-nominations-start-vote initiated by {interaction.user.name} ({interaction.user.id})")
        await interaction.response.defer(ephemeral=True)

        metadata = self.db.get_cycle_metadata()
        if metadata.get("state") != "nominations":
            await interaction.followup.send(
                "❌ **Invalid state.** This command can only be run during the `nominations` phase.",
                ephemeral=True,
            )
            return

        if not interaction.guild:
            await interaction.followup.send(
                "❌ **Invalid environment.** This command must be run within a server.",
                ephemeral=True,
            )
            return

        # ── Step 1: Check if the thread has new messages since the last tally ──
        thread_id = metadata.get("nomination_thread_id", 0)
        last_tallied = str(metadata.get("last_tallied_message_id", ""))

        if thread_id:
            try:
                channel = await self.bot.fetch_channel(int(thread_id))
                latest_id = None
                async for msg in channel.history(limit=1):
                    latest_id = str(msg.id)

                if latest_id and latest_id != last_tallied:
                    await interaction.followup.send(
                        "🔄 New messages detected since the last `/tally-nominations`. Re-running AI tally now…",
                        ephemeral=True,
                    )
                    from cogs.process_nominations import run_nomination_tally
                    tally_result = await run_nomination_tally(self.bot, self.db)

                    if not tally_result["success"]:
                        view = ConfirmProceedView()
                        await interaction.followup.send(
                            f"⚠️ **Re-tally failed:** {tally_result['error']}\n\n"
                            "Proceed with the existing nomination data anyway?",
                            view=view,
                            ephemeral=True,
                        )
                        proceed = await view.decision
                        if not proceed:
                            await interaction.followup.send("❌ Aborted. No changes were made.", ephemeral=True)
                            return
                    else:
                        await interaction.followup.send(
                            f"✅ Re-tally complete — **{tally_result['added_count']}** nomination(s) saved.",
                            ephemeral=True,
                        )
                else:
                    await interaction.followup.send(
                        "✅ Nomination thread is up to date with the last tally.",
                        ephemeral=True,
                    )

            except Exception as e:
                logger.error(f"end-nominations-start-vote: thread check failed: {e}")
                view = ConfirmProceedView()
                await interaction.followup.send(
                    f"⚠️ **Could not check thread for new messages:** {e}\n\n"
                    "Proceed with the existing nomination data anyway?",
                    view=view,
                    ephemeral=True,
                )
                proceed = await view.decision
                if not proceed:
                    await interaction.followup.send("❌ Aborted. No changes were made.", ephemeral=True)
                    return

        # ── Step 2: Preview nominations and ask admin to confirm ──
        results = self.db.get_nominations()

        heroes = set()
        encounters = set()

        for data in results:
            category = data.get('category', '').lower()
            set_name = data.get('set_name', data.get('nomineeName', 'Unknown'))
            creator_name = data.get('creatorName', '')
            display_name = f"{set_name} — {creator_name}" if creator_name else set_name
            if category == 'hero':
                heroes.add(display_name)
            elif category == 'encounter':
                encounters.add(display_name)

        heroes = sorted(heroes)
        encounters = sorted(encounters)

        embed = discord.Embed(title="Final Nominations", color=discord.Color.blue())
        embed.add_field(
            name="Heroes",
            value="\n".join(f"- {n}" for n in heroes) if heroes else "No hero nominations.",
            inline=False,
        )
        embed.add_field(
            name="Encounters",
            value="\n".join(f"- {n}" for n in encounters) if encounters else "No encounter nominations.",
            inline=False,
        )

        confirm_view = ConfirmProceedView()
        await interaction.followup.send(
            "**📋 Review the final nominations below.**\n\n"
            "Confirming will close nominations and open voting.",
            embed=embed,
            view=confirm_view,
            ephemeral=True,
        )
        proceed = await confirm_view.decision
        if not proceed:
            await interaction.followup.send("❌ Aborted. Nominations remain open.", ephemeral=True)
            return

        # ── Step 3: Send public announcement and transition state ──
        role = discord.utils.get(interaction.guild.roles, name="Community Seal Updates")
        role_mention = role.mention if role else "@Community Seal Updates"

        await interaction.followup.send(
            f"{role_mention} **📢 Nominations are now closed! Voting is now open!**\n\n"
            "Use the `/vote` command to cast your ballot. You may vote for up to 10 Heroes and 3 Encounters.",
            embed=embed,
            ephemeral=False,
        )

        metadata["state"] = "voting"
        self.db.update_cycle_metadata(metadata)
        self.bot.nomination_state = "voting"

    @app_commands.command(name="vote", description="Summon your personal ballot to vote on the current nominations.")
    async def vote(self, interaction: discord.Interaction):
        logger.info(f"User Action: vote initiated by {interaction.user.name} ({interaction.user.id})")
        await interaction.response.defer(ephemeral=True)
        
        # Ensure voting is actually open
        metadata = self.db.get_cycle_metadata()
        if metadata.get("state") != "voting":
            await interaction.followup.send("❌ **Invalid state.** Voting is not open right now.", ephemeral=True)
            return
            
        # Fetch current nominations
        results = self.db.get_nominations()
        
        heroes = set()
        encounters = set()
        
        for data in results:
            category = data.get('category', '').lower()
            set_name = data.get('set_name', data.get('nomineeName', 'Unknown'))
            creator_name = data.get('creatorName', '')
            
            display_name = f"{set_name} — {creator_name}" if creator_name else set_name
            
            if category == 'hero':
                heroes.add((set_name, display_name))
            elif category == 'encounter':
                encounters.add((set_name, display_name))
                
        if not heroes and not encounters:
            await interaction.followup.send("There are no active nominations to vote on.", ephemeral=True)
            return

        # Sort alphabetically by set_name
        heroes = sorted(list(heroes), key=lambda x: x[0])
        encounters = sorted(list(encounters), key=lambda x: x[0])
        
        hero_options = [discord.SelectOption(label=h[1][:100], value=h[0][:100]) for h in heroes]
        encounter_options = [discord.SelectOption(label=e[1][:100], value=e[0][:100]) for e in encounters]
        
        view = VotingView(self.db, hero_options, encounter_options)
        
        await interaction.followup.send(
            "**🗳️ Cast Your Votes!**\n"
            "Select up to **10 Heroes** and **3 Encounters**",
            view=view,
            ephemeral=True
        )



async def setup(bot):
    await bot.add_cog(Voting(bot))
