import discord
from discord import app_commands
from discord.ext import commands
import logging
from mcp_firestore import MCPFirestore
from gemini_agent import GeminiAgent
import asyncio

logger = logging.getLogger('octobot')


async def run_nomination_tally(bot, db) -> dict:
    """
    Core AI nomination tally pipeline. Fetches thread history, runs Gemini,
    clears old nominations, saves new ones, and records a checkpoint.

    Returns:
        {"success": True,  "added_count": int, "last_message_id": str | None}
        {"success": False, "error": str}
    """
    metadata = db.get_cycle_metadata()
    thread_id = metadata.get("nomination_thread_id", 0)
    current_cycle_number = int(metadata.get("number", 100))

    if not thread_id:
        return {"success": False, "error": "No nomination thread ID found in the database."}

    try:
        channel = await bot.fetch_channel(int(thread_id))
    except discord.NotFound:
        return {"success": False, "error": "Nomination thread not found — it may have been deleted."}
    except Exception as e:
        return {"success": False, "error": f"Could not fetch thread: {e}"}

    rules_text = db.get_rules()
    hero_creators, encounter_creators = db.get_ineligible_creators(current_cycle_number)

    # Build thread history and track the channel's latest message ID as checkpoint.
    # We save the channel's last_message_id (not just the last non-bot message we
    # processed) so that the comparison in end-nominations-start-vote is correct even
    # when the most recent message in the thread is a bot message.
    messages_text = []
    async for msg in channel.history(limit=None, oldest_first=True):
        if msg.author == bot.user:
            continue
        messages_text.append(f"[{msg.author.name} (ID: {msg.author.id})]: {msg.content}")

    # Capture the channel's actual latest message ID for the checkpoint
    checkpoint_id = None
    async for msg in channel.history(limit=1):
        checkpoint_id = str(msg.id)

    history_str = "\n".join(messages_text)

    agent = GeminiAgent()
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            agent.process_thread,
            history_str,
            rules_text,
            hero_creators,
            encounter_creators,
        )
    except Exception as e:
        logger.error(f"run_nomination_tally: Gemini processing failed: {e}")
        return {"success": False, "error": f"AI processing failed: {e}"}

    if "error" in result:
        return {"success": False, "error": result["error"]}

    nominations = result.get("nominations", [])

    deleted_count = db.clear_nominations()
    logger.info(f"Tally: cleared {deleted_count} old nomination(s) before bulk add.")

    added_count = 0
    noms_by_user: dict = {}
    for nom in nominations:
        user_id = nom.get("nominator_id", "")
        if not user_id:
            continue
        if user_id not in noms_by_user:
            noms_by_user[user_id] = {
                "nominator_id": user_id,
                "nominator_name": nom.get("nominator_name", ""),
                "sets": [],
            }
        cat = nom.get("category", "")
        noms_by_user[user_id]["sets"].append({
            "set_name": nom.get("set_name", ""),
            "category": cat,
            "creatorName": nom.get("creator_name", ""),
            "creatorDiscordId": nom.get("creator_discord_id", ""),
            "ip_category": nom.get("ip_category", ""),
            "type": "villain" if cat == "Encounter" else "hero",
        })

    for user_id, user_data in noms_by_user.items():
        try:
            db.add_nomination_batch(
                cycle_number=current_cycle_number,
                nominator_id=user_data["nominator_id"],
                nominator_name=user_data["nominator_name"],
                sets=user_data["sets"],
            )
            added_count += len(user_data["sets"])
        except Exception as e:
            logger.error(f"run_nomination_tally: failed to save batch for {user_id}: {e}")

    # Persist the checkpoint so end-nominations-start-vote can detect new messages
    if checkpoint_id:
        db.update_cycle(current_cycle_number, {"last_tallied_message_id": checkpoint_id})
        logger.info(f"Tally checkpoint saved: message_id={checkpoint_id}")

    return {"success": True, "added_count": added_count, "last_message_id": checkpoint_id}


class ProcessNominations(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(
        name="tally-nominations",
        description="Process the entire nominations thread and tally the valid nominations."
    )
    @app_commands.default_permissions(manage_channels=True)
    async def tally_nominations(self, interaction: discord.Interaction):
        logger.info(f"Admin Action: tally-nominations initiated by {interaction.user.name}")
        await interaction.response.defer(ephemeral=True)

        metadata = self.db.get_cycle_metadata()

        if metadata.get("state") != "nominations":
            await interaction.followup.send(
                "❌ **Invalid state.** This command can only be run when the cycle is in the `nominations` state.",
                ephemeral=True,
            )
            return

        if not metadata.get("nomination_thread_id"):
            await interaction.followup.send(
                "❌ Could not find the nomination thread ID in the database.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "📚 Fetching thread history and processing nominations. This may take a moment…",
            ephemeral=True,
        )

        result = await run_nomination_tally(self.bot, self.db)

        if result["success"]:
            await interaction.followup.send(
                f"✅ Successfully processed thread. Extracted and saved **{result['added_count']}** nomination(s).",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"❌ Tally failed: {result['error']}",
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(ProcessNominations(bot))
