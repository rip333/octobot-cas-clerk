import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore
import asyncio
import logging
import time

logger = logging.getLogger('octobot')

class ViewSeals(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()
        # In-memory cache
        self._cached_categories = []
        self._cached_ips = []
        self._last_cache_update = 0
        # 30 days in seconds (60 * 60 * 24 * 30)
        self.cache_timeout = 2592000 

    @app_commands.default_permissions(manage_channels=True)
    async def update_autocomplete_cache(self, force: bool = False):
        """Refreshes the cache if expired or forced."""
        current_time = time.time()
        if force or not self._cached_categories or (current_time - self._last_cache_update > self.cache_timeout):
            try:
                env_prefix = "[TEST] " if self.db.collection_prefix else ""
                logger.info(f"{env_prefix}Refreshing Firestore autocomplete cache (Monthly/Manual)...")
                data = await asyncio.to_thread(self.db.get_all_sealed_sets)
                
                # Extract unique values and sort them
                self._cached_categories = sorted(list({str(s.get("category")) for s in data if s.get("category")}))
                self._cached_ips = sorted(list({str(s.get("ip_category")) for s in data if s.get("ip_category")}))
                
                self._last_cache_update = current_time
            except Exception as e:
                logger.error(f"Failed to refresh cache: {e}")

    @app_commands.command(
        name="view-seals",
        description="View sealed sets filtered by Category and IP Category."
    )
    @app_commands.describe(
        category_choice="The category (e.g., Hero, Encounter)",
        ip_choice="The IP Category (e.g., Marvel, DC)"
    )
    async def view_seals(self, interaction: discord.Interaction, category_choice: str, ip_choice: str):
        env_prefix = "[TEST] " if self.db.collection_prefix else ""
        logger.info(f"{env_prefix}User Action: view-seals requested by {interaction.user} (Filter: {category_choice}/{ip_choice})")
        await interaction.response.defer(ephemeral=True)

        # We still fetch the full list here to ensure the results are current, 
        # but the Autocomplete (the frequent part) uses the cache.
        all_sealed = await asyncio.to_thread(self.db.get_all_sealed_sets)
        
        filtered = [
            s for s in all_sealed 
            if str(s.get("category")).lower() == category_choice.lower() 
            and str(s.get("ip_category")).lower() == ip_choice.lower()
        ]

        if not filtered:
            logger.info(f"view-seals: No results found for {category_choice}/{ip_choice}")
            await interaction.followup.send(f"No sets found matching **{category_choice}** in **{ip_choice}**.", ephemeral=True)
            return

        logger.info(f"view-seals: Found {len(filtered)} sets for {category_choice}/{ip_choice}")
        filtered.sort(key=lambda x: x.get("set_name", "").lower())

        env_prefix = "[TEST] " if self.db.collection_prefix else ""
        lines = [f"## {env_prefix}🏅 {ip_choice}: {category_choice}s ({len(filtered)} total)\n"]
        for s in filtered:
            name, creator, drive = s.get("set_name", "Unknown"), s.get("creatorName", "Unknown"), s.get("google_drive", "")
            
            has_link = drive and str(drive).strip().lower() not in ["", "none", "unknown"]
            
            if has_link:
                lines.append(f"• **[{name}]({drive})** — {creator}")
            else:
                lines.append(f"• **{name}** — {creator} *(no drive link)*")

        # Standard chunking logic for Discord's 2000 character limit
        full_text = "\n".join(lines)
        if len(full_text) <= 2000:
            await interaction.followup.send(full_text, ephemeral=True)
        else:
            current_chunk = ""
            for line in lines:
                if len(current_chunk) + len(line) + 1 > 2000:
                    await interaction.followup.send(current_chunk, ephemeral=True)
                    current_chunk = line
                else:
                    current_chunk += ("\n" if current_chunk else "") + line
            if current_chunk:
                await interaction.followup.send(current_chunk, ephemeral=True)

    @app_commands.command(
        name="refresh-seals-cache",
        description="Manually force a refresh of the autocomplete dropdown options."
    )
    async def refresh_cache(self, interaction: discord.Interaction):
        """Allows admins to update dropdown options without waiting a month."""
        env_prefix = "[TEST] " if self.db.collection_prefix else ""
        logger.info(f"{env_prefix}Admin Action: refresh-seals-cache requested by {interaction.user}")
        await interaction.response.defer(ephemeral=True)
        await self.update_autocomplete_cache(force=True)
        await interaction.followup.send("Autocomplete cache successfully refreshed from Firestore!", ephemeral=True)

    # --- Autocomplete Handlers (Pulling from 1-month cache) ---

    @view_seals.autocomplete("category_choice")
    async def category_autocomplete(self, interaction: discord.Interaction, current: str):
        await self.update_autocomplete_cache()
        return [
            app_commands.Choice(name=c, value=c)
            for c in self._cached_categories if current.lower() in c.lower()
        ][:25]

    @view_seals.autocomplete("ip_choice")
    async def ip_autocomplete(self, interaction: discord.Interaction, current: str):
        await self.update_autocomplete_cache()
        return [
            app_commands.Choice(name=c, value=c)
            for c in self._cached_ips if current.lower() in c.lower()
        ][:25]

async def setup(bot):
    await bot.add_cog(ViewSeals(bot))