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
        - `add_nomination(nominator_id="...", nominee_name="...", category="...")`: Add a nomination. category must be EXACTLY "HERO" or "ENCOUNTER". nominator_id is the current user's ID.
        - `remove_nomination(nomination_id="...")`: Remove a nomination by its document ID.
        - `log_error(text="...")`: Log a nomination error with a reason.

        Analyze the user's intent and use the necessary tools. Read the rules if the user's message is on topic for nominations.
        """
        
        from google.genai import types
        
        response = self.client.models.generate_content(
            model='gemini-flash-latest',
            contents=system_instruction,
            config=types.GenerateContentConfig(
                tools=[
                    self.firestore_tool.get_rules,
                    self.firestore_tool.get_nominations,
                    self.firestore_tool.add_nomination,
                    self.firestore_tool.remove_nomination,
                    self.firestore_tool.log_error
                ],
                temperature=0.1,
            )
        )
        
        # In a real app we'd iterate over function calls if using manual loop, 
        # but modern SDK with tools might auto-call if enabled, or we parse response.function_calls.
        # Note: If automatic function calling isn't enabled by default, you may need a loop.
        
        return {"status": "success", "gemini_response": response.text}

    def generate_cycle_intro(self, cycle_number: int) -> str:
        """
        Use Gemini Flash to generate a new thread introduction for the current cycle.  **Be creative in this section!**
        """

        prompt = f"""
Generate an introduction for the "Cycle {cycle_number} - Nominations" Discord thread. 

Example:
"Hey @Community Seal Updates!  
** Create something to fill some space with a random fact or interesting tidbit regarding Marvel, DC, or other superhero media.  Be creative.

Welcome to Cycle {cycle_number}!  This thread will be used for nominations for Cycle {cycle_number}!  Please read over the rules here and then nominate away!

Rules
• You may nominate 2 Hero sets and 1 Encounter set"

Output *only* the generated introduction text. Do not wrap it in markdown code blocks unless necessary.
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

