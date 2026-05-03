import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore
import asyncio
import logging
import re

logger = logging.getLogger('octobot')

# Only allow Google Drive URLs - refined to prevent most common injection/obfuscation attempts
DRIVE_URL_PATTERN = re.compile(
    r'^https://drive\.google\.com/[-a-zA-Z0-9@:%._\+~#=/?&]+$',
    re.IGNORECASE
)


class DriveModal(discord.ui.Modal, title="Set Google Drive Link"):
    drive_link = discord.ui.TextInput(
        label="Google Drive Link",
        placeholder="https://drive.google.com/drive/folders/...",
        style=discord.TextStyle.short,
        required=True,
        max_length=500,
    )

    def __init__(self, db: MCPFirestore, doc_id: str, set_name: str):
        super().__init__()
        self.db = db
        self.doc_id = doc_id
        self.set_name = set_name

    async def on_submit(self, interaction: discord.Interaction):
        link = self.drive_link.value.strip()

        # 1. Guard against path traversal in internal doc_id (defense in depth)
        if "/" in str(self.doc_id) or ".." in str(self.doc_id):
            logger.error(f"set-seal-drive-link: SECURITY ALERT - Malicious doc_id attempted: {self.doc_id}")
            await interaction.response.send_message("❌ System Error: Invalid document reference.", ephemeral=True)
            return

        # 2. Validate: must be a valid Google Drive URL structure
        if not DRIVE_URL_PATTERN.match(link):
            logger.warning(
                f"set-seal-drive-link: REJECTED invalid or suspicious URL from "
                f"{interaction.user.name}: '{link}'"
            )
            await interaction.response.send_message(
                "❌ Invalid link. Only standard `https://drive.google.com/...` URLs are accepted for security reasons.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await asyncio.to_thread(
                self.db.update_sealed_set_drive_link, self.doc_id, link
            )
            logger.info(
                f"set-seal-drive-link: '{self.set_name}' drive link updated by "
                f"{interaction.user.name} -> {link}"
            )
            await interaction.followup.send(
                f"✅ Drive link for **{self.set_name}** saved successfully.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"set-seal-drive-link: failed to update '{self.set_name}': {e}")
            await interaction.followup.send(
                f"❌ Failed to save drive link: {e}", ephemeral=True
            )


class SealSelectView(discord.ui.View):
    """A dropdown of all sealed sets. Selecting one opens the drive-link modal."""

    def __init__(self, db: MCPFirestore, sealed_sets: list):
        super().__init__(timeout=300)
        self.db = db

        # Build options (max 25 per select; paginate if needed — handled by splitting)
        options = []
        self.doc_map: dict[str, tuple[str, str]] = {}  # value -> (doc_id, set_name)

        for s in sealed_sets[:25]:
            doc_id = s["_doc_id"]
            set_name = s.get("set_name", "Unknown")
            cycle = s.get("cycle_number", "?")
            label = f"{set_name} (Cycle {cycle})"[:100]
            value = doc_id
            options.append(discord.SelectOption(label=label, value=value))
            self.doc_map[value] = (doc_id, set_name)

        self.select = discord.ui.Select(
            placeholder="Select a sealed set to update its drive link…",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        doc_id, set_name = self.doc_map[self.select.values[0]]
        modal = DriveModal(self.db, doc_id, set_name)
        await interaction.response.send_modal(modal)


class SetSealDriveLink(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(
        name="set-seal-drive-link",
        description="Admin: Set or update the Google Drive link for a sealed set."
    )
    @app_commands.default_permissions(manage_messages=True)
    async def set_seal_drive_link(self, interaction: discord.Interaction):
        logger.info(
            f"Admin Action: set-seal-drive-link initiated by "
            f"{interaction.user.name} ({interaction.user.id})"
        )
        await interaction.response.defer(ephemeral=True)

        sealed = await asyncio.to_thread(self.db.get_all_sealed_sets)

        if not sealed:
            await interaction.followup.send("No sealed sets found in the database.", ephemeral=True)
            return

        # Only show sets that are missing a drive link
        needs_link = [
            s for s in sealed
            if not s.get("google_drive") or str(s.get("google_drive")).strip().lower() in ["", "none", "unknown"]
        ]

        if not needs_link:
            await interaction.followup.send(
                "✅ All sealed sets already have a Google Drive link assigned!", ephemeral=True
            )
            return

        # Sort by name for easier browsing
        needs_link_sorted = sorted(needs_link, key=lambda x: x.get("set_name", "").lower())

        if len(needs_link_sorted) > 25:
            await interaction.followup.send(
                f"There are **{len(needs_link_sorted)}** sealed sets missing a drive link. "
                "Only the first 25 are shown in the dropdown.",
                ephemeral=True,
            )
            needs_link_sorted = needs_link_sorted[:25]

        view = SealSelectView(self.db, needs_link_sorted)
        await interaction.followup.send(
            f"**{len(needs_link_sorted)}** sealed set(s) are missing a Google Drive link. Select one to update:",
            view=view,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(SetSealDriveLink(bot))
