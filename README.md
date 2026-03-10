# Octobot CAS Clerk

**Marvel Champions Homebrew Community Approval System Clerk**

Octobot CAS Clerk is the second arm of the bot - to help the homebrew community manage the voting and sealing of custom content. 

## Prerequisites

- **Python 3.9+**
- **Google Cloud Platform Account**: Need to have Cloud Firestore and Gen AI enabled.
- **Discord Developer Application**: A bot token with Message Content Intents enabled.

## Bot Commands & Workflow

The Octobot manages the homebrew lifecycle through distinct phases:
1. **Nominations Phase**: Users nominate Heroes and Encounters (monitored and parsed by a Gemini natural language agent).
2. **Voting Phase**: Admins use `/start-voting` to lock nominations. Users cast their ballots using `/vote` (selecting up to 10 Heroes and 2 Encounters). Admins can view raw vote numbers anytime with `/tally-votes`.
3. **Spotlight Assignment Phase**: 
   - After voting, admins use `/assign-ip` to interactively tag the IP (Marvel, DC, Other) for every unique candidate.
   - Finally, they run `/confirm-spotlight` to automatically enforce quotas (2 Marvel, 2 DC, 2 Other, 2 Wildcards) and limits (1-per-creator). The bot will intercede and prompt the admin with a Tiebreaker UI if any manual resolutions are required before saving the final Spotlight Roster.

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
