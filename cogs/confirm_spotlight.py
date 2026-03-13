import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from mcp_firestore import MCPFirestore
from google_services import GoogleServices

def build_roster_embed(roster: list, title: str) -> discord.Embed:
    embed = discord.Embed(title=title, color=discord.Color.green())
    
    def format_entry(entry):
        base = f"- {entry['set_name']}"
        if entry.get('response_url'):
            base = f"{base} — [Form Link]({entry['response_url']})"
        return base
        
    marvel_heroes = [format_entry(h) for h in roster if h['category'] == 'Marvel']
    dc_heroes = [format_entry(h) for h in roster if h['category'] == 'DC']
    other_heroes = [format_entry(h) for h in roster if h['category'] == 'Other']
    wildcard_heroes = [format_entry(h) for h in roster if h['category'] == 'Wildcard']
    encounters = [format_entry(h) for h in roster if h['category'] == 'Encounter']
    
    embed.add_field(name="Marvel", value="\n".join(marvel_heroes) if marvel_heroes else "None", inline=False)
    embed.add_field(name="DC", value="\n".join(dc_heroes) if dc_heroes else "None", inline=False)
    embed.add_field(name="Other", value="\n".join(other_heroes) if other_heroes else "None", inline=False)
    embed.add_field(name="Wildcards", value="\n".join(wildcard_heroes) if wildcard_heroes else "None", inline=False)
    embed.add_field(name="Encounters", value="\n".join(encounters) if encounters else "None", inline=False)
    
    return embed


class TiebreakerView(discord.ui.View):
    def __init__(self, title: str, description: str, options: list, num_to_select: int):
        super().__init__(timeout=None)
        self.future = asyncio.Future()
        self.options = options
        self.num_to_select = num_to_select
        
        # Max values cannot exceed the number of options available
        max_vals = min(num_to_select, len(options))
        
        self.select = discord.ui.Select(
            placeholder=f"Select {num_to_select} option(s)...",
            min_values=max_vals,
            max_values=max_vals,
            options=[discord.SelectOption(label=opt[:100], value=opt) for opt in options]
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
        self.submit_btn = discord.ui.Button(label="Submit Tiebreaker", style=discord.ButtonStyle.success)
        self.submit_btn.callback = self.submit_callback
        self.add_item(self.submit_btn)

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

    async def submit_callback(self, interaction: discord.Interaction):
        if len(self.select.values) != self.num_to_select:
            await interaction.response.send_message(f"Please select exactly {self.num_to_select} option(s).", ephemeral=True)
            return
            
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="**✅ Tiebreaker Resolved**", view=self)
        self.future.set_result(self.select.values)


class FinalConfirmView(discord.ui.View):
    def __init__(self, db, cycle_number, roster, original_interaction):
        super().__init__(timeout=None)
        self.db = db
        self.cycle_number = cycle_number
        self.roster = roster
        self.original_interaction = original_interaction

    @discord.ui.button(label="Confirm & Save to Roster", style=discord.ButtonStyle.success)
    async def btn_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable buttons and show processing message
        for child in self.children:
            child.disabled = True
            
        await interaction.response.edit_message(
            content="**⏳ Processing roster and creating Google Forms... This may take a minute.**", 
            view=self
        )

        # 1. Create Google Forms for each set in the roster
        status_lines = ["**✅ Spotlight roster and Google Forms created successfully!**", ""]

        try:
            gs = GoogleServices()

            status_lines.append("**Scorecard Forms:**")
            for entry in self.roster:
                try:
                    creator_name = entry.get("creatorName", "Unknown")
                    form_result = gs.copy_form_for_set(entry["set_name"], self.cycle_number, creator_name)
                    
                    entry["form_id"] = form_result["form_id"]
                    entry["title"] = form_result["title"]
                    entry["edit_url"] = form_result["edit_url"]
                    entry["response_url"] = form_result["response_url"]
                    
                    status_lines.append(
                        f"- **{entry['set_name']}** ({entry['category']}):\n"
                        f"  [Form]({form_result['response_url']})"
                    )
                except Exception as form_err:
                    status_lines.append(f"- ⚠️ **{entry['set_name']}**: Form creation failed — {form_err}")

            # 2. Save the final roster containing all form data into the single Firestore source of truth.
            self.db.save_spotlight_roster(self.cycle_number, self.roster)

        except Exception as e:
            status_lines.append(f"\n⚠️ Error creating forms or saving roster: {e}")

        # 4. Generate Feedback Thread + Update Status
        form_output_block = "".join(status_lines)
        await interaction.edit_original_response(content=form_output_block, view=self)

        try:
            # Update state
            metadata = self.db.get_cycle_metadata()
            metadata["state"] = "reviewing"
            self.db.update_cycle_metadata(metadata)
            
            # Create Thread
            thread_name = f"Cycle {self.cycle_number} - Scorecards"
            channel = interaction.channel
            if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.ForumChannel):
                thread = await channel.create_thread(
                    name=thread_name,
                    type=discord.ChannelType.public_thread,
                    auto_archive_duration=10080
                )
                
                # Calculate end date: 6 weeks from now, at midnight
                from datetime import datetime, timedelta
                end_date = datetime.now() + timedelta(weeks=6)
                # Set to midnight (00:00:00) of that future day
                end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end_ts = int(end_date.timestamp())

                # Send welcome message
                welcome_msg = (
                    f"Congratulations on the confirmed Spotlight Sets for **Cycle {self.cycle_number}**!\n\n"
                    f"The review cycle ends on **<t:{end_ts}:F>** (<t:{end_ts}:R>).\n\n"
                    "Below are the links to submit your reviews for the confirmed Spotlight Sets:"
                )
                roster_embed = build_roster_embed(self.roster, f"Cycle {self.cycle_number} Scorecards")
                await thread.send(welcome_msg, embed=roster_embed)
                
        except Exception as e:
            await interaction.followup.send(f"⚠️ Error changing cycle to `reviewing` or creating thread: {e}", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="**Assignment Cancelled.**", view=self)


class ConfirmSpotlight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    async def resolve_tie(self, interaction, title, description, options, num_to_select):
        view = TiebreakerView(title, description, options, num_to_select)
        embed = discord.Embed(title=title, description=description, color=discord.Color.red())
        
        msg = await interaction.followup.send(embed=embed, view=view, wait=True, ephemeral=True)
        
        result = await view.future
        return result

    @app_commands.command(name="confirm-spotlight", description="Admin: Run the spotlight logic, resolve ties, and save the final roster.")
    @app_commands.default_permissions(manage_messages=True)
    async def confirm_spotlight(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        metadata = self.db.get_cycle_metadata()
        cycle_number = metadata.get("number", 0)
        
        results = self.db.get_all_votes()
        noms = self.db.get_nominations()
        
        nom_map = {}
        ip_cache = {}
        for data in noms:
            set_name = data.get('set_name', data.get('nomineeName', 'Unknown'))
            nom_map[set_name] = data
            ip_cache[set_name] = data.get('ip_category', 'Other')
            
        # Tally Raw Votes
        hero_counts = {}
        encounter_counts = {}
        
        for data in results:
            for hero_obj in data.get('heroes', []):
                if isinstance(hero_obj, dict):
                    set_name = hero_obj.get('set_name', hero_obj.get('nomineeName', 'Unknown'))
                else:
                    set_name = hero_obj.split(' — ')[0]
                hero_counts[set_name] = hero_counts.get(set_name, 0) + 1
                
            for encounter_obj in data.get('encounters', []):
                if isinstance(encounter_obj, dict):
                    set_name = encounter_obj.get('set_name', encounter_obj.get('nomineeName', 'Unknown'))
                else:
                    set_name = encounter_obj.split(' — ')[0]
                encounter_counts[set_name] = encounter_counts.get(set_name, 0) + 1
                
        # Group by Creator for Tiebreaking
        creator_heroes = {}
        creator_encounters = {}
        
        for item, count in hero_counts.items():
            nom_data = nom_map.get(item, {})
            creator = nom_data.get('creatorName', 'Unknown')
            if creator not in creator_heroes:
                creator_heroes[creator] = []
            creator_heroes[creator].append({'name': item, 'count': count})
            
        for item, count in encounter_counts.items():
            nom_data = nom_map.get(item, {})
            creator = nom_data.get('creatorName', 'Unknown')
            if creator not in creator_encounters:
                creator_encounters[creator] = []
            creator_encounters[creator].append({'name': item, 'count': count})
            
        # STEP 1: Creator Tiebreakers
        clean_heroes = []
        for creator, items in creator_heroes.items():
            if creator == 'Unknown':
                clean_heroes.extend(items)
                continue
                
            sorted_items = sorted(items, key=lambda x: -x['count'])
            max_votes = sorted_items[0]['count']
            tied = [i for i in sorted_items if i['count'] == max_votes]
            
            if len(tied) > 1:
                # Need tiebreaker
                options = [i['name'] for i in tied]
                res = await self.resolve_tie(
                    interaction,
                    f"Creator Tiebreaker: {creator} (Heroes)",
                    f"{creator} has multiple heroes tied at {max_votes} votes. Choose 1 to move forward.",
                    options,
                    1
                )
                winner_name = res[0]
                clean_heroes.append(next(i for i in tied if i['name'] == winner_name))
            else:
                clean_heroes.append(sorted_items[0])
                
        clean_encounters = []
        for creator, items in creator_encounters.items():
            if creator == 'Unknown':
                clean_encounters.extend(items)
                continue
                
            sorted_items = sorted(items, key=lambda x: -x['count'])
            max_votes = sorted_items[0]['count']
            tied = [i for i in sorted_items if i['count'] == max_votes]
            
            if len(tied) > 1:
                options = [i['name'] for i in tied]
                res = await self.resolve_tie(
                    interaction,
                    f"Creator Tiebreaker: {creator} (Encounters)",
                    f"{creator} has multiple encounters tied at {max_votes} votes. Choose 1 to move forward.",
                    options,
                    1
                )
                winner_name = res[0]
                clean_encounters.append(next(i for i in tied if i['name'] == winner_name))
            else:
                clean_encounters.append(sorted_items[0])

        # Resort clean pools
        clean_heroes = sorted(clean_heroes, key=lambda x: -x['count'])
        clean_encounters = sorted(clean_encounters, key=lambda x: -x['count'])
        
        final_roster = []
        
        def format_hero_data(name, category):
            data = {"set_name": name, "category": category}
            nom = nom_map.get(name, {})
            if nom.get('creatorName'):
                data['creatorName'] = nom['creatorName']
            if nom.get('creatorDiscordId'):
                data['creatorDiscordId'] = nom['creatorDiscordId']
            return data

        # STEP 2: Encounters
        needed_encounters = 2
        encounter_winners = []
        
        if len(clean_encounters) > 0:
            current_idx = 0
            while len(encounter_winners) < needed_encounters and current_idx < len(clean_encounters):
                current_votes = clean_encounters[current_idx]['count']
                tied = [e for e in clean_encounters[current_idx:] if e['count'] == current_votes]
                remaining_slots = needed_encounters - len(encounter_winners)
                
                if len(tied) <= remaining_slots:
                    for t in tied:
                        encounter_winners.append(t)
                    current_idx += len(tied)
                else:
                    options = [t['name'] for t in tied]
                    res = await self.resolve_tie(
                        interaction,
                        "Encounter Slot Tiebreaker",
                        f"There are {remaining_slots} Encounter slot(s) left, but {len(tied)} candidates are tied at {current_votes} votes.",
                        options,
                        remaining_slots
                    )
                    for r in res:
                        encounter_winners.append(next(t for t in tied if t['name'] == r))
                    break # All slots filled
            
        for e in encounter_winners:
            final_roster.append(format_hero_data(e['name'], "Encounter"))

        # STEP 3: Heroes (Quotas)
        quotas = {"Marvel": 2, "DC": 2, "Other": 2}
        pool = clean_heroes[:]
        
        for quota_cat, limit in quotas.items():
            cat_winners = []
            candidates = []
            for h in pool:
                ip = ip_cache.get(h['name'], "Other")
                if ip == quota_cat:
                    candidates.append(h)
                    
            if not candidates:
                continue
                
            current_idx = 0
            while len(cat_winners) < limit and current_idx < len(candidates):
                current_votes = candidates[current_idx]['count']
                tied = [c for c in candidates[current_idx:] if c['count'] == current_votes]
                remaining_slots = limit - len(cat_winners)
                
                if len(tied) <= remaining_slots:
                    for t in tied:
                        cat_winners.append(t)
                        pool.remove(t)
                    current_idx += len(tied)
                else:
                    options = [t['name'] for t in tied]
                    res = await self.resolve_tie(
                        interaction,
                        f"Hero Quota Tiebreaker: {quota_cat}",
                        f"There are {remaining_slots} {quota_cat} slot(s) left, but {len(tied)} candidates are tied at {current_votes} votes.",
                        options,
                        remaining_slots
                    )
                    for r in res:
                        winner = next(t for t in tied if t['name'] == r)
                        cat_winners.append(winner)
                        pool.remove(winner)
                    break 

            for h in cat_winners:
                final_roster.append(format_hero_data(h['name'], quota_cat))

        # STEP 4: Wildcards
        wildcard_slots = 2
        wildcard_winners = []
        
        current_idx = 0
        while len(wildcard_winners) < wildcard_slots and current_idx < len(pool):
            current_votes = pool[current_idx]['count']
            tied = [c for c in pool[current_idx:] if c['count'] == current_votes]
            remaining_slots = wildcard_slots - len(wildcard_winners)
            
            if len(tied) <= remaining_slots:
                for t in tied:
                    wildcard_winners.append(t)
                current_idx += len(tied)
            else:
                options = [t['name'] for t in tied]
                res = await self.resolve_tie(
                    interaction,
                    "Wildcard Slot Tiebreaker",
                    f"There are {remaining_slots} wildcard slot(s) left, but {len(tied)} candidates are tied at {current_votes} votes.",
                    options,
                    remaining_slots
                )
                for r in res:
                    wildcard_winners.append(next(t for t in tied if t['name'] == r))
                break
                
        for h in wildcard_winners:
            final_roster.append(format_hero_data(h['name'], 'Wildcard'))

        # STEP 5: Final Confirmation
        embed = build_roster_embed(final_roster, "Final Spotlight Roster Preview")
        
        view = FinalConfirmView(self.db, cycle_number, final_roster, interaction)
        await interaction.followup.send("Please verify the roster below and confirm to save to the database:", embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ConfirmSpotlight(bot))
