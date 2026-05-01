import os
import logging

from google import genai
from google.api_core import exceptions as google_exceptions

logger = logging.getLogger('octobot')

# Rough token limit for Gemini 2.5 Flash (1M context), with buffer for system prompt overhead
MAX_ESTIMATED_TOKENS = 900_000

from mcp_firestore import MCPFirestore
from pydantic import BaseModel, Field
from typing import List, Optional

class Nomination(BaseModel):
    nominator_id: str = Field(description="The Discord user ID of the person nominating")
    nominator_name: str = Field(description="The display name of the person nominating")
    set_name: str = Field(description="The name of the Hero or Encounter set being nominated. Use standard capitalization.")
    category: str = Field(description="Either 'Hero' or 'Encounter'")
    creator_name: str = Field(description="The name of the creator of the set. Empty string if unknown.", default="")
    creator_discord_id: str = Field(description="The raw Discord mention string of the creator if used (e.g. <@123456>). Empty string if unknown.", default="")
    ip_category: str = Field(description="The guessed IP category: 'Marvel', 'DC', or 'Other'. Empty string if unknown.", default="")

class ProcessThreadResult(BaseModel):
    nominations: list[Nomination] = Field(description="List of all valid nominations extracted from the thread.")


class GeminiAgent:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.firestore_tool = MCPFirestore()



    def process_thread(self, history_text: str, rules_text: str, hero_creators: list, encounter_creators: list) -> dict:
        """
        Use Gemini Flash to extract all valid nominations from the thread history at once.
        Returns a dict with a 'nominations' list.
        """
        from google.genai import types
        
        system_instruction = f"""
        You are the CAP Silent Secretary, processing nominations in a Marvel Champions LCG Discord thread.
        This community loves and creates custom content for a superhero card game and wants to nominate the best sets.
        Hero sets are played by players in a cooperative game against an autopiloted encounter set.
        
        RULES:
        {rules_text}
        
        INELIGIBLE CREATORS (Do not accept nominations for sets by these creators for these categories):
        Heroes: {hero_creators}
        Encounters: {encounter_creators}
        
        You are provided with the ENTIRE chat history of the nominations thread.
        Your job is to read through the entire conversation and extract the final list of valid nominations.
        
        Consider the following when extracting nominations:
        1. Users may nominate sets in earlier messages, and change their minds or retract them later. Only include their final intent.
        2. "Vote for" or "I second" should be treated as nominations.
        3. A user can nominate up to 2 Heroes and 1 Encounter. If they nominate more, only take the first ones or their latest clarification.
        4. A user CANNOT nominate their own set.
        5. A user CANNOT nominate a set by an ineligible creator for that category.
        6. The administrator 'ripper3' may perform admin overrides (e.g. adding nominations for others).
        7. If multiple users nominate the SAME set, list it multiple times (once for each nominator).
        8. Format nominee names consistently (e.g., "spiderman" -> "Spider-Man").
        9. `ip_category` should be your best guess ("Marvel", "DC", or "Other").

        Thread History:
        {history_text}
        """

        # Pre-flight check: estimate token count and bail early if too large
        estimated_tokens = len(system_instruction) // 4
        if estimated_tokens > MAX_ESTIMATED_TOKENS:
            logger.error(f"Thread history too large for Gemini context window. Estimated tokens: {estimated_tokens:,} (limit: {MAX_ESTIMATED_TOKENS:,})")
            return {
                "status": "error",
                "error": f"Thread history is too large to process (~{estimated_tokens:,} estimated tokens). Max is ~{MAX_ESTIMATED_TOKENS:,}."
            }

        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=system_instruction,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ProcessThreadResult,
                    temperature=0.1,
                )
            )
            
            # Since we are using structured outputs, the response text is a JSON string matching the schema.
            # We can parse it directly.
            import json
            result_dict = json.loads(response.text)
            return {"status": "success", "nominations": result_dict.get("nominations", [])}

        except google_exceptions.InvalidArgument as e:
            logger.error(f"Gemini API rejected the request (likely context length): {e}")
            return {"status": "error", "error": f"Gemini rejected the request — the thread history may be too large. Details: {e}"}
        except google_exceptions.ResourceExhausted as e:
            logger.error(f"Gemini API quota exceeded: {e}")
            return {"status": "error", "error": f"Gemini API quota exceeded. Try again later. Details: {e}"}
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            return {"status": "error", "error": f"Gemini returned an unparseable response: {e}"}
        except Exception as e:
            logger.error(f"Unexpected error during Gemini processing: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}


