import discord
from discord import app_commands
from discord.ext import commands

from mcp_firestore import MCPFirestore


class CycleManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(name="start-nominations", description="Create and monitor nominations and voting thread for CAS cycle.")
    @app_commands.default_permissions(manage_channels=True)
    async def start_nominations(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        metadata = self.db.get_cycle_metadata()
        current_state = metadata.get("state", "off")
        
        if current_state != "planning":
            await interaction.followup.send("❌ **Invalid state.** This command can only be run when the cycle is in the `planning` state.", ephemeral=True)
            return
        
        current_cycle_number = int(metadata.get("number"))
        
        deleted_count = self.db.clear_nominations()
        print(f"Deleted {deleted_count} nominations from table.")
        
        role = discord.utils.get(interaction.guild.roles, name="Community Seal Updates")
        role_mention = role.mention if role else "@Community Seal Updates"

        intro_text = (
            f"Hey {role_mention}!\n\n"
            f"Welcome to Cycle {current_cycle_number}! "
            f"This thread will be used for nominations and voting for Cycle {current_cycle_number}!\n\n"
            "**Rules**\n"
            "\u2022 First, we will have nominations. You may nominate 2 Hero sets and 1 Encounter set. "
            "Please include \"hero\" or \"encounter\" in your nomination to specify which type of set you are nominating."
            "\u2022 After nominations close (in about a week), we will close nominations and begin voting."
        )
        
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel) and not isinstance(channel, discord.ForumChannel):
            await interaction.followup.send("This command must be used in a text or forum channel.", ephemeral=True)
            return

        thread_name = f"Cycle {current_cycle_number} - Nominations and Voting"
        
        thread = await channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            slowmode_delay=60,
            auto_archive_duration=10080
        )
        
        await thread.send(intro_text)
        
        self.db.begin_cycle(thread.id)
        self.bot.nomination_thread_id = thread.id
        self.bot.nomination_state = "nominations"
        
        await interaction.delete_original_response()
        
async def setup(bot):
    await bot.add_cog(CycleManagement(bot))
