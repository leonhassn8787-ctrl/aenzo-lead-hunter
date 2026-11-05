# AENZO LABS — Telegram Group Lead Hunter

## What it does
- Uses the owner's own Telegram account through Telethon (MTProto).
- Scans only group conversations the account has already joined and can access; excludes broadcast channels.
- Detects messages that appear to request services matching AENZO LABS.
- Stores the message evidence, date, group/message link, and a publicly visible sender username when available.
- Drafts English outreach with a Bengali meaning and deduplicates by Telegram group/message ID.

## Important limitations
- It cannot access private groups unless the account has already joined them.
- It does not bypass Telegram membership or privacy controls.
- The first scan checks up to 200 recent messages per accessible group within the last 30 days. Later runs check messages newer than the saved scan cursor.
- A group title is not proof of a project/company identity. Results are labelled “Potential project (verify)” and must be reviewed manually.
- Detection is rule-based, not an AI guarantee. It can miss or misclassify messages.
- The worker is not active until the required GitHub Actions secrets are configured and a manual scan succeeds.

## Free GitHub Actions runner
The repository is public. The workflow at `.github/workflows/telegram-scan.yml` can be run manually from the repository's **Actions** tab and is scheduled every six hours. GitHub documents standard hosted runners as free for public repositories. See https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job.

## Generate the Telegram session from an Android browser (no Termux)
A one-time Telegram StringSession is required. It acts like a password for the Telegram account.

1. Open https://github.com/codespaces/new?repo=leonhassn8787-ctrl/aenzo-lead-hunter in a browser and create a Codespace on the `main` branch using the smallest available machine.
2. Wait for the browser editor to open. Open **Terminal → New Terminal**.
3. Run:
   ```bash
   python -m pip install -r telegram-worker/requirements.txt
   python telegram-worker/session_login.py
   ```
4. Enter the Telegram API ID, API Hash, phone number, login code, and (if requested) 2-step password only in that Codespaces terminal. Never paste them into chat or a public file.
5. Copy the generated session string directly into the GitHub Actions secret named `TELEGRAM_SESSION_STRING`. Do not save it in the repository.
6. After saving the secret, stop and delete the Codespace if it is no longer needed. Do not continue if GitHub warns that the free Codespaces quota is exhausted or that paid usage would start. GitHub Free personal accounts currently include 120 core-hours and 15 GB-month of Codespaces storage; usage beyond the allowance can be billed if billing is enabled. See https://docs.github.com/en/billing/concepts/product-billing/github-codespaces.

## Required repository Actions secrets
Open repository **Settings → Secrets and variables → Actions → New repository secret** and add:
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_STRING`
- `SUPABASE_URL` (AENZO Supabase project URL)
- `SUPABASE_SERVICE_ROLE_KEY` (server-side secret only; never expose it in browser code, chat, or repository files)
- `SUPABASE_OWNER_ID` (the UUID of the Supabase user who should own the saved leads)

Do not send any of these values to anyone. Do not commit a Telegram session string or a Supabase service-role key.

## Run and verify
1. Open the repository's **Actions** tab.
2. Select **AENZO Telegram Group Lead Scan**.
3. Press **Run workflow** and confirm the branch is `main`.
4. Open the new run and check the job logs. A successful run should finish with a scan summary.
5. Confirm that new candidates are stored in the AENZO Supabase `leads` table.

The workflow runs once per invocation and exits; it does not keep a server running. Scan progress is saved in the Actions cache. It is not proven operational until the first manual run succeeds and a lead (or a zero-result scan) is verified.

## Paid Render option
The root `render.yaml` describes a paid Render worker. It is not needed for the free GitHub Actions route and must not be deployed unless the account owner explicitly approves its price.
