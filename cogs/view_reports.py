import discord
from discord import app_commands
from discord.ext import commands
from mcp_firestore import MCPFirestore
import logging

logger = logging.getLogger('octobot')

class CycleSelectView(discord.ui.View):
    def __init__(self, db, action_type):
        super().__init__(timeout=300)
        self.db = db
        self.action_type = action_type # "nominations" or "votes"
        
        cycles = self.db.get_all_cycles()
        current_cycle = self.db.get_current_cycle_number()
        self.selected_cycle = current_cycle  # default to current cycle
        
        options = []
        for c in cycles:
            is_current = (c == current_cycle)
            label = f"Cycle {c} (current)" if is_current else f"Cycle {c}"
            options.append(discord.SelectOption(label=label, value=str(c), default=is_current))
        
        # Discord limits select menus to 25 options. Just slice the latest 25 for now.
        if len(options) > 25:
            options = options[:25]
            
        self.select = discord.ui.Select(
            placeholder="Select a cycle to view...",
            min_values=1,
            max_values=1,
            options=options
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
        
        if self.action_type == "nominations":
            await self.show_nominations(interaction, cycle_number)
        elif self.action_type == "votes":
            await self.show_votes(interaction, cycle_number)
            
    async def show_nominations(self, interaction: discord.Interaction, cycle_number: int):
        noms = self.db.get_nominations(cycle_number)
        
        heroes = []
        encounters = []
        
        for data in noms:
            category = data.get('category', '').lower()
            set_name = data.get('set_name', data.get('nomineeName', 'Unknown'))
            creator_name = data.get('creatorName', '')
            display_name = f"{set_name} — {creator_name}" if creator_name else set_name
            
            if category == 'hero':
                heroes.append(display_name)
            elif category == 'encounter':
                encounters.append(display_name)
        
        embed = discord.Embed(title=f"Nomination Report - Cycle {cycle_number}", color=discord.Color.blue())
        
        hero_text = "\n".join(f"- {name}" for name in heroes) if heroes else "No hero nominations."
        embed.add_field(name="Heroes", value=hero_text, inline=False)
        
        encounter_text = "\n".join(f"- {name}" for name in encounters) if encounters else "No encounter nominations."
        embed.add_field(name="Encounters", value=encounter_text, inline=False)
        
        await interaction.edit_original_response(content=None, embed=embed, view=None)

    async def show_votes(self, interaction: discord.Interaction, cycle_number: int):
        results = self.db.get_all_votes(cycle_number)
        noms = self.db.get_nominations(cycle_number)
        
        nom_map = {}
        for data in noms:
            set_name = data.get('set_name', data.get('nomineeName', 'Unknown'))
            creator_name = data.get('creatorName', '')
            display_name = f"{set_name} — {creator_name}" if creator_name else set_name
            nom_map[set_name] = display_name
            
        hero_counts = {}
        encounter_counts = {}
        total_voters = 0
        
        for data in results:
            total_voters += 1
            for hero_obj in data.get('heroes', []):
                if isinstance(hero_obj, dict):
                    set_name = hero_obj.get('set_name', hero_obj.get('nomineeName', 'Unknown'))
                else:
                    set_name = hero_obj.split(' — ')[0]
                disp = nom_map.get(set_name, set_name)
                hero_counts[disp] = hero_counts.get(disp, 0) + 1
                
            for encounter_obj in data.get('encounters', []):
                if isinstance(encounter_obj, dict):
                    set_name = encounter_obj.get('set_name', encounter_obj.get('nomineeName', 'Unknown'))
                else:
                    set_name = encounter_obj.split(' — ')[0]
                disp = nom_map.get(set_name, set_name)
                encounter_counts[disp] = encounter_counts.get(disp, 0) + 1
                
        if total_voters == 0:
            await interaction.edit_original_response(content=f"No votes have been cast in Cycle {cycle_number}.", view=None)
            return
            
        sorted_heroes = sorted(hero_counts.items(), key=lambda x: (-x[1], x[0]))
        sorted_encounters = sorted(encounter_counts.items(), key=lambda x: (-x[1], x[0]))
            
        embed = discord.Embed(title=f"Voting Results - Cycle {cycle_number}", color=discord.Color.gold(), description=f"Total Voters: **{total_voters}**")
        
        def format_results(items):
            return "\n".join(f"**{count}** - {name}" for name, count in items)
            
        hero_text = format_results(sorted_heroes) if sorted_heroes else "No hero votes."
        encounter_text = format_results(sorted_encounters) if sorted_encounters else "No encounter votes."
            
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
            
        await interaction.edit_original_response(content=None, embed=embed, view=None)


class ViewReports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(name="view-nominations", description="View all nominations for a specific cycle.")
    @app_commands.default_permissions(manage_messages=True)
    async def view_nominations(self, interaction: discord.Interaction):
        logger.info(f"Admin Action: view-nominations initiated by {interaction.user.name} ({interaction.user.id})")
        await interaction.response.defer(ephemeral=True)
        
        cycles = self.db.get_all_cycles()
        if not cycles:
            await interaction.followup.send("No cycles found in the database.", ephemeral=True)
            return
            
        view = CycleSelectView(self.db, action_type="nominations")
        await interaction.followup.send("Please select a cycle to view its nominations:", view=view, ephemeral=True)

    @app_commands.command(name="view-votes", description="View voting results for a specific cycle.")
    @app_commands.default_permissions(manage_messages=True)
    async def view_votes(self, interaction: discord.Interaction):
        logger.info(f"Admin Action: view-votes initiated by {interaction.user.name} ({interaction.user.id})")
        await interaction.response.defer(ephemeral=True)
        
        cycles = self.db.get_all_cycles()
        if not cycles:
            await interaction.followup.send("No cycles found in the database.", ephemeral=True)
            return
            
        view = CycleSelectView(self.db, action_type="votes")
        await interaction.followup.send("Please select a cycle to view its voting results:", view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ViewReports(bot))
