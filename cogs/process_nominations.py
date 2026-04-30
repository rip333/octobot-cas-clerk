import discord
from discord import app_commands
from discord.ext import commands
import logging
from mcp_firestore import MCPFirestore
from gemini_agent import GeminiAgent
import asyncio

logger = logging.getLogger('octobot')

class ProcessNominations(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()
        self.agent = GeminiAgent()

    @app_commands.command(name="tally-nominations", description="Process the entire nominations thread and tally the valid nominations.")
    @app_commands.default_permissions(manage_channels=True)
    async def tally_nominations(self, interaction: discord.Interaction):
        logger.info(f"Admin Action: tally-nominations initiated by {interaction.user.name}")
        await interaction.response.defer(ephemeral=True)
        
        metadata = self.db.get_cycle_metadata()
        current_state = metadata.get("state", "off")
        thread_id = metadata.get("nomination_thread_id", 0)
        
        if current_state != "nominations":
            await interaction.followup.send("❌ **Invalid state.** This command can only be run when the cycle is in the `nominations` state.", ephemeral=True)
            return
            
        if not thread_id:
            await interaction.followup.send("❌ Could not find the nomination thread ID in the database.", ephemeral=True)
            return
            
        try:
            channel = await self.bot.fetch_channel(int(thread_id))
        except discord.NotFound:
            await interaction.followup.send("❌ Could not find the nomination thread. It may have been deleted.", ephemeral=True)
            return

        await interaction.followup.send("📚 Fetching thread history and processing nominations. This may take a moment...", ephemeral=True)

        # Get rules and ineligible creators
        rules_text = self.db.get_rules()
        current_cycle_number = int(metadata.get("number", 100))
        hero_creators, encounter_creators = self.db.get_ineligible_creators(current_cycle_number)
        
        # Build thread history
        messages_text = []
        async for msg in channel.history(limit=None, oldest_first=True):
            if msg.author == self.bot.user:
                continue
            messages_text.append(f"[{msg.author.name} (ID: {msg.author.id})]: {msg.content}")
            
        history_str = "\n".join(messages_text)

        # Process with Gemini
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self.agent.process_thread,
                history_str,
                rules_text,
                hero_creators,
                encounter_creators
            )
        except Exception as e:
            logger.error(f"Failed to process via Gemini: {e}")
            await interaction.followup.send(f"❌ Error during AI processing: {e}", ephemeral=True)
            return

        if "error" in result:
            await interaction.followup.send(f"❌ AI Processing Error: {result['error']}", ephemeral=True)
            return

        nominations = result.get("nominations", [])
        
        # Clear existing nominations before adding the new tallied ones
        deleted_count = self.db.clear_nominations()
        logger.info(f"Cleared {deleted_count} old nominations before bulk add.")

        added_count = 0
        noms_by_user = {}
        for nom in nominations:
            user_id = nom.get("nominator_id", "")
            if not user_id: continue
            
            if user_id not in noms_by_user:
                noms_by_user[user_id] = {
                    "nominator_id": user_id,
                    "nominator_name": nom.get("nominator_name", ""),
                    "sets": []
                }
                
            cat = nom.get("category", "")
            noms_by_user[user_id]["sets"].append({
                "set_name": nom.get("set_name", ""),
                "category": cat,
                "creatorName": nom.get("creator_name", ""),
                "creatorDiscordId": nom.get("creator_discord_id", ""),
                "ip_category": nom.get("ip_category", ""),
                "type": "villain" if cat == "Encounter" else "hero"
            })
            
        for user_id, user_data in noms_by_user.items():
            try:
                self.db.add_nomination_batch(
                    cycle_number=current_cycle_number,
                    nominator_id=user_data["nominator_id"],
                    nominator_name=user_data["nominator_name"],
                    sets=user_data["sets"]
                )
                added_count += len(user_data["sets"])
            except Exception as e:
                logger.error(f"Failed to add nomination batch for {user_id}: {e}")
                
        await interaction.followup.send(f"✅ Successfully processed thread. Extracted and saved {added_count} nominations.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ProcessNominations(bot))
