import os

import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import sys

# Configure standard logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger('octobot')
load_dotenv()
ALLOWED_GUILDS = [gid.strip() for gid in os.getenv("ALLOWED_GUILDS", "").split(",") if gid.strip()]

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True # Ensure guild events are tracked
client = commands.Bot(command_prefix="!", intents=intents)

import traceback

@client.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    from mcp_firestore import MCPFirestore
    
    db = MCPFirestore()
    
    # Format the traceback
    error_traceback = "".join(traceback.format_exception(type(error), error, error.__traceback__)) if hasattr(error, '__traceback__') else "".join(traceback.format_exception(error))
    print(f"Command Error: {error_traceback}")
    
    # Log to Firestore
    try:
        db.log_error(f"Command '{interaction.command.name if interaction.command else 'Unknown'}' failed by user {interaction.user.name}:\n{error_traceback}")
    except Exception as e:
        print(f"Failed to log error to Firestore: {e}")
        
    # Respond to user
    error_msg = "An error occurred while executing the command. The admin has been logged the details."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(error_msg, ephemeral=True)
        else:
            await interaction.response.send_message(error_msg, ephemeral=True)
    except discord.errors.NotFound:
        print("Interaction expired before error message could be sent.")

@client.event
async def setup_hook():
    await client.load_extension("cogs.view_reports")
    await client.load_extension("cogs.cycle_management")
    await client.load_extension("cogs.voting")
    await client.load_extension("cogs.assign_ip")
    await client.load_extension("cogs.confirm_spotlight")
    await client.load_extension("cogs.view_spotlight_scorecard")
    await client.load_extension("cogs.process_nominations")
    await client.load_extension("cogs.confirm_seals")
    await client.load_extension("cogs.view_seal_progress")
    await client.tree.sync()
    
    from mcp_firestore import MCPFirestore
    try:
        db = MCPFirestore()
        metadata = db.get_cycle_metadata()
        target_thread = metadata.get("nomination_thread_id", 0)
        client.nomination_thread_id = int(target_thread) if target_thread else 0
        client.nomination_state = metadata.get("state", "off")
        print(f"Loaded target thread ID from DB: {client.nomination_thread_id}, State: {client.nomination_state}")
    except Exception as e:
        print(f"Could not load cycle metadata on boot: {e}")

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    if ALLOWED_GUILDS:
        print(f"Server Lockdown active. Allowed Guilds: {ALLOWED_GUILDS}")

@client.event
async def on_guild_join(guild):
    if ALLOWED_GUILDS and str(guild.id) not in ALLOWED_GUILDS:
        print(f"Joined unauthorized guild: {guild.name} ({guild.id}). Leaving...")
        await guild.leave()

@client.tree.interaction_check
async def global_guild_check(interaction: discord.Interaction) -> bool:
    if not ALLOWED_GUILDS:
        return True
    if str(interaction.guild_id) in ALLOWED_GUILDS:
        return True
    
    await interaction.response.send_message("This bot is not authorized to run on this server.", ephemeral=True)
    return False

import time

import aiohttp
import asyncio



if __name__ == "__main__":
    client.run(os.getenv("DISCORD_TOKEN"))
