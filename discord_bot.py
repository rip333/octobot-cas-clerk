import discord
import os
from dotenv import load_dotenv

from discord.ext import commands

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="!", intents=intents)

@client.event
async def setup_hook():
    await client.load_extension("cogs.cap_report")
    await client.tree.sync()

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

import time
import aiohttp

user_last_msg_time = {}

import asyncio
from gemini_agent import GeminiAgent

agent = GeminiAgent()

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Thread ID check
    target_thread = int(os.getenv("NOMINATION_THREAD_ID", "0"))
    if target_thread and getattr(message.channel, 'id', 0) != target_thread:
        return

    # 2s Rate Limit
    now = time.time()
    last_time = user_last_msg_time.get(message.author.id, 0)
    if now - last_time < 2.0:
        print(f"Rate limited {message.author.name}")
        return
    user_last_msg_time[message.author.id] = now

    print(f"Processing message from {message.author}: {message.content}")
    
    # Run the Gemini Agent process in an executor so we don't block the async event loop
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, 
            agent.process_message, 
            message.content, 
            str(message.author.id), 
            message.author.name
        )
        print(f"Gemini Outcome: {result.get('gemini_response')}")
    except Exception as e:
        print(f"Failed to process via Gemini: {e}")

if __name__ == "__main__":
    client.run(os.getenv("DISCORD_TOKEN"))
