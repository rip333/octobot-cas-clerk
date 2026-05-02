import os
import logging
import json

from google import genai
from google.api_core import exceptions as google_exceptions
from google.genai import types

from cycle_rules import CycleRuleBase

logger = logging.getLogger('octobot')

# Rough token limit for Gemini 2.5 Flash (1M context), with buffer for system prompt overhead
MAX_ESTIMATED_TOKENS = 900_000

class GeminiAgent:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def process_thread(self, history_text: str, rule: CycleRuleBase, context: dict) -> dict:
        """
        Use Gemini Flash to extract all valid nominations from the thread history at once.
        Returns a dict with a 'nominations' list.
        """
        
        system_instruction = rule.build_system_instruction(history_text, context)

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
                    response_schema=rule.get_result_schema(),
                    temperature=0.1,
                )
            )
            
            # Since we are using structured outputs, the response text is a JSON string matching the schema.
            # We can parse it directly.
            result_dict = json.loads(response.text)
            raw_nominations = result_dict.get("nominations", [])
            
            # Allow the rule to filter or post-process nominations
            final_nominations = rule.post_process_nominations(raw_nominations, context)
            
            return {"status": "success", "nominations": final_nominations}

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


