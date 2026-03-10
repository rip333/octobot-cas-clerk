import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore

class AssignIPView(discord.ui.View):
    def __init__(self, db, candidates, cycle_number, interaction: discord.Interaction):
        super().__init__(timeout=None)
        self.db = db
        self.candidates = candidates
        self.cycle_number = cycle_number
        self.original_interaction = interaction
        self.current_index = 0
        
    async def update_message(self, interaction: discord.Interaction):
        if self.current_index >= len(self.candidates):
            await self.finish_assignment(interaction)
            return
            
        nominee = self.candidates[self.current_index]
        
        embed = discord.Embed(
            title="IP Category Assignment", 
            description=f"Assigning IP for candidate {self.current_index + 1}/{len(self.candidates)}.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Current Candidate", value=f"**{nominee}**", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)

    async def assign_ip(self, interaction: discord.Interaction, ip_category: str):
        nominee = self.candidates[self.current_index]
        
        # Save to DB
        self.db.save_ip_assignment(self.cycle_number, nominee, ip_category)
        
        self.current_index += 1
        await self.update_message(interaction)

    @discord.ui.button(label="Marvel", style=discord.ButtonStyle.primary)
    async def btn_marvel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_ip(interaction, "Marvel")

    @discord.ui.button(label="DC", style=discord.ButtonStyle.primary)
    async def btn_dc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_ip(interaction, "DC")

    @discord.ui.button(label="Other", style=discord.ButtonStyle.primary)
    async def btn_other(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_ip(interaction, "Other")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def btn_skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index += 1
        await self.update_message(interaction)
        
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="IP assignment cancelled.", embed=None, view=self)

    async def finish_assignment(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(content="**IP Assignment Complete!** All cached assignments are ready for `/confirm-spotlight`.", embed=None, view=self)


class AssignIP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(name="assign-ip", description="Admin: Label the IP (Marvel, DC, Other) for every voted candidate.")
    @app_commands.default_permissions(manage_messages=True)
    async def assign_ip_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        metadata = self.db.get_cycle_metadata()
        cycle_number = metadata.get("number", 0)
        
        # Get all voted candidates
        results = self.db.get_all_votes()
        noms = self.db.get_nominations()
        
        nom_map = {}
        for data in noms:
            nominee = data.get('nomineeName', 'Unknown')
            creator_name = data.get('creatorName', '')
            display_name = f"{nominee} — {creator_name}" if creator_name else nominee
            nom_map[nominee] = display_name
            
        unique_candidates = set()
        for data in results:
            for hero in data.get('heroes', []):
                disp = nom_map.get(hero.split(" — ")[0], hero)
                unique_candidates.add(disp)
            for enc in data.get('encounters', []):
                disp = nom_map.get(enc.split(" — ")[0], enc)
                unique_candidates.add(disp)
                
        # Also check existing assignments to avoid duplicate work? Let's assign all for clarity, or filter existing.
        # We will present all of them. 
        candidates = sorted(list(unique_candidates))
        
        if not candidates:
            await interaction.followup.send("No votes found to assign.", ephemeral=True)
            return
            
        view = AssignIPView(self.db, candidates, cycle_number, interaction)
        
        nominee = candidates[0]
        
        embed = discord.Embed(
            title="IP Category Assignment", 
            description=f"Assigning IP for candidate 1/{len(candidates)}.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Current Candidate", value=f"**{nominee}**", inline=False)
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AssignIP(bot))
