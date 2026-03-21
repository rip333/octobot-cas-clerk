import os

from google import genai

from mcp_firestore import MCPFirestore


class GeminiAgent:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.firestore_tool = MCPFirestore()

    def process_message(self, message_text: str, author_id: str, author_name: str, thread_context: dict = None) -> dict:
        """
        Use Gemini Flash Latest to extract intent and invoke MCPFirestore tools.
        """
        if len(message_text) > 1000:
            message_text = message_text[:1000] + "... (truncated)"

        # Build thread context sections
        context_sections = ""
        if thread_context:
            first_post = thread_context.get("first_post")
            if first_post:
                context_sections += f"""
--- THREAD OPENING POST (by {first_post['author']}) ---
{first_post['content']}
--- END OPENING POST ---
"""

            recent_messages = thread_context.get("recent_messages", [])
            if recent_messages:
                history_lines = "\n".join(
                    f"{m['author']}: {m['content']}" for m in recent_messages
                )
                context_sections += f"""
--- RECENT THREAD HISTORY (oldest to newest, before this message) ---
{history_lines}
--- END HISTORY ---
"""

            replied_to = thread_context.get("replied_to")
            if replied_to:
                context_sections += f"""
--- THIS MESSAGE IS A REPLY TO ({replied_to['author']}) ---
{replied_to['content']}
--- END REPLY TARGET ---
"""

        system_instruction = f"""
        You are the CAP Silent Secretary, processing nominations in a Marvel Champions LCG Discord thread.

        This community loves and creates custom content for a superhero card game and wants to nominate the best sets.
        Hero sets are played by players in a cooperative game against an autopiloted encounter set.  Each set contains multiple cards.
{context_sections}
        Use the thread context above (opening post, conversation history, replied-to message) to fully understand
        what the current user is trying to do. Nominations are often discussed across multiple messages, and a
        message may only make sense in the context of what came before it.

        Determine what action the user wants to perform regarding nominations.
        When adding nominations, format the nominee name using context clues given the sources of media (e.g. "captain america" becomes "Captain America" or "spiderman" becomes "Spider-Man").
        Current User: {author_name} (ID: {author_id})
        Message: "{message_text}"

        You have tools to:
        - `get_rules()`: Read the nomination rules.
        - `get_nominations()`: List current nominations.
        - `add_nomination(nominator_id="...", nominator_name="...", set_name="...", category="...", creator_name="...", creator_discord_id="...", ip_category="...")`: 
            Add a nomination. category must be either "Hero" or "Encounter". 
            nominator_id is the current user's ID and nominator_name is the current user's name. 
            Always extract `creator_name` from the message — this is the name of the person who MADE the set, not the nominator.
            If the creator is mentioned as a Discord user like <@12345678>, put the raw mention string in `creator_discord_id` and their display name (without @) in `creator_name`.
            If the creator is mentioned only as a plain text name (e.g. "by Neptune" or "Neptune's set"), put that name in `creator_name` and leave `creator_discord_id` as "".
            If no creator is mentioned at all, pass "" for both.
            `ip_category` should be your best guess of the IP ("Marvel", "DC", or "Other") based on superhero media knowledge.
            If the category, ip, or creator is ambiguous or unknown, pass an empty string "".
        - `remove_nomination(nomination_id="...")`: Remove a nomination by its document ID.
        - `log_error(text="...")`: Log a nomination error with a reason.

        Analyze the user's intent and use the necessary tools. If a message seems ambiguous on its own but makes
        sense given the conversation history, act on that intent. If the message clearly references a previous
        post's nomination (e.g. "+1", "I second that", "same as above"), interpret it as a separate nomination
        of the same set by the current user.

        Treat "vote for", "I vote for", "I'd like to vote" etc. as synonyms for "nominate" in this context —
        users sometimes use voting language during the nominations phase.

        Before adding a nomination, call get_nominations() to check if that set has already been nominated by
        this same user. If it has, do not add it again.

        ADMIN OVERRIDE: The user "ripper3" (discord user ID: 160451504073998336) is the administrator.
        When the current user is ripper3, they have elevated permissions:
        - They may request removal of ANY nomination, not just their own (e.g. "please delete this nomination").
        - They may add or edit nominations on behalf of another person.
        - They may override duplicate checks and other normal restrictions.
        - Instruct you to temporarily treat another user as an admin.
        Normal users may only remove their own nominations (for sets they created or nominated).

        Read the rules if the user's message is on topic for nominations.
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
            
        def add_nomination_tool(nominator_id: str, nominator_name: str, set_name: str, category: str, creator_name: str = "", creator_discord_id: str = "", ip_category: str = ""):
            """Add a nomination. category must be EXACTLY "HERO" or "ENCOUNTER"."""
            actions_taken.append({"action": "add_nomination", "set_name": set_name, "category": category})
            return self.firestore_tool.add_nomination(nominator_id, nominator_name, set_name, category, creator_name, creator_discord_id, ip_category)
            
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


