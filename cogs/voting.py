import discord
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore

class VotingView(discord.ui.View):
    def __init__(self, db, hero_options, encounter_options):
        super().__init__(timeout=None)
        self.db = db
        self.add_selects(encounter_options, hero_options)
    async def select_callback(self, interaction: discord.Interaction):
        # Acknowledge the interaction so Discord doesn't show "This interaction failed"
        await interaction.response.defer()
        
    def add_selects(self, encounter_options, hero_options):
        # Add Encounter Select (Max 2)
        if encounter_options:
            self.encounter_select = discord.ui.Select(
                placeholder="Select up to 2 encounters...",
                min_values=0,
                max_values=min(2, len(encounter_options)),
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
            
        # Validate totals
        if len(selected_heroes) > 10:
            await interaction.response.send_message(f"You selected {len(selected_heroes)} heroes, but the maximum is 10. Please adjust your selections.", ephemeral=True)
            return
        if len(selected_encounters) > 2:
             await interaction.response.send_message(f"You selected {len(selected_encounters)} encounters, but the maximum is 2. Please adjust your selections.", ephemeral=True)
             return
        if len(selected_heroes) == 0 and len(selected_encounters) == 0:
             await interaction.response.send_message("You didn't select anything to vote for! Please make a selection.", ephemeral=True)
             return

        # Record to Firestore
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        self.db.record_user_vote(user_id, user_name, selected_heroes, selected_encounters)
        
        await interaction.response.send_message(f"Thanks! Your votes have been recorded. You selected **{len(selected_heroes)}** Heroes and **{len(selected_encounters)}** Encounters.\n*(You can change your votes by submitting again)*", ephemeral=True)

class Voting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(name="start-voting", description="Admin: Switch the active cycle to the voting phase and alert users.")
    @app_commands.default_permissions(manage_messages=True)
    async def start_voting(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        # Update metadata state to voting
        metadata = self.db.get_cycle_metadata()
        metadata["state"] = "voting"
        self.db.update_cycle_metadata(metadata)
        self.bot.nomination_state = "voting"
        
        deleted_count = self.db.clear_votes()
        print(f"Deleted {deleted_count} votes from table.")
        
        # Build embed from current nominations
        results = self.db.get_nominations()
        
        heroes = set()
        encounters = set()
        
        for data in results:
            category = data.get('category', '').lower()
            nominee = data.get('nomineeName', 'Unknown')
            
            if category == 'hero':
                heroes.add(nominee)
            elif category == 'encounter':
                encounters.add(nominee)

        # Sort alphabetically
        heroes = sorted(list(heroes))
        encounters = sorted(list(encounters))

        embed = discord.Embed(title="Final Nominations", color=discord.Color.blue())
        
        hero_text = "\n".join(f"- {name}" for name in heroes) if heroes else "No hero nominations."
        embed.add_field(name="Heroes", value=hero_text, inline=False)
        
        encounter_text = "\n".join(f"- {name}" for name in encounters) if encounters else "No encounter nominations."
        embed.add_field(name="Encounters", value=encounter_text, inline=False)
        
        await interaction.followup.send(
            "**📢 Nominations are closed! Voting is now open!**\n\n"
            "Here are the final candidates for this cycle. Use the `/vote` command to cast your ballot. You may vote for up to 10 Heroes and 2 Encounters.",
            embed=embed
        )

    @app_commands.command(name="vote", description="Summon your personal ballot to vote on the current nominations.")
    async def vote(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Ensure voting is actually open
        if getattr(self.bot, 'nomination_state', 'off') != "voting":
            await interaction.followup.send("Voting for the current cycle is not open right now.", ephemeral=True)
            return
            
        # Fetch current nominations
        results = self.db.get_nominations()
        
        heroes = set()
        encounters = set()
        
        for data in results:
            category = data.get('category', '').lower()
            nominee = data.get('nomineeName', 'Unknown')
            
            if category == 'hero':
                heroes.add(nominee)
            elif category == 'encounter':
                encounters.add(nominee)
                
        if not heroes and not encounters:
            await interaction.followup.send("There are no active nominations to vote on.", ephemeral=True)
            return

        # Sort alphabetically
        heroes = sorted(list(heroes))
        encounters = sorted(list(encounters))
        
        hero_options = [discord.SelectOption(label=h[:100], value=h[:100]) for h in heroes]
        encounter_options = [discord.SelectOption(label=e[:100], value=e[:100]) for e in encounters]
        
        view = VotingView(self.db, hero_options, encounter_options)
        
        await interaction.followup.send(
            "**🗳️ Cast Your Votes!**\n"
            "Select up to **10 Heroes** and **2 Encounters** from the dropdowns below.\n"
            "When you are finished making your selections, click **Submit Votes**.",
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="tally-votes", description="Tally the current votes and display the winners.")
    @app_commands.default_permissions(manage_messages=True)
    async def tally_votes(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        results = self.db.get_all_votes()
        
        hero_counts = {}
        encounter_counts = {}
        total_voters = 0
        
        for data in results:
            total_voters += 1
            for hero in data.get('heroes', []):
                hero_counts[hero] = hero_counts.get(hero, 0) + 1
            for encounter in data.get('encounters', []):
                encounter_counts[encounter] = encounter_counts.get(encounter, 0) + 1
                
        if total_voters == 0:
            await interaction.followup.send("No votes have been cast yet.")
            return
            
        # Sort by vote count descending, then alphabetically for ties
        sorted_heroes = sorted(hero_counts.items(), key=lambda x: (-x[1], x[0]))
        sorted_encounters = sorted(encounter_counts.items(), key=lambda x: (-x[1], x[0]))
        
        embed = discord.Embed(title="Voting Results", color=discord.Color.gold(), description=f"Total Voters: **{total_voters}**")
        
        hero_text = ""
        for name, count in sorted_heroes:
            hero_text += f"**{count}** - {name}\n"
        if not hero_text:
            hero_text = "No hero votes."
            
        encounter_text = ""
        for name, count in sorted_encounters:
            encounter_text += f"**{count}** - {name}\n"
        if not encounter_text:
            encounter_text = "No encounter votes."
            
        def split_text(text):
            return [text[i:i+1024] for i in range(0, len(text), 1024)]
            
        hero_chunks = split_text(hero_text)
        for i, chunk in enumerate(hero_chunks):
            name_val = "Hero Votes" if i == 0 else "Hero Votes (Cont.)"
            embed.add_field(name=name_val, value=chunk, inline=False)
            
        encounter_chunks = split_text(encounter_text)
        for i, chunk in enumerate(encounter_chunks):
            name_val = "Encounter Votes" if i == 0 else "Encounter Votes (Cont.)"
            embed.add_field(name=name_val, value=chunk, inline=False)
            
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Voting(bot))
