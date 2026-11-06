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

## One-time Telegram authorization (free route)
The repository includes an Android-compatible Google Colab notebook:
https://colab.research.google.com/github/leonhassn8787-ctrl/aenzo-lead-hunter/blob/main/telegram-worker/AENZO_Telegram_Login.ipynb

The notebook uses ordinary input prompts (not ipywidgets). Run its code cell. It asks privately for:
- Telegram API ID
- Telegram API Hash (hidden input)
- Phone number with country code
- Telegram login code (hidden input)
- Telegram 2-step verification password only if Telegram requests it

After successful authorization, it prints a **Telegram StringSession**. This string grants access to the Telegram account and must be treated like a password. Copy it directly into the GitHub Actions secret named `TELEGRAM_SESSION_STRING`. Never send it in chat, put it in a public file, or commit it to this repository.

If the notebook cannot run on the device, stop rather than repeatedly retrying. Do not use paid Codespaces or paid hosting for this project.

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
