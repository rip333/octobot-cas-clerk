import discord
from discord.ext import commands
from discord import app_commands
from google.cloud import firestore

class CapReport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = firestore.Client(database="octobot-cas-db")

    @app_commands.command(name="cap-report", description="Generate a CAP Nomination Report")
    @app_commands.default_permissions(manage_messages=True)
    async def cap_report(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        query = self.db.collection('nominations').order_by('timestamp', direction=firestore.Query.DESCENDING)
        results = query.stream()
        
        heroes = []
        encounters = []
        
        for doc in results:
            data = doc.to_dict()
            category = data.get('category', '').lower()
            nominee = data.get('nomineeName', 'Unknown')
            
            if category == 'hero':
                heroes.append(nominee)
            elif category == 'encounter':
                encounters.append(nominee)
        
        embed = discord.Embed(title="CAP Nomination Report", color=discord.Color.blue())
        
        hero_text = "\n".join(f"- {name}" for name in heroes) if heroes else "No hero nominations."
        embed.add_field(name="Heroes", value=hero_text, inline=False)
        
        encounter_text = "\n".join(f"- {name}" for name in encounters) if encounters else "No encounter nominations."
        embed.add_field(name="Encounters", value=encounter_text, inline=False)
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CapReport(bot))
