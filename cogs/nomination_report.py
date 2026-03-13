import discord
from discord import app_commands
from discord.ext import commands
from mcp_firestore import MCPFirestore


class CapReport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(name="nomination-report", description="Generate a Nomination Report")
    @app_commands.default_permissions(manage_messages=True)
    async def nomination_report(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        metadata = self.db.get_cycle_metadata()
        if metadata.get("state") != "nominations":
            await interaction.followup.send("❌ **Invalid state.** This command can only be run during the `nominations` phase.", ephemeral=True)
            return
        
        noms = self.db.get_nominations()
        
        heroes = []
        encounters = []
        
        for data in noms:
            category = data.get('category', '').lower()
            set_name = data.get('set_name', data.get('nomineeName', 'Unknown'))
            
            if category == 'hero':
                heroes.append(set_name)
            elif category == 'encounter':
                encounters.append(set_name)
        
        embed = discord.Embed(title="Nomination Report", color=discord.Color.blue())
        
        hero_text = "\n".join(f"- {name}" for name in heroes) if heroes else "No hero nominations."
        embed.add_field(name="Heroes", value=hero_text, inline=False)
        
        encounter_text = "\n".join(f"- {name}" for name in encounters) if encounters else "No encounter nominations."
        embed.add_field(name="Encounters", value=encounter_text, inline=False)
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CapReport(bot))
