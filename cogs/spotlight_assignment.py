import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore

class SpotlightAssignmentView(discord.ui.View):
    def __init__(self, db, sorted_heroes, cycle_number, interaction: discord.Interaction, top_encounters=None, nom_map=None):
        super().__init__(timeout=None)
        self.db = db
        self.sorted_heroes = sorted_heroes
        self.cycle_number = cycle_number
        self.original_interaction = interaction
        self.current_index = 0
        self.roster = []
        self.top_encounters = top_encounters or []
        self.nom_map = nom_map or {}
        
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

        hero_data = {
            "name": hero_name,
            "category": assigned_category
        }
        nom = self.nom_map.get(hero_name, {})
        if nom.get('creatorName'):
            hero_data['creatorName'] = nom['creatorName']
        if nom.get('creatorDiscordId'):
            hero_data['creatorDiscordId'] = nom['creatorDiscordId']

        self.roster.append(hero_data)
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
        # Auto-add the Top 2 encounters to the roster if they exist
        for enc_name, _ in self.top_encounters:
            enc_data = {
                "name": enc_name,
                "category": "Encounter"
            }
            nom = self.nom_map.get(enc_name, {})
            if nom.get('creatorName'):
                enc_data['creatorName'] = nom['creatorName']
            if nom.get('creatorDiscordId'):
                enc_data['creatorDiscordId'] = nom['creatorDiscordId']
            self.roster.append(enc_data)

        # Save to DB
        self.db.save_spotlight_roster(self.cycle_number, self.roster)
        
        for child in self.children:
            child.disabled = True
            
        embed = discord.Embed(title="Final Spotlight Roster", color=discord.Color.green())
        
        marvel_heroes = [h['name'] for h in self.roster if h['category'] == 'Marvel']
        dc_heroes = [h['name'] for h in self.roster if h['category'] == 'DC']
        other_heroes = [h['name'] for h in self.roster if h['category'] == 'Other']
        wildcard_heroes = [h['name'] for h in self.roster if h['category'] == 'Wildcard']
        encounters = [h['name'] for h in self.roster if h['category'] == 'Encounter']
        
        embed.add_field(name="Marvel", value="\n".join(f"- {h}" for h in marvel_heroes) if marvel_heroes else "None", inline=False)
        embed.add_field(name="DC", value="\n".join(f"- {h}" for h in dc_heroes) if dc_heroes else "None", inline=False)
        embed.add_field(name="Other", value="\n".join(f"- {h}" for h in other_heroes) if other_heroes else "None", inline=False)
        embed.add_field(name="Wildcards", value="\n".join(f"- {h}" for h in wildcard_heroes) if wildcard_heroes else "None", inline=False)
        embed.add_field(name="Encounters", value="\n".join(f"- {h}" for h in encounters) if encounters else "None", inline=False)
        
        await interaction.response.edit_message(content="**Spotlight Sets saved to table**", embed=embed, view=self)


class SpotlightAssignment(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(name="assign-spotlight", description="Admin: Interactively assign top-voted heroes to the Spotlight roster.")
    @app_commands.default_permissions(manage_messages=True)
    async def assign_spotlight(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Get cycle number
        metadata = self.db.get_cycle_metadata()
        cycle_number = metadata.get("number", 0)
        
        from cogs.voting import get_filtered_results
        filtered = get_filtered_results(self.db)
        
        sorted_heroes = filtered['heroes']
        top_encounters = filtered['encounters'][:2]
        nom_map = filtered['nom_map']
        
        if not sorted_heroes:
            await interaction.followup.send("No votes found to assign.", ephemeral=True)
            return
            
        view = SpotlightAssignmentView(self.db, sorted_heroes, cycle_number, interaction, top_encounters, nom_map)
        
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
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(SpotlightAssignment(bot))
