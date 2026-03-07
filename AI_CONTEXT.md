# AI Context for Octobot CAS Clerk

## Project Overview
Octobot CAS Clerk is an AI-driven Discord bot and webhook listener for a Marvel Champions LCG Discord server. It serves as a "Silent Secretary" that processes natural language messages, determines the user's intent regarding homebrew content nominations, and executes actions against a Google Cloud Firestore backend using the Model Context Protocol (MCP).

## Architecture & Core Technologies
- **Language**: Python 3.9+
- **Discord Integration**: `discord.py` (Bot client, rate limiting, thread watching, `/cap-report` and `/start-nominations` commands)
- **AI Intelligence**: `google-genai` (using Gemini Flash Latest) to extract intent from natural language, and generate cycle thread intros.
- **Backend/Database**: Google Cloud Firestore (using `google-cloud-firestore`), integrated as MCP tools. Uses a `cycle_metadata` document to persist state such as current cycle number and the dynamic `nomination_thread_id`.
- **Cloud Gateway**: `functions-framework` (entry point `main.py`) for Google Cloud Functions exposing HTTP endpoints.

## Directory Structure
- `main.py`: HTTP Cloud Function entry point for webhook payloads.
- `discord_bot.py`: The async Discord bot client. Listens to a specific thread, rate-limits users (2s cooldown), and dispatches messages to the Gemini agent in a thread pool executor. It boots up by reading `cycle_metadata` to find the active thread.
- `gemini_agent.py`: Orchestrates the `google-genai` client. Constructs the system prompt giving the AI rules, injects the Firestore MCP tools, and contains functionality to prompt the LLM for new thread introductions.
- `mcp_firestore.py`: Contains the actual implementation of the tools (e.g., `get_rules`, `get_nominations`, `add_nomination`, `remove_nomination`, `log_error`, `get_cycle_metadata`).
- `cogs/cap_report.py`: A `discord.py` Cog that implements the `/cap-report` slash command to generate a summary of current Hero and Encounter nominations.
- `cogs/cycle_management.py`: A `discord.py` Cog managing cycle transitions. The `/start-nominations` command clears the old database, increments the cycle, generates an intro with Gemini, creates a new Discord thread, and updates Firestore's `cycle_metadata`.
- `rules.txt`: Plaintext file injected into the Gemini prompt detailing how to handle edge cases, deduplication, ambiguity, and logging.

## Core Directives for the Agent
When modifying this codebase, keep the following architectural constraints in mind:
1. **Silent Execution**: The bot must act as a "Silent Clerk". It reads the thread and performs actions in the background but should NOT send conversational reply messages in the thread itself. The only user-facing output is the `/cap-report` command.
2. **Intent Extraction over Commands**: The core philosophy is to avoid rigid `!commands`. The user speaks naturally, and `gemini_agent.py` extracts the intent (add, remove, check) and calls the appropriate MCP tool.
3. **Hard Logic vs. Soft Logic**: 
    - **Soft Logic** (Gemini): Determining if the user means "Venom" (Hero) or "Venom" (Villain).
    - **Hard Logic** (Firestore Tools): Deduplicating entries natively before writing, logging specific structured errors (`QUOTA_EXCEEDED`, `AMBIGUOUS_TYPE`).
4. **Asynchronous Non-Blocking Execution**: Calls to the Gemini API are synchronous in the SDK, so `discord_bot.py` uses `loop.run_in_executor()` to avoid blocking the Discord bot's async event loop. Keep this pattern intact.

## Key Environment Variables
- `DISCORD_TOKEN`: Discord Bot Token.
- `GEMINI_API_KEY`: Google Gemini API Key.
- `CLOUD_FUNCTION_URL`: URL to point webhooks at, if testing local integrations.
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to the service account JSON needed to connect to Firestore outside of GCP environments.
