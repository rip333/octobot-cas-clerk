import discord
from discord import app_commands
from discord.ext import commands

from mcp_firestore import MCPFirestore
import logging

logger = logging.getLogger('octobot')

class StartCycleModal(discord.ui.Modal, title='Start Cycle'):
    def __init__(self, db, bot, default_cycle_num, channel):
        super().__init__()
        self.db = db
        self.bot = bot
        self.channel = channel
        self.default_cycle_num = default_cycle_num
        
        self.cycle_number = discord.ui.TextInput(
            label='Cycle Number',
            style=discord.TextStyle.short,
            default=str(default_cycle_num),
            required=True
        )
        self.add_item(self.cycle_number)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            chosen_cycle = int(self.cycle_number.value)
        except ValueError:
            await interaction.followup.send("❌ Please enter a valid integer for the cycle number.", ephemeral=True)
            return

        if chosen_cycle != self.default_cycle_num:
            # Update the current_cycle source of truth in Firestore
            self.db.db.collection(self.db.collection_prefix + 'cycles').document('current_cycle').set({"number": chosen_cycle})
            
            # Initialize the base document for the new cycle
            default_cycle = {
                "number": chosen_cycle,
                "state": "planning",
                "is_active": True,
                "nomination_thread_id": 0,
                "spotlights": []
            }
            self.db.db.collection(self.db.collection_prefix + 'cycles').document(str(chosen_cycle)).set(default_cycle)

        # Proceed with start logic using chosen_cycle
        hero_creators, encounter_creators = self.db.get_ineligible_creators(chosen_cycle)
        
        ineligible_text = []
        if hero_creators:
            ineligible_text.append(f"**Heroes**: {', '.join(sorted(hero_creators))}")
        if encounter_creators:
            ineligible_text.append(f"**Encounters**: {', '.join(sorted(encounter_creators))}")
            
        ineligible_section = ""
        if ineligible_text:
            ineligible_str = "\n".join([f"- {item}" for item in ineligible_text])
            ineligible_section = f"The following creators are ineligible for nomination:\n{ineligible_str}\n\n"
            
        role = discord.utils.get(interaction.guild.roles, name="Community Seal Updates")
        role_mention = role.mention if role else "@Community Seal Updates"

        intro_text = (
            f"Hey {role_mention}!\n\n"
            f"Welcome to Cycle {chosen_cycle}! "
            f"This thread will be used for nominations and voting for Cycle {chosen_cycle}!\n\n"
            "**Rules**\n"
            "NOMINATIONS:\n\nYou may nominate 2 Hero sets and 1 Encounter (villain or leader) set.\n\n"
            "Please include \"hero\" or \"encounter\" in your nomination to specify which type of set you are nominating.\n\n"
            "You may not nominate yourself.\n\n"
            f"{ineligible_section}"
            "After nominations close (in about a week), we will close nominations and begin voting.\n\n"
        )

        thread_name = f"Cycle {chosen_cycle} - Nominations and Voting"

        thread = await self.channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            slowmode_delay=60,
            auto_archive_duration=10080
        )
        
        await thread.send(intro_text)
        
        # Only update the DB and wipe the table if the Discord operations succeeded
        deleted_count = self.db.clear_nominations()
        print(f"Deleted {deleted_count} nominations from table.")
        
        self.db.begin_cycle(thread.id)
        self.bot.nomination_thread_id = thread.id
        self.bot.nomination_state = "nominations"
        
        await interaction.followup.send(f"✅ Started Cycle {chosen_cycle} in thread: {thread.mention}", ephemeral=True)


class CycleManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(name="start-cycle", description="Start a new CAS cycle and create the nominations thread.")
    @app_commands.default_permissions(manage_channels=True)
    async def start_cycle(self, interaction: discord.Interaction):
        logger.info(f"Admin Action: start-cycle initiated by {interaction.user.name} ({interaction.user.id})")
        
        # We must NOT defer here if we intend to show a modal
        metadata = self.db.get_cycle_metadata()
        current_state = metadata.get("state", "off")
        
        if current_state != "planning":
            await interaction.response.send_message("❌ **Invalid state.** This command can only be run when the cycle is in the `planning` state.", ephemeral=True)
            return
            
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
            await interaction.response.send_message("❌ **Invalid channel.** This command must be used in a text or forum channel to create the Nominations thread.", ephemeral=True)
            return
        
        current_cycle_number = int(metadata.get("number"))
        
        modal = StartCycleModal(self.db, self.bot, current_cycle_number, channel)
        await interaction.response.send_modal(modal)
        
async def setup(bot):
    await bot.add_cog(CycleManagement(bot))
