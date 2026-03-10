import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore

class SpotlightAssignmentView(discord.ui.View):
    def __init__(self, db, sorted_heroes, cycle_number, interaction: discord.Interaction):
        super().__init__(timeout=None)
        self.db = db
        self.sorted_heroes = sorted_heroes
        self.cycle_number = cycle_number
        self.original_interaction = interaction
        self.current_index = 0
        self.roster = []
        
        # Quotas
        self.quotas = {
            "Marvel": 2,
            "DC": 2,
            "Other": 2,
            "Wildcards": 2
        }
        
    async def update_message(self, interaction: discord.Interaction):
        if self.current_index >= len(self.sorted_heroes) or len(self.roster) >= 8:
            await self.finish_assignment(interaction)
            return
            
        hero_name, vote_count = self.sorted_heroes[self.current_index]
        
        embed = discord.Embed(
            title="Spotlight Assignment", 
            description=f"Assigning hero {len(self.roster) + 1}/8.",
            color=discord.Color.purple()
        )
        embed.add_field(name="Current Hero", value=f"**{hero_name}** ({vote_count} votes)", inline=False)
        
        quota_text = (
            f"Marvel: {self.quotas['Marvel']} left\n"
            f"DC: {self.quotas['DC']} left\n"
            f"Other: {self.quotas['Other']} left\n"
            f"Wildcards: {self.quotas['Wildcards']} left"
        )
        embed.add_field(name="Remaining Quotas", value=quota_text, inline=False)
        
        roster_text = "\n".join([f"- {h['name']} ({h['category']})" for h in self.roster])
        if not roster_text:
            roster_text = "None yet."
        embed.add_field(name="Current Roster", value=roster_text, inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)

    async def assign_hero(self, interaction: discord.Interaction, category: str):
        hero_name, _ = self.sorted_heroes[self.current_index]
        assigned_category = category
        
        if self.quotas[category] > 0:
            self.quotas[category] -= 1
        elif self.quotas["Wildcards"] > 0:
            self.quotas["Wildcards"] -= 1
            assigned_category = "Wildcard"
        else:
            await interaction.response.send_message(f"No slots remaining for {category} or Wildcards!", ephemeral=True)
            return

        self.roster.append({
            "name": hero_name,
            "category": assigned_category
        })
        self.current_index += 1
        await self.update_message(interaction)

    @discord.ui.button(label="Marvel", style=discord.ButtonStyle.primary)
    async def btn_marvel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_hero(interaction, "Marvel")

    @discord.ui.button(label="DC", style=discord.ButtonStyle.primary)
    async def btn_dc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_hero(interaction, "DC")

    @discord.ui.button(label="Other", style=discord.ButtonStyle.primary)
    async def btn_other(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_hero(interaction, "Other")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def btn_skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index += 1
        await self.update_message(interaction)
        
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Spotlight assignment cancelled.", embed=None, view=self)

    async def finish_assignment(self, interaction: discord.Interaction):
        # Save to DB
        self.db.save_spotlight_roster(self.cycle_number, self.roster)
        
        for child in self.children:
            child.disabled = True
            
        embed = discord.Embed(title="Final Spotlight Roster", color=discord.Color.green())
        
        marvel_heroes = [h['name'] for h in self.roster if h['category'] == 'Marvel']
        dc_heroes = [h['name'] for h in self.roster if h['category'] == 'DC']
        other_heroes = [h['name'] for h in self.roster if h['category'] == 'Other']
        wildcard_heroes = [h['name'] for h in self.roster if h['category'] == 'Wildcard']
        
        embed.add_field(name="Marvel", value="\n".join(f"- {h}" for h in marvel_heroes) if marvel_heroes else "None", inline=False)
        embed.add_field(name="DC", value="\n".join(f"- {h}" for h in dc_heroes) if dc_heroes else "None", inline=False)
        embed.add_field(name="Other", value="\n".join(f"- {h}" for h in other_heroes) if other_heroes else "None", inline=False)
        embed.add_field(name="Wildcards", value="\n".join(f"- {h}" for h in wildcard_heroes) if wildcard_heroes else "None", inline=False)
        
        await interaction.response.edit_message(content="**Assignment Complete!** The roster has been saved.", embed=embed, view=self)


class SpotlightAssignment(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(name="assign-spotlight", description="Admin: Interactively assign top-voted heroes to the Spotlight roster.")
    @app_commands.default_permissions(manage_messages=True)
    async def assign_spotlight(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        # Get cycle number
        metadata = self.db.get_cycle_metadata()
        cycle_number = metadata.get("number", 0)
        
        # Tally Votes
        results = self.db.get_all_votes()
        
        hero_counts = {}
        for data in results:
            for hero in data.get('heroes', []):
                hero_counts[hero] = hero_counts.get(hero, 0) + 1
                
        if not hero_counts:
            await interaction.followup.send("No votes found to assign.", ephemeral=True)
            return
            
        # Sort desc by votes, asc by name
        sorted_heroes = sorted(hero_counts.items(), key=lambda x: (-x[1], x[0]))
        
        view = SpotlightAssignmentView(self.db, sorted_heroes, cycle_number, interaction)
        
        hero_name, vote_count = sorted_heroes[0]
        
        embed = discord.Embed(
            title="Spotlight Assignment", 
            description="Assigning hero 1/8.",
            color=discord.Color.purple()
        )
        embed.add_field(name="Current Hero", value=f"**{hero_name}** ({vote_count} votes)", inline=False)
        
        quota_text = (
            f"Marvel: {view.quotas['Marvel']} left\n"
            f"DC: {view.quotas['DC']} left\n"
            f"Other: {view.quotas['Other']} left\n"
            f"Wildcards: {view.quotas['Wildcards']} left"
        )
        embed.add_field(name="Remaining Quotas", value=quota_text, inline=False)
        embed.add_field(name="Current Roster", value="None yet.", inline=False)
        
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(SpotlightAssignment(bot))
