# Octobot CAS Clerk

**Marvel Champions Homebrew Community Approval System Clerk**

Octobot CAS Clerk is the Discord bot that helps the homebrew community manage the nomination, voting, and sealing of custom content through a structured cycle workflow.

## Prerequisites

- **Python 3.11+**
- **Google Cloud Platform Account**: Cloud Firestore (database: `octobot-cas-db`) and Gemini AI enabled.
- **Discord Developer Application**: A bot token with Message Content Intents enabled.
- **Google OAuth Credentials**: For Google Drive/Forms access (`credentials.json` and `token.json`).

## Bot Commands & Workflow

The Octobot manages the homebrew lifecycle through distinct phases. The active phase is stored in Firestore and gates each command.

### Cycle States
`planning` → `nominations` → `voting` → `review` → `complete`

### 1. Nominations Phase (`nominations`)
- **`/start-cycle`** *(Admin)*: Creates the Nominations & Voting thread and transitions the cycle from `planning` to `nominations`. Opens a modal to confirm the cycle number. Ineligible creators (from the previous cycle's `sealed_sets`) are announced in the opening message.
- **`/tally-nominations`** *(Admin)*: Fetches the entire history of the nominations thread and sends it to the Gemini AI agent for batch processing. The agent parses all valid nominations (respecting rules and creator eligibility), guesses the IP category (Marvel/DC/Other), and writes the results to Firestore in bulk. This replaces any previously tallied nominations.

### 2. Voting Phase (`voting`)
- **`/start-voting`** *(Admin)*: Locks nominations, posts the final nominee list publicly, and transitions the cycle to the `voting` state.
- **`/vote`** *(Public)*: Sends the user an ephemeral ballot UI with dropdown selects for up to **10 Heroes** and **3 Encounters**. Heroes are chunked into multiple select menus if there are more than 25 options. Submitting records the vote in Firestore (one document per user, overwriting any previous vote).
- **`/tally-votes`** *(Admin)*: Displays the current vote counts for the active cycle, filtered to show at most one set per creator.

### 3. Spotlight Assignment Phase (`voting`)
- **`/assign-ip`** *(Admin)*: Launches an interactive flow to manually assign IP categories (Marvel/DC/Other) to any nominations that were not correctly auto-labeled by the AI.
- **`/confirm-spotlight`** *(Admin)*: Runs the full spotlight selection algorithm:
  - Resolves per-creator ties (only the highest-voted set per creator moves forward).
  - Fills **2 Encounter** slots, then **2 Marvel / 2 DC / 2 Other** Hero slots, then **2 Wildcard** slots from the remaining pool.
  - Prompts the admin with an interactive **Tiebreaker UI** for any tied slots that cannot be resolved automatically.
  - Previews the final roster and asks for a final confirmation.
  - Upon confirmation: clones a Google Form template for each Spotlight Set, organizes them into a Drive folder, opens a public **"Cycle X - Scorecards"** thread with all review links embedded, saves the roster to Firestore, and transitions the cycle state to `review`.

### 4. Review & Reporting
- **`/view-nominations`** *(Admin)*: Select any past or current cycle from a dropdown to view its full nomination list.
- **`/view-votes`** *(Admin)*: Select any cycle from a dropdown to view the full vote tallies.
- **`/view-spotlight-scorecard`** *(Public)*: View the confirmed Spotlight Roster and Google Form links for the active cycle's review.

---

## Setup Instructions

### 1. Installation

Clone the repository and install the required dependencies:

```bash
git clone git@github.com:rip333/octobot-cas-clerk.git
cd octobot-cas-clerk
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy `.env_template` to `.env` and fill in your values:

```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
CLOUD_FUNCTION_URL=your_cloud_function_url
GOOGLE_APPLICATION_CREDENTIALS=gen-lang-client.json
GOOGLE_TEMPLATE_FORM_ID=your_template_google_form_id
GOOGLE_DRIVE_FOLDER_ID=your_google_drive_folder_id
ALLOWED_GUILDS=your_guild_id_1,your_guild_id_2
```

> **Note on `ALLOWED_GUILDS`**: A comma-separated list of Discord server IDs the bot is authorized to operate in. If set, the bot will leave any unauthorized server it joins and ignore slash command interactions from other guilds. Leave empty to allow all guilds.

> **Note on `ENVIRONMENT`**: Set to `test` to use Firestore collections prefixed with `test_` (e.g., `test_cycles`, `test_nominations`), keeping test data isolated from production. Any other value (or omitting it) uses production collections.

> **Note on Google credentials**: You must have `gen-lang-client.json` (a GCP Service Account key for Firestore) and `token.json` (OAuth token for Google Drive/Forms access) in the project root. Run `python get_google_token.py` to generate `token.json` from your `credentials.json`.

### 3. Running Locally

**To run the Discord Bot:**
```bash
python discord_bot.py
```

On Windows, you can also use the included batch file:
```bash
start_bot.bat
```

### 4. Running Tests

The project includes a `pytest` suite covering core business logic in the `tests/` directory. Tests use mocked Discord interactions and a mocked Firestore client, so no live credentials are required.

```bash
pytest
```

Test files:
- `tests/test_cycle_management.py` — Tests for `/start-cycle` state and channel validation.
- `tests/test_process_nominations.py` — Tests for `/tally-nominations` state gating and AI result processing.
- `tests/test_voting.py` — Tests for `/vote` state gating, empty nominations handling, and `VotingView` construction.

### 5. Deployment

#### Continuous Deployment (CI/CD)

This repository includes a GitHub Actions workflow (`.github/workflows/deploy.yml`) that runs automatically on every push to `main`. The pipeline has three sequential stages:

1. **Lint and Syntax Check** (`lint-and-check`): Runs `flake8` to catch syntax errors and undefined names.
2. **Unit Tests** (`run-tests`): Runs the full `pytest` suite. Both the Cloud Function and Discord Bot deploys are **gated behind this job** — a failing test blocks deployment.
3. **Deploy Webhook to GCF** (`deploy-cloud-function`): Deploys `main.py` as a Google Cloud Function (`handle_nomination_webhook`) only if `main.py` or `requirements.txt` changed (uses path filtering).
4. **Deploy Discord Bot to VM** (`deploy-discord-bot`): SSHs into the GCE VM via `google-github-actions/ssh-compute`, pulls the latest code, writes secrets to `.env`, installs dependencies, and restarts the `octobot.service` systemd daemon.

#### Required GitHub Secrets

Configure these in your repository under `Settings > Secrets and variables > Actions`:

| Secret | Description |
|---|---|
| `GCP_CREDENTIALS` | JSON Service Account key with permissions for Cloud Functions and Compute Engine SSH. |
| `VM_SSH_KEY` | Private SSH key used to authenticate into the GCE VM. |
| `DISCORD_TOKEN` | Discord bot token, written to `.env` on the VM and injected into the Cloud Function. |
| `GEMINI_API_KEY` | Gemini API key, written to `.env` on the VM and injected into the Cloud Function. |
| `CLOUD_FUNCTION_URL` | The deployed Cloud Function URL, written to `.env` on the VM. |
| `GOOGLE_OAUTH_TOKEN` | Contents of `token.json` (Google OAuth token for Drive/Forms), written to the VM. |

---

## Project Structure

```
octobot-cas-clerk/
├── discord_bot.py          # Main bot entrypoint; loads all cogs on startup
├── mcp_firestore.py        # Firestore data access layer (MCPFirestore class)
├── gemini_agent.py         # Gemini AI agent for batch-processing nomination threads
├── google_services.py      # Google Drive & Forms API helpers (GoogleServices class)
├── main.py                 # Cloud Function entrypoint (handle_nomination_webhook)
├── rules.txt               # Nomination rules text, loaded dynamically by the AI agent
├── requirements.txt
├── pytest.ini
├── cogs/
│   ├── cycle_management.py       # /start-cycle
│   ├── process_nominations.py    # /tally-nominations
│   ├── voting.py                 # /start-voting, /vote, /tally-votes
│   ├── assign_ip.py              # /assign-ip
│   ├── confirm_spotlight.py      # /confirm-spotlight
│   ├── view_reports.py           # /view-nominations, /view-votes
│   └── view_spotlight_scorecard.py # /view-spotlight-scorecard
├── tests/
│   ├── conftest.py
│   ├── test_cycle_management.py
│   ├── test_process_nominations.py
│   └── test_voting.py
├── functions/
│   └── index.js            # Legacy Firebase Cloud Function (MCP endpoint)
└── scripts_local/          # Local utility scripts (not deployed)
```

## Database Schema

The bot uses a Cloud Firestore database named `octobot-cas-db`. In `test` environments, all collection names are prefixed with `test_`.

```
cycles/
  current_cycle           # { number: int } — pointer to the active cycle
  {cycle_number}/         # e.g., "12"
    { number, state, is_active, nomination_thread_id, spotlights[] }
    nominations/
      {nominator_discord_id}
        { nominator_id, nominator_name, sets[], timestamp }
    votes/
      {voter_discord_id}
        { userId, userName, heroes[], encounters[], timestamp }

sealed_sets/
  {auto_id}               # { set_name, creatorName, category, type, cycle_number, ... }

errors/
  {auto_id}               # { text, timestamp }
```

## License
MIT License.
