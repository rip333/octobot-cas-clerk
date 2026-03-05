# Octobot CAS Clerk

**Marvel Champions Homebrew Community Approval System Clerk**

Octobot CAS Clerk is a sophisticated, AI-driven Discord bot and webhook listener designed to serve as a "Silent Secretary" for managing homebrew content nominations within a Marvel Champions LCG Discord server. By leveraging Google's Gemini Flash AI and Model Context Protocol (MCP) tool integration, the bot can intelligently understand natural language messages from Discord users, determine their intent (such as adding, withdrawing, or querying nominations), and execute the required actions directly into a Google Cloud Firestore backend.

## Features

- **Discord Listener & Command Setup**  
  Listens to a specific nomination thread, employing an efficient executor to offload asynchronous AI processing without blocking the main Discord event loop. Also includes a slash command (`/cap-report`) to generate a dynamic, embedded summary of all current Hero and Encounter nominations.
- **Natural Language Intent Extraction (Gemini AI)**  
  Instead of requiring rigid `/commands` for every action, the bot reads standard messages, understands context, resolves ambiguity (e.g., parsing whether "Venom" means the hero or the villain), and processes batch inputs in a single message.
- **Model Context Protocol (MCP) Backend**  
  The agent seamlessly executes intent by using a suite of custom Python tools (`get_rules`, `add_nomination`, `remove_nomination`, `get_nominations`, `log_error`) mapped via prompt to Gemini, allowing dynamic execution against the Firestore `octobot-cas-db`.
- **Advanced Rules & Verification Engine**  
  Implements hard-logic systems (deduplication of nominees) and specific behavioral directives (Silent Execution, comprehensive Error Logging for failures like `QUOTA_EXCEEDED` or `AMBIGUOUS_TYPE`).
- **Google Cloud Functions Support**  
  Exposes an HTTP Cloud Function (`main.py`) that can receive webhook payloads from alternative platforms and funnel them directly into the Gemini extraction layer.

## Architecture

The system is decoupled into several main components:
- **`discord_bot.py`**: The main async Discord bot script utilizing `discord.py` to listen for messages, handle rate-limiting, and trigger the agent.
- **`main.py`**: The Google Cloud Functions entry point for webhook-driven events via `functions-framework`.
- **`gemini_agent.py`**: Configured to orchestrate the `google-genai` client, construct the prompt definitions, and inject Firebase MCP toolsets.
- **`mcp_firestore.py`**: The toolkit containing mutation and query functions connecting to Google Cloud Firestore.
- **`cogs/cap_report.py`**: Discord Cog containing the interactive `/cap-report` UI component.
- **`rules.txt`**: Plaintext definitions given directly to the AI as part of its system prompt to restrict edge-cases and validate behavior.

## Prerequisites

- **Python 3.9+**
- **Google Cloud Platform Account**: Need to have Cloud Firestore and Gen AI enabled.
- **Discord Developer Application**: A bot token with Message Content Intents enabled.

## Setup Instructions

### 1. Installation

Clone the repository and install the required dependencies:

```bash
git clone git@github.com:User/octobot-cas-clerk.git
cd octobot-cas-clerk
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Configuration

Create a `.env` file in the root directory (referencing the required secrets):

```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
NOMINATION_THREAD_ID=the_discord_thread_id_to_watch
```

*Note: You must also ensure that the environment running the code has access to Google Cloud Default Credentials configured for Firestore connection (`GOOGLE_APPLICATION_CREDENTIALS`).*

### 3. Running Locally

**To run the Discord Bot Client:**
```bash
python discord_bot.py
```

**To test the Cloud Function Webhook locally:**
```bash
functions-framework --target=handle_nomination_webhook
```
*You can then throw HTTP POST requests with JSON containing `content`, `author_id`, and `author_name` at `localhost:8080`.*

### 4. Deployment

Deploy the serverless Cloud Function components utilizing Google Cloud CLI:
```bash
gcloud functions deploy handle_nomination_webhook \
  --runtime python39 \
  --trigger-http \
  --allow-unauthenticated
```
Make sure that your deployed function has access to the appropriate secrets required by `gemini_agent.py` and `firebase`.

## License
MIT License.
