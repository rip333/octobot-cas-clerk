import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from gemini_agent import GeminiAgent
from mcp_firestore import MCPFirestore


class CycleManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()
        self.agent = GeminiAgent()

    @app_commands.command(name="start-nominations", description="Create and monitor nominations thread for CAS cycle.")
    @app_commands.default_permissions(manage_channels=True)
    async def start_nominations(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        metadata = self.db.get_cycle_metadata()
        current_cycle_number = int(metadata.get("number"))
        
        deleted_count = self.db.clear_nominations()
        print(f"Deleted {deleted_count} nominations from table.")
        
        role = discord.utils.get(interaction.guild.roles, name="Community Seal Updates")
        role_mention = role.mention if role else "@Community Seal Updates"

        loop = asyncio.get_running_loop()
        intro_text = await loop.run_in_executor(
            None,
            self.agent.generate_cycle_intro,
            current_cycle_number,
            role_mention
        )
        
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel) and not isinstance(channel, discord.ForumChannel):
            await interaction.followup.send("This command must be used in a text or forum channel.", ephemeral=True)
            return

        thread_name = f"Cycle {current_cycle_number} - Nominations"
        
        thread = await channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            slowmode_delay=60,
            auto_archive_duration=10080
        )
        
        await thread.send(intro_text)
        
        new_metadata = {
            "number": current_cycle_number,
            "active": True,
            "nomination_thread_id": thread.id,
            "state": "nominations"
        }
        self.db.update_cycle_metadata(new_metadata)
        
        self.bot.nomination_thread_id = thread.id
        self.bot.nomination_state = "nominations"
        
        await interaction.delete_original_response()
        
async def setup(bot):
    await bot.add_cog(CycleManagement(bot))
