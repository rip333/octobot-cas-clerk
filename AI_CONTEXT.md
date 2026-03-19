# AI Context: Octobot CAS Clerk

## Project Overview
Octobot CAS Clerk is an AI-driven "Silent Secretary" for a Marvel Champions LCG homebrew community. It manages the lifecycle of custom content approval (nominations and voting) using natural language processing (NLP) to parse user messages and a structured interactive UI for administrative tasks.

## Core Architecture
- **Language**: Python 3.9+
- **Discord Integration**: `discord.py` using Slash Commands (Cogs) and persistent views.
- **AI Engine**: `google-genai` (Gemini Flash) for intent extraction and IP category guessing (Marvel, DC, or Other).
- **Backend**: Google Cloud Firestore, accessed via the `MCPFirestore` toolkit.
- **Model Context Protocol (MCP)**: The `GeminiAgent` uses Firestore methods as tools to perform actions like adding nominations or logging errors.

## Cycle State Machine
The bot's behavior is strictly gated by the `state` field in the `cycle_metadata/current` Firestore document:

- **`planning`**: The initial idle state. Only the `/start-nominations` command is valid.
- **`nominations`**:
    - The bot monitors a specific thread (`nomination_thread_id`).
    - `on_message` payloads are sent to Gemini for NLP extraction.
    - Gemini attempts to identify the nominee, category (Hero/Encounter), creator, and IP category.
- **`voting`**:
    - Admins trigger this via `/start-voting`.
    - Users cast ephemeral ballots via `/vote` (Max 10 Heroes, 2 Encounters).
    - Admins perform IP cleanup (`/assign-ip`) and final roster generation (`/confirm-spotlight`).
- **`off` / `complete`**: The cycle ends, data is archived, and the system resets to `planning`.

## Spotlight Selection Logic
The `/confirm-spotlight` command implements "Hard Logic" to enforce community quotas:

- **Quotas**: Automatically selects 2 Marvel, 2 DC, 2 Other, and 2 Wildcard sets based on vote counts.
- **Creator Limit**: Only one set per creator can be included in the final roster.
- **Tiebreaking**: If multiple sets are tied at the threshold for a quota or creator slot, the bot spawns an interactive `TiebreakerView` for the admin to resolve the conflict manually.

## Key Files & Responsibilities
- **`discord_bot.py`**: Entry point. Manages state-gating and rate-limiting for the `on_message` listener.
- **`gemini_agent.py`**: Contains the system instructions for the LLM. It defines how Gemini should format names and guess IP categories.
- **`mcp_firestore.py`**: The "Source of Truth" for all database interactions, including cycle resets and vote tallies.
- **`cogs/`**:
    - **`voting.py`**: Manages the interactive voting phase and tallying.
    - **`assign_ip.py`**: Provides a "Back" button UI for admins to manually label IP categories if AI guessing fails.
    - **`confirm_spotlight.py`**: Executes the complex selection algorithm and creates Google Forms for the winners.

## Critical Constraints for AI Development
- **State-Gating**: Never process messages for nominations unless `state == "nominations"`.
- **Ephemeral Views**: All admin commands and user voting interfaces must be ephemeral to maintain privacy in public threads.
- **Audit Trails**: Always store `nominatorName` or `userName` alongside IDs when using `add_nomination` or `record_user_vote`.
- **IP Guessing**: Gemini should use its internal knowledge to pre-label IP categories as "Marvel", "DC", or "Other" during the nomination phase to reduce admin workload later.