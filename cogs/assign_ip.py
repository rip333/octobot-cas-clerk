import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore
import logging

logger = logging.getLogger('octobot')

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
        
        # Disable 'Back' button if we are at the beginning
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label == "Back":
                child.disabled = (self.current_index == 0)
        
        await interaction.response.edit_message(embed=embed, view=self)

    async def assign_ip(self, interaction: discord.Interaction, ip_category: str):
        nominee = self.candidates[self.current_index]
        
        # Save to DB
        self.db.save_ip_assignment(self.cycle_number, nominee, ip_category)
        
        self.current_index += 1
        await self.update_message(interaction)

    @discord.ui.button(label="Marvel", style=discord.ButtonStyle.primary)
    async def btn_marvel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_ip(interaction, "MARVEL")

    @discord.ui.button(label="DC", style=discord.ButtonStyle.primary)
    async def btn_dc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_ip(interaction, "DC")

    @discord.ui.button(label="Other", style=discord.ButtonStyle.primary)
    async def btn_other(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.assign_ip(interaction, "OTHER")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, row=1)
    async def btn_skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index += 1
        await self.update_message(interaction)
        
    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_index > 0:
            self.current_index -= 1
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

    @app_commands.command(name="assign-ip", description="Admin: Label the IP (Marvel, DC, Other) for every nominated candidate.")
    @app_commands.default_permissions(manage_messages=True)
    async def assign_ip_cmd(self, interaction: discord.Interaction):
        logger.info(f"Admin Action: assign-ip initiated by {interaction.user.name} ({interaction.user.id})")
        await interaction.response.defer(ephemeral=True)
        
        metadata = self.db.get_cycle_metadata()
        if metadata.get("state") != "voting":
            await interaction.followup.send("❌ **Invalid state.** This command can only be run during the `voting` phase.", ephemeral=True)
            return
            
        if metadata.get("type") == "redemption":
            await interaction.followup.send("✅ **Not needed.** Redemption cycles do not require IP categorization.", ephemeral=True)
            return
        
        cycle_number = metadata.get("number", 0)
        
        # Get all candidates from nominations
        noms = self.db.get_nominations()
        
        nom_ips = {}
        for data in noms:
            set_name = data.get('set_name', data.get('nomineeName', 'Unknown'))
            # Gather LLM AI Guessed IPs
            ip_cat = data.get('ip_category')
            if ip_cat and ip_cat.upper() in ["MARVEL", "DC", "OTHER"]:
                nom_ips[set_name] = ip_cat.upper()
            
        unique_candidates = set()
        for data in noms:
            set_name = data.get('set_name', data.get('nomineeName', 'Unknown'))
            # If the AI did not automatically successfully guess the IP, add to candidates
            if set_name not in nom_ips:
                unique_candidates.add(set_name)
                
        # Sorted candidate list that strips out the already successfully guessed sets 
        candidates = sorted(list(unique_candidates))
        
        if not candidates:
            await interaction.followup.send("No votes found to assign.", ephemeral=True)
            return
            
        view = AssignIPView(self.db, candidates, cycle_number, interaction)
        
        # Before sending, let's manually trigger the update logic to sync button states
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.label == "Back":
                child.disabled = True
        
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
