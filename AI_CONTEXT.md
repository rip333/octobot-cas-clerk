# AI Context for Octobot CAS Clerk

## Project Overview
Octobot CAS Clerk is an AI-driven Discord bot and webhook listener for a Marvel Champions LCG Discord server. It serves as a "Silent Secretary" that processes natural language messages, determines the user's intent regarding homebrew content nominations, and executes actions against a Google Cloud Firestore backend using the Model Context Protocol (MCP).

## Architecture & Core Technologies
- **Language**: Python 3.9+
- **Discord Integration**: `discord.py` (Bot client, rate limiting, thread watching, and slash commands)
- **AI Intelligence**: `google-genai` (using Gemini Flash Latest) to extract intent from natural language and generate cycle intros.
- **Backend/Database**: Google Cloud Firestore. Uses a `cycle_metadata` document to persist state:
    - `number`: Current cycle number.
    - `nomination_thread_id`: The ID of the active Discord thread. (Syncs instantly to bot on creation)
    - `state`: Current phase of the cycle (`"nominations"`, `"voting"`, or `"off"`).

## Directory Structure
- `main.py`: HTTP Cloud Function entry point for webhook payloads.
- `discord_bot.py`: The async Discord bot client. Listens to the active thread, but only processes messages via Gemini if `state == "nominations"`.
- `gemini_agent.py`: Orchestrates the `google-genai` client and Firestore MCP tools.
- `mcp_firestore.py`: toolkit for Firestore interactions.
- `cogs/nomination_report.py`: Slash command for nomination summaries.
- `cogs/cycle_management.py`: Manages transitions into the `"nominations"` state.
- `cogs/voting.py`: Manages transitions into the `"voting"` state and provides the interactive voting UI.
- `set_state_off.py`: Utility script to manually set `state` to `"off"`.

## Core Directives for the Agent
When modifying this codebase, keep the following architectural constraints in mind:
1. **Silent Selection Phase**: While adding/removing nominations is silent via the LLM, the **Voting Phase** uses interactive Discord components (Select Menus) spawned ephemerally via `/vote`.
2. **State-Gated Processing**: The bot's on-message handler is gated. It MUST check that the current message is in the correct thread AND that the state is `"nominations"` before hitting the Gemini API.
3. **Display Name Tracking**: Both the `add_nomination` and `record_user_vote` MCP tools require the user's Discord Display Name (`nominatorName`, `userName`) to be stored alongside their numeric ID for auditing.
4. **Intent Extraction over Commands**: Users speak naturally for nominations; the LLM handles extraction. Voting is performed via explicit UI interactions.
4. **Hard Logic vs. Soft Logic**: 
    - **Soft Logic**: AI handles ambiguity (Hero vs. Villain).
    - **Hard Logic**: Firestore tools handle deduplication and structured errors.

## Key Environment Variables
- `DISCORD_TOKEN`: Discord Bot Token.
- `GEMINI_API_KEY`: Google Gemini API Key.
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to the service account JSON.
