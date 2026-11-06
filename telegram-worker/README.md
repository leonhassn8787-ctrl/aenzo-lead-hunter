# AENZO LABS — Telegram Group Lead Hunter

## What it does
- Uses the owner's own Telegram account through Telethon (MTProto).
- Scans only group conversations the account has already joined and can access; excludes broadcast channels.
- Detects messages that appear to request AENZO LABS services.
- Stores the message text as evidence, UTC date, group/message link where available, and the message author's publicly visible Telegram username where available.
- Drafts English outreach with a Bengali meaning and deduplicates by Telegram group/message ID.
- Labels uncertain company identity as **Potential project (verify)**; a group title is never treated as verified company identity.

## Access and accuracy limits
- It cannot read private groups unless the Telegram account has already joined them.
- It does not bypass Telegram membership or privacy controls.
- The first scan checks up to 200 recent messages per accessible group within the last 30 days. Later runs use a saved per-group message cursor.
- Detection is rule-based and may miss or misclassify messages. Review each candidate before outreach.
- A public sender username is recorded only when Telegram exposes one. No usernames or project identities are invented.
- The worker is not operational until the required GitHub Actions secrets are configured and a manual scan succeeds.

## One-time Telegram authorization — browser only

Use GitHub Codespaces in your phone's browser. No Python app needs to be installed on the phone.

**Free-use warning:** GitHub personal accounts currently include a monthly Codespaces allowance (120 core-hours and 15 GB-month storage for Free accounts). If the allowance is exhausted, GitHub blocks additional usage unless billing is enabled. Do not add a payment method or enable spending for this project. If GitHub says the free allowance is unavailable, stop; do not pay.

1. Open this direct link while signed in to GitHub:
   https://github.com/codespaces/new?repo=1447576201
2. If GitHub offers a machine type, choose the smallest available option. Do not enable paid spending.
3. Wait for the browser-based VS Code workspace to open. The repository's devcontainer installs the Python dependencies automatically.
4. In the bottom Terminal panel, run:
   `python telegram-worker/session_login.py`
5. Enter your Telegram API ID, API Hash, phone number with country code, and the login code in the terminal. Enter your Telegram 2-step password only if requested.
6. The script prints a **Telegram StringSession**. Copy it directly into the GitHub Actions secret named `TELEGRAM_SESSION_STRING`.

If Codespaces fails to open or asks for payment, stop and tell us the exact message. Do not retry paid machine options. Do not send the login code, 2-step password, API Hash, or Session string in ChatGPT, Telegram chats, screenshots, or public files.

A Telegram StringSession grants access to the Telegram account and must be treated like a password. Never send it in chat, put it in a public file, or commit it to this repository.

## Required GitHub Actions secrets
Open:
https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/settings/secrets/actions

Add these six repository secrets (values must be obtained privately by the account owner):
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_STRING`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (server-side only; never expose in browser code, chat, or repository files)
- `SUPABASE_OWNER_ID`

The Supabase project URL and owner UUID are already known to the project owner. The Supabase service-role key must be copied from the project's API keys page and stored only as a GitHub secret:
https://supabase.com/dashboard/project/royezoicromoebaxqzhx/settings/api-keys

Do not send any secret to anyone, including the assistant.

## Free scheduled scanning
The workflow `.github/workflows/telegram-scan.yml` supports manual execution and a six-hour schedule using GitHub-hosted runners for this public repository. It checks that all six secrets exist before attempting a scan. Each run scans once and exits; it does not keep a server running.

After adding secrets:
1. Open the repository Actions tab: https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/actions
2. Select **AENZO Telegram Group Lead Scan**.
3. Select **Run workflow** on branch `main`.
4. Open the run and check whether the scan completed.
5. Confirm candidates in the Supabase `public.leads` table.

A successful syntax check is not proof that Telegram login or scanning works. Do not describe the system as active until a manual scan succeeds.

## Cost guard
The root `render.yaml` describes an optional paid worker and is not required. Do not deploy it or enable paid services without the owner's explicit approval.
