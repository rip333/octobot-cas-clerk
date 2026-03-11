import os

from google import genai

from mcp_firestore import MCPFirestore


class GeminiAgent:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.firestore_tool = MCPFirestore()

    def process_message(self, message_text: str, author_id: str, author_name: str) -> dict:
        """
        Use Gemini Flash Latest to extract intent and invoke MCPFirestore tools.
        """
        if len(message_text) > 1000:
            message_text = message_text[:1000] + "... (truncated)"
            
        system_instruction = f"""
        You are the CAP Silent Secretary, processing nominations in a Marvel Champions LCG Discord thread.

        This community loves and creates custom content for a superhero card game and wants to nominate the best sets.
        Hero sets are played by players in a cooperative game against an autopiloted encounter set.  Each set contains multiple cards.

        Determine what action the user wants to perform regarding nominations. 
        When adding nominations, format the nominee name using context clues given the sources of media (e.g. "captain america" becomes "Captain America" or "spiderman" becomes "Spider-Man").  
        Current User: {author_name} (ID: {author_id})
        Message: "{message_text}"
        
        You have tools to:
        - `get_rules()`: Read the nomination rules.
        - `get_nominations()`: List current nominations.
        - `add_nomination(nominator_id="...", nominator_name="...", nominee_name="...", category="...", creator_name="...", creator_discord_id="...", ip_category="...")`: Add a nomination. category must be EXACTLY "HERO" or "ENCOUNTER". nominator_id is the current user's ID and nominator_name is the current user's name. Extract `creator_name` and an optional `creator_discord_id` (if they mention a user like <@12345678>) from the nomination. If a discord ID mention is present, `creator_discord_id` should hold the raw mention string. `creator_name` should be their clean display name without the @ symbol. `ip_category` should be your best guess of the IP ("Marvel", "DC", or "Other") based on superhero media knowledge. If ambiguous or unknown, pass an empty string "".
        - `remove_nomination(nomination_id="...")`: Remove a nomination by its document ID.
        - `log_error(text="...")`: Log a nomination error with a reason.

        Analyze the user's intent and use the necessary tools. Read the rules if the user's message is on topic for nominations.
        """
        
        from google.genai import types
        
        actions_taken = []
        
        def get_rules_tool():
            """Read the nomination rules."""
            actions_taken.append({"action": "get_rules"})
            return self.firestore_tool.get_rules()
            
        def get_nominations_tool():
            """List current nominations."""
            actions_taken.append({"action": "get_nominations"})
            return self.firestore_tool.get_nominations()
            
        def add_nomination_tool(nominator_id: str, nominator_name: str, nominee_name: str, category: str, creator_name: str = "", creator_discord_id: str = "", ip_category: str = ""):
            """Add a nomination. category must be EXACTLY "HERO" or "ENCOUNTER"."""
            actions_taken.append({"action": "add_nomination", "nominee": nominee_name, "category": category})
            return self.firestore_tool.add_nomination(nominator_id, nominator_name, nominee_name, category, creator_name, creator_discord_id, ip_category)
            
        def remove_nomination_tool(nomination_id: str):
            """Remove a nomination by its document ID."""
            actions_taken.append({"action": "remove_nomination", "nomination_id": nomination_id})
            return self.firestore_tool.remove_nomination(nomination_id)
            
        def log_error_tool(text: str):
            """Log a nomination error with a reason."""
            actions_taken.append({"action": "log_error", "text": text})
            return self.firestore_tool.log_error(text)
        
        response = self.client.models.generate_content(
            model='gemini-flash-latest',
            contents=system_instruction,
            config=types.GenerateContentConfig(
                tools=[
                    get_rules_tool,
                    get_nominations_tool,
                    add_nomination_tool,
                    remove_nomination_tool,
                    log_error_tool
                ],
                temperature=0.1,
            )
        )
        
        return {"status": "success", "gemini_response": response.text, "actions": actions_taken}

    def generate_cycle_intro(self, cycle_number: int, role_mention: str = "@Community Seal Updates") -> str:
        """
        Use Gemini Flash to generate a new thread introduction for the current cycle.  **Be creative in this section!**
        """

        prompt = f"""
Generate an introduction for the "Cycle {cycle_number} - Nominations" Discord thread. 

Example:
"Hey {role_mention}!  
*Create something to fill some space with a random fact or interesting tidbit regarding Marvel, DC, or other superhero media.  Be creative.  Format it in italics.*

Welcome to Cycle {cycle_number}! This thread will be used for nominations for Cycle {cycle_number}!

Rules
• You may nominate 2 Hero sets and 1 Encounter set. Please include "hero" or "encounter" in your nomination to specify which type of set you are nominating.

Output *only* the generated introduction text.
"""
        from google.genai import types
        response = self.client.models.generate_content(
            model='gemini-flash-latest',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=1.4
            )
        )
        return response.text.strip()

