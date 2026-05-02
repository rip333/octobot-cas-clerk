from pydantic import BaseModel, Field
from typing import List, Type, Dict, Any

class CycleRuleBase:
    """Base class for defining cycle business logic and AI prompts."""
    
    @property
    def cycle_type(self) -> str:
        raise NotImplementedError

    def get_nomination_schema(self) -> Type[BaseModel]:
        """Return the Pydantic BaseModel for a single nomination."""
        raise NotImplementedError

    def get_result_schema(self) -> Type[BaseModel]:
        """Return the Pydantic BaseModel for the overall thread processing result."""
        raise NotImplementedError

    def build_system_instruction(self, history_text: str, context: Dict[str, Any]) -> str:
        """Build the system instruction prompt for the LLM based on context."""
        raise NotImplementedError

    def post_process_nominations(self, nominations: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Optional hook to filter or modify the AI's extracted nominations."""
        return nominations


class StandardNomination(BaseModel):
    nominator_id: str = Field(description="The Discord user ID of the person nominating")
    nominator_name: str = Field(description="The display name of the person nominating")
    set_name: str = Field(description="The name of the Hero or Encounter set being nominated. Use standard capitalization.")
    category: str = Field(description="Either 'Hero' or 'Encounter'")
    creator_name: str = Field(description="The name of the creator of the set. Empty string if unknown.", default="")
    creator_discord_id: str = Field(description="The raw Discord mention string of the creator if used (e.g. <@123456>). Empty string if unknown.", default="")
    ip_category: str = Field(description="The guessed IP category: 'Marvel', 'DC', or 'Other'. Empty string if unknown.", default="")

class StandardProcessResult(BaseModel):
    nominations: list[StandardNomination] = Field(description="List of all valid nominations extracted from the thread.")


class StandardCycleRule(CycleRuleBase):
    @property
    def cycle_type(self) -> str:
        return "standard"

    def get_nomination_schema(self) -> Type[BaseModel]:
        return StandardNomination

    def get_result_schema(self) -> Type[BaseModel]:
        return StandardProcessResult

    def build_system_instruction(self, history_text: str, context: Dict[str, Any]) -> str:
        rules_text = context.get("rules_text", "")
        hero_creators = context.get("hero_creators", [])
        encounter_creators = context.get("encounter_creators", [])

        return f"""
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
        6. The administrator 'ripper3' may perform admin overrides (e.g. adding nominations for others or himself).
        7. If multiple users nominate the SAME set, list it multiple times (once for each nominator).
        8. Format nominee names consistently (e.g., "spiderman" -> "Spider-Man").
        9. `ip_category` should be your best guess ("Marvel", "DC", or "Other").

        Thread History:
        {history_text}
        """

class RedemptionCycleRule(CycleRuleBase):
    @property
    def cycle_type(self) -> str:
        return "redemption"

    def get_nomination_schema(self) -> Type[BaseModel]:
        return StandardNomination

    def get_result_schema(self) -> Type[BaseModel]:
        return StandardProcessResult

    def build_system_instruction(self, history_text: str, context: Dict[str, Any]) -> str:
        rules_text = context.get("rules_text", "")
        eligible_sets = context.get("eligible_sets", [])
        
        # Format eligible sets for the prompt to help the LLM guide its extraction
        eligible_str = ", ".join([f"'{s}'" for s in eligible_sets]) if eligible_sets else "None available"

        return f"""
        You are the CAP Silent Secretary, processing nominations for a REDEMPTION CYCLE in a Marvel Champions LCG Discord thread.
        This community loves and creates custom content for a superhero card game and wants to nominate the best sets.
        
        RULES:
        {rules_text}
        
        REDEMPTION CYCLE RULES:
        - This cycle allows sets that were previously spotlighted but NOT sealed.
        - SELF-NOMINATIONS ARE ALLOWED in a Redemption cycle.
        
        ELIGIBLE SETS (Only sets matching these names should be extracted as valid nominations):
        {eligible_str}
        
        You are provided with the ENTIRE chat history of the nominations thread.
        Your job is to read through the entire conversation and extract the final list of valid nominations.
        
        Consider the following when extracting nominations:
        1. Users may nominate sets in earlier messages, and change their minds or retract them later. Only include their final intent.
        2. "Vote for" or "I second" should be treated as nominations.
        3. A user can nominate up to 2 Heroes and 1 Encounter. If they nominate more, only take the first ones or their latest clarification.
        4. The administrator 'ripper3' may perform admin overrides (e.g. adding nominations for others or himself).
        5. If multiple users nominate the SAME set, list it multiple times (once for each nominator).
        6. Format nominee names consistently (e.g., "spiderman" -> "Spider-Man").
        7. `ip_category` should be your best guess ("Marvel", "DC", or "Other").

        Thread History:
        {history_text}
        """

    def post_process_nominations(self, nominations: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Python-side filtering to strictly enforce eligibility
        eligible_sets_lower = [s.lower() for s in context.get("eligible_sets", [])]
        valid_nominations = []
        for nom in nominations:
            # We assume dict-like access here since we convert from Pydantic
            set_name = nom.get("set_name", "").lower()
            # Simple matching: if the lowercased name matches or is a substring of an eligible set
            # In a real scenario we might need fuzzy matching, but for now exact/substring is safe
            is_valid = any(set_name in e or e in set_name for e in eligible_sets_lower)
            if is_valid or not eligible_sets_lower: # If eligible_sets is empty we might skip filtering or reject all, for now skip if not provided properly
                valid_nominations.append(nom)
            else:
                import logging
                logger = logging.getLogger('octobot')
                logger.info(f"RedemptionCycleRule: Filtered out ineligible nomination '{nom.get('set_name')}'")
                
        return valid_nominations

def get_rule_for_type(cycle_type: str) -> CycleRuleBase:
    if cycle_type == "redemption":
        return RedemptionCycleRule()
    return StandardCycleRule()
