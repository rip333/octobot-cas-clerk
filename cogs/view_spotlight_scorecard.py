import discord
from discord.ext import commands
from discord import app_commands
from mcp_firestore import MCPFirestore
from google_services import GoogleServices
import logging

logger = logging.getLogger('octobot')


class ScorecardCycleSelectView(discord.ui.View):
    """First step: pick a cycle. Mirrors the pattern in view_reports.py."""
    def __init__(self, db):
        super().__init__(timeout=300)
        self.db = db

        cycles = self.db.get_all_cycles()
        current_cycle = self.db.get_current_cycle_number()
        self.selected_cycle = current_cycle

        options = []
        for c in cycles:
            is_current = (c == current_cycle)
            label = f"Cycle {c} (current)" if is_current else f"Cycle {c}"
            options.append(discord.SelectOption(label=label, value=str(c), default=is_current))

        if len(options) > 25:
            options = options[:25]

        self.select = discord.ui.Select(
            placeholder="Select a cycle to view scorecards...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

        self.submit_button = discord.ui.Button(label="Submit", style=discord.ButtonStyle.primary)
        self.submit_button.callback = self.submit_callback
        self.add_item(self.submit_button)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_cycle = int(self.select.values[0])
        await interaction.response.defer()

    async def submit_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cycle_number = self.selected_cycle

        cycle_forms_data = self.db.get_spotlight_roster(cycle_number)
        forms_list = cycle_forms_data.get("spotlights", [])

        # Filter to entries that actually have a Google Form link
        forms_with_links = [f for f in forms_list if f.get("form_id")]

        if not forms_with_links:
            await interaction.followup.send(f"No scorecard forms found for Cycle {cycle_number}.", ephemeral=True)
            return

        view = ScorecardSelectView(forms_with_links, interaction)
        await interaction.edit_original_response(content="Select a spotlight set below to view its scorecard results:", view=view)


class ScorecardSelectView(discord.ui.View):
    def __init__(self, forms_data, original_interaction):
        super().__init__(timeout=None)
        self.forms_data = forms_data
        self.original_interaction = original_interaction
        
        # Build options for each form
        options = []
        for form in forms_data:
            # title is usually: Cycle X - [Set Name] by [Creator]
            title = form.get("title", form.get("set_name", "Unknown Form"))
            options.append(discord.SelectOption(
                label=title[:100], 
                value=form.get("form_id"),
                description=f"Category: {form.get('category', 'Unknown')}"
            ))
            
        self.select = discord.ui.Select(
            placeholder="Select a Spotlight Set to view scores...",
            options=options
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        form_id = self.select.values[0]
        
        # Find the form title from the data
        form_title = "Scorecard Results"
        for f in self.forms_data:
            if f.get("form_id") == form_id:
                form_title = f.get("title", f.get("set_name", "Scorecard Results"))
                break
                
        try:
            gs = GoogleServices()
            
            # Fetch structure to get question titles
            form_structure = gs.get_form(form_id)
            items = form_structure.get("items", [])
            
            question_map = {}
            for item in items:
                q_item = item.get("questionItem")
                if q_item:
                    q = q_item.get("question", {})
                    if q and "questionId" in q:
                        title = item.get("title", "Unknown")
                        if "scaleQuestion" in q or "Approval" in title:
                            question_map[q["questionId"]] = title
                    
            # Fetch responses
            responses = gs.get_form_responses(form_id)
            if not responses:
                await interaction.followup.send(f"**{form_title}**\n\nNo responses have been submitted yet.", ephemeral=True)
                return
                
            # Tally scores
            # responses list -> dict of answers -> textAnswers -> answers [value]
            question_scores = {q_id: [] for q_id in question_map.keys()}
            approval_counts = {"Yes": 0, "No": 0, "Total": 0}
            
            for response in responses:
                answers = response.get("answers", {})
                for q_id, answer_data in answers.items():
                    if q_id in question_scores:
                        text_answers = answer_data.get("textAnswers", {}).get("answers", [])
                        for ta in text_answers:
                            val = ta.get("value", "").strip()
                            if not val:
                                continue
                            
                            # Check for Approval (Yes/No)
                            if "Approval" in question_map[q_id]:
                                if "Yes" in val:
                                    approval_counts["Yes"] += 1
                                elif "No" in val:
                                    approval_counts["No"] += 1
                                approval_counts["Total"] += 1
                                continue
                                
                            try:
                                # Many scorecard answers are "5", "4", or "3 - Average" etc.
                                # Try extracting the initial number if it starts with one.
                                num_val = float(val.split(" ")[0].split("-")[0].strip())
                                question_scores[q_id].append(num_val)
                            except ValueError:
                                pass # Non-numerical answer

            # Create embed
            embed = discord.Embed(title=f"📊 {form_title}", color=discord.Color.gold())
            embed.description = f"**Total Responses: {len(responses)}**\n"
            
            # Form averages and pass/fail logic
            total_avg_sum = 0
            total_questions = 0
            passing_scores = 0
            
            response_averages = []
            for response in responses:
                answers = response.get("answers", {})
                resp_scores = []
                for q_id, answer_data in answers.items():
                    if q_id in question_map and "Approval" not in question_map[q_id]:
                        text_answers = answer_data.get("textAnswers", {}).get("answers", [])
                        for ta in text_answers:
                            val = ta.get("value", "").strip()
                            if val:
                                try:
                                    num_val = float(val.split(" ")[0].split("-")[0].strip())
                                    resp_scores.append(num_val)
                                except ValueError:
                                    pass
                if resp_scores:
                    resp_avg = sum(resp_scores) / len(resp_scores)
                    response_averages.append(resp_avg)
                    if resp_avg >= 8.0:
                        passing_scores += 1
            
            for q_id, q_title in question_map.items():
                if "Approval" in q_title:
                    continue # handled separately
            
                scores = question_scores.get(q_id, [])
                if scores:
                    avg = sum(scores) / len(scores)
                    embed.add_field(name=q_title, value=f"**{avg:.2f}** / 10.0 (from {len(scores)} ratings)", inline=False)
                    total_avg_sum += avg
                    total_questions += 1
                else:
                    embed.add_field(name=q_title, value="No numerical ratings yet.", inline=False)
                    
            if total_questions > 0:
                overall_avg = total_avg_sum / total_questions
                embed.description += f"**Overall Average Score:** {overall_avg:.2f} / 10.0\n"
                
            if approval_counts["Total"] > 0:
                approval_pct = (approval_counts["Yes"] / approval_counts["Total"]) * 100
                embed.add_field(name="User 'Seal of Approval' Votes", value=f"**{approval_pct:.1f}%** (Yes: {approval_counts['Yes']} | No: {approval_counts['No']})", inline=False)

            num_responses = len(response_averages)
            if num_responses < 5:
                embed.add_field(name="Seal of Approval Status", value=f"**PENDING** - Requires at least 5 reviews (Currently {num_responses})", inline=False)
            else:
                pass_rate = (passing_scores / num_responses) * 100
                if pass_rate >= 70.0:
                    embed.add_field(name="Seal of Approval Status", value=f"✅ **PASS** - {pass_rate:.1f}% of reviews scored 8.0 or higher", inline=False)
                    embed.color = discord.Color.green()
                else:
                    embed.add_field(name="Seal of Approval Status", value=f"❌ **FAIL** - Only {pass_rate:.1f}% of reviews scored 8.0 or higher (Requires 70%)", inline=False)
                    embed.color = discord.Color.red()
                
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error fetching scorecard data: {e}", exc_info=True)
            await interaction.followup.send(f"Error fetching data from Google Forms API:\n{e}", ephemeral=True)

class ViewSpotlightScorecard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = MCPFirestore()

    @app_commands.command(name="view-spotlight-scorecard", description="View form responses and averages for a spotlight set's scorecard.")
    @app_commands.default_permissions(manage_messages=True)
    async def view_spotlight_scorecard(self, interaction: discord.Interaction):
        logger.info(f"Admin Action: view-spotlight-scorecard initiated by {interaction.user.name} ({interaction.user.id})")
        await interaction.response.defer(ephemeral=True)
        
        cycles = self.db.get_all_cycles()
        if not cycles:
            await interaction.followup.send("No cycles found in the database.", ephemeral=True)
            return

        view = ScorecardCycleSelectView(self.db)
        await interaction.followup.send("Select a cycle to view its spotlight scorecards:", view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ViewSpotlightScorecard(bot))

