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

## One-time Telegram authorization (Android alternative to Colab)

If Google Colab is inconvenient, an Android phone can run the login helper locally with **Pydroid 3**. Pydroid 3 is listed on Google Play as an Android Python IDE with a pip package manager; the app listing also mentions in-app purchases, so do not buy Premium or any add-on for this project.

1. Install/open Pydroid 3 from Google Play: https://play.google.com/store/apps/details?id=ru.iiec.pydroid3
2. In Pydroid 3, open its **Pip** menu and install the exact package `Telethon==1.42.0`. Do not install optional native speed-up packages.
3. Download this repository file to your phone: https://raw.githubusercontent.com/leonhassn8787-ctrl/aenzo-lead-hunter/main/telegram-worker/session_login.py
4. Open the downloaded `session_login.py` in Pydroid 3 and run it.
5. Enter your Telegram API ID, API Hash, phone number with country code, and the login code in the local Pydroid console. Enter your Telegram 2-step password only if requested.
6. After successful login, the script prints a **Telegram StringSession**. Copy it directly into the GitHub Actions secret named `TELEGRAM_SESSION_STRING`.

The Pydroid route is a practical Android alternative, but it has not yet been tested on this specific phone. If Pydroid asks for a paid Premium feature, stop and do not pay. Do not send the login code, 2-step password, API Hash, or Session string in ChatGPT, Telegram chats, screenshots, or public files.

The optional Colab route remains available if preferred:
https://colab.research.google.com/github/leonhassn8787-ctrl/aenzo-lead-hunter/blob/main/telegram-worker/AENZO_Telegram_Login.ipynb

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
The free GitHub Actions route is the intended setup. The root `render.yaml` describes an optional paid worker and is not required. Do not deploy it or enable paid services without the owner's explicit approval.
