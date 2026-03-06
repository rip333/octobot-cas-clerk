# Octobot CAS Clerk

**Marvel Champions Homebrew Community Approval System Clerk**

Octobot CAS Clerk is a sophisticated, AI-driven Discord bot and webhook listener designed to serve as a "Silent Secretary" for managing homebrew content nominations within a Marvel Champions LCG Discord server. By leveraging Google's Gemini Flash AI and Model Context Protocol (MCP) tool integration, the bot can intelligently understand natural language messages from Discord users, determine their intent (such as adding, withdrawing, or querying nominations), and execute the required actions directly into a Google Cloud Firestore backend.

## Features

- **Discord Listener & Command Setup**  
  Listens to a specific nomination thread, employing an efficient executor to offload asynchronous AI processing without blocking the main Discord event loop. Includes slash commands such as `/cap-report` to generate a dynamic summary and `/start-nominations` to initialize new cycles.
- **Natural Language Intent Extraction (Gemini AI)**  
  Instead of requiring rigid `/commands` for every action, the bot reads standard messages, understands context, resolves ambiguity (e.g., parsing whether "Venom" means the hero or the villain), and processes batch inputs in a single message.
- **Model Context Protocol (MCP) Backend**  
  The agent seamlessly executes intent by using a suite of custom Python tools (`get_rules`, `add_nomination`, `remove_nomination`, `get_nominations`, `log_error`) mapped via prompt to Gemini, allowing dynamic execution against the Firestore `octobot-cas-db`.
- **Advanced Rules & Verification Engine**  
  Implements hard-logic systems (deduplication of nominees) and specific behavioral directives (Silent Execution, comprehensive Error Logging for failures like `QUOTA_EXCEEDED` or `AMBIGUOUS_TYPE`).
- **Dynamic Cycle Management**  
  Tracks the current cycle dynamically via Firestore (`cycle_metadata`), allowing the bot to automatically generate opening introductions for new threads via Gemini and maintain the `nomination_thread_id` dynamically.
- **Google Cloud Functions Support**  
  Exposes an HTTP Cloud Function (`main.py`) that can receive webhook payloads from alternative platforms and funnel them directly into the Gemini extraction layer.

## Architecture

The system is decoupled into several main components:
- **`discord_bot.py`**: The main async Discord bot script utilizing `discord.py` to listen for messages, handle rate-limiting, and trigger the agent.
- **`main.py`**: The Google Cloud Functions entry point for webhook-driven events via `functions-framework`.
- **`gemini_agent.py`**: Configured to orchestrate the `google-genai` client, construct the prompt definitions, inject Firebase MCP toolsets, and generate automated responses for new threads.
- **`mcp_firestore.py`**: The toolkit containing mutation and query functions connecting to Google Cloud Firestore, handling documents like nominations and cycle metadata.
- **`cogs/cap_report.py`**: Discord Cog containing the interactive `/cap-report` UI component.
- **`cogs/cycle_management.py`**: Discord Cog enabling cycle administration (`/start-nominations`), which uses the AI to dynamically generate thread intros and manage cycle resets.
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
CLOUD_FUNCTION_URL=your_cloud_function_url_for_webhooks
GOOGLE_APPLICATION_CREDENTIALS=gen-lang-client.json
```

*Note: The system loads the `nomination_thread_id` dynamically from Firestore's `cycle_metadata`. You must also ensure that the environment running the code has access to Google Cloud Default Credentials configured for Firestore connection (`GOOGLE_APPLICATION_CREDENTIALS`).*

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

### 5. Continuous Deployment (CI/CD)

This repository includes a GitHub Actions workflow (`.github/workflows/deploy.yml`) that automatically deploys the Cloud Function and Discord bot upon pushes to `main`.

#### Required GitHub Secrets
To utilize the automated pipeline, you must configure the following Secrets in your GitHub repository (`Settings` > `Secrets and variables` > `Actions`):

- **`GCP_CREDENTIALS`**: A JSON Service Account key with permissions to deploy Cloud Functions.
- **`VM_HOST`**: The external IP address of your Google Compute Engine VM hosting the Discord bot.
- **`VM_USERNAME`**: The SSH username for the VM.
- **`VM_SSH_KEY`**: A private SSH key used to authenticate into the VM.
- **`DISCORD_TOKEN`**: Exposed to the Cloud Function during automated deployment.
- **`GEMINI_API_KEY`**: Exposed to the Cloud Function during automated deployment.
- **`CLOUD_FUNCTION_URL`**: Exposed to the Cloud Function.

#### Fresh Server Initialization
If you need to rebuild the host server for the Discord bot, a bootstrap script is included. Simply copy and run `scripts/setup_vm.sh` as your main user on a fresh Ubuntu VM. This will install dependencies, pull the repository to `/opt/octobot-cas-clerk`, setup the Python environment, and generate the `octobot.service` systemd daemon.

## License
MIT License.
