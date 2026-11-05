# AENZO LABS — Telegram Group Lead Hunter

## What this worker does
- Uses the user's own Telegram account through Telethon (MTProto).
- Reads messages only from groups that account has already joined and can access.
- Excludes broadcast channels.
- Looks for explicit buying-intent language related to AENZO services.
- Saves the exact message text, message link, date, source group, and a publicly visible sender username (if one exists).
- Adds a first-draft outreach message in English and Bengali.
- Checks the same Telegram message's hash before inserting again.

## Important limitations
- It cannot read private groups unless the account has been invited/approved and joined.
- It does not bypass membership, privacy, or Telegram access controls.
- The first scan checks up to the latest 200 messages per accessible group, limited to the last 30 days. Later scans check newer messages.
- A group title is not proof of the project/company name. Leads are deliberately labelled “Potential project (verify)” until a human verifies them.
- The signal matcher is rule-based, so every result must be reviewed before outreach. It is not an AI guarantee and may miss or misclassify messages.
- This worker is not deployed or running yet.

## Deploy prerequisites
A Render Background Worker with a persistent disk is described in the repository's root `render.yaml`. The Render `starter` worker plan and persistent disk are paid services. Do not deploy until the account owner approves the displayed price.

Required environment variables:
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`: from https://my.telegram.org.
- `SUPABASE_URL`: the AENZO Supabase project URL.
- `SUPABASE_SERVICE_ROLE_KEY`: server-side secret only. Never put it in browser code, GitHub, chat, or a public file.
- `SUPABASE_OWNER_ID`: the UUID of the signed-in Supabase user who owns the leads.
- `SESSION_FILE` and `STATE_FILE`: must remain on the persistent disk under `/data`.

## First Telegram authorization
1. Configure the environment variables in the private Render service settings.
2. Open the service's Shell and run: `cd /app && python worker.py --login`.
3. Enter the one-time login code only in that private Shell. If Telegram asks for the 2-step password, enter it only at the hidden password prompt. Never send either value to anyone.
4. Confirm that `/data/aenzo_telegram.session` exists on the persistent disk.
5. Start/restart the worker normally. The worker should log a scan summary every 10 minutes.

The session file grants access to the Telegram account. Keep it private, never commit it to GitHub, and revoke the session from Telegram's Devices settings if it is exposed.

## Local validation
```bash
python -m pip install -r requirements.txt
python -m py_compile worker.py
```


## Free scheduled runner (GitHub Actions)
A free GitHub Actions workflow is provided at `.github/workflows/telegram-scan.yml`. It runs one scan every 6 hours and can also be started manually from the repository's Actions tab. Standard GitHub-hosted runners are free for public repositories; GitHub Free private repositories include 2,000 Actions minutes per month. Usage beyond the allowance must not be enabled or purchased without the account owner's approval.

### One-time Telegram session setup
The workflow uses a Telethon StringSession stored as a GitHub Actions secret. Generate it on a trusted device:
```bash
python -m pip install -r telegram-worker/requirements.txt
python telegram-worker/session_login.py
``
Enter the API ID, API Hash, phone number, Telegram login code, and (if requested) 2-step password only in the private terminal. The script prints a session string. Treat it like the account password; never commit it or paste it into chat.

### Required GitHub Actions secrets
Add these in repository Settings → Secrets and variables → Actions:
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_STRING`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (server-side secret only)
- `SUPABASE_OWNER_ID`

The scheduled workflow scans groups only, excludes broadcast channels, and stores scan progress in the GitHub Actions cache. Each run is a one-shot scan; it does not require a continuously running server. It is not active until all secrets are configured and a successful manual run is verified.
