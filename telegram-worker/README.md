# AENZO LABS — Telegram Group Lead Hunter

## Purpose
This worker scans only Telegram group conversations that the account owner has already joined and can access. It excludes broadcast channels and does not bypass membership, privacy, or access controls.

It looks for public messages that appear to request AENZO LABS services, then stores:
- the original message text as evidence and its UTC date;
- a Telegram message link when that group type supports one;
- the sender's public Telegram username and any explicitly posted X, WhatsApp, email, Telegram, or website contact details; each is labelled as sourced from the message or author and is not independently verified;
- detected service categories, a conservative priority score, and English outreach with a Bengali meaning;
- a stable deduplication key that suppresses the same author's identical cross-posted request across groups, while keeping different authors and different requests separate.

A group title is not treated as a verified company name. Unverified identities are labelled **Potential project (verify)**. Every candidate needs human review before outreach.

## Accuracy and scan limits
- Detection uses a broader rule-based reading of natural group wording (recommendation requests, requests for help, partner searches, and service needs), not only exact service keywords. It is not a full language model: indirect, slang-heavy, multilingual, or context-dependent requests can still be missed or misclassified. Review every candidate before outreach.
- The first scan checks up to `MAX_MESSAGES_PER_GROUP` messages from the last `LOOKBACK_DAYS` days in each group.
- Messages are processed oldest-first. If a group has more than one batch of unseen messages, the next run continues from the saved cursor rather than skipping the backlog.
- If saving or resolving a candidate fails, that group's cursor is held so the failed message can be retried.
- The worker ignores messages sent by the account owner and bot accounts.
- No public username, project identity, or link is invented.

## Required private configuration
The scheduled GitHub Actions workflow needs these six repository secrets:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_STRING`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` — the modern Supabase `sb_secret_...` key, server-side only
- `SUPABASE_OWNER_ID`

The Supabase secret key is sent only in the `apikey` header. It is not a JWT and must not be sent as `Authorization: Bearer`.

Add or update secrets here:
https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/settings/secrets/actions

Never send API credentials, Telegram login codes, 2-step passwords, or the StringSession to ChatGPT, a public file, a screenshot, or a chat. A Telegram StringSession grants access to the Telegram account and must be treated like a password. A green preflight check only confirms the secret is present; the workflow separately validates its format and Telegram authorization.

## Telegram login helper
`telegram-worker/session_login.py` creates a StringSession in an interactive Python environment controlled by the account owner. It prompts privately for the API ID, API Hash, phone number, login code, and (if enabled) 2-step password, then prints the StringSession for the owner to add directly to the GitHub secret.

### Android phone setup using your own Termux app

If you already have Termux installed from its official F-Droid or GitHub distribution, you can create the session locally on your own Android phone. This is an owner-operated terminal process, not a no-code flow. Do not install Termux APKs from random websites, and do not paste the session into ChatGPT, Telegram chats, screenshots, or public files.

Run these commands one at a time in Termux:

```sh
pkg update -y
pkg install python git -y
git clone https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter.git
cd aenzo-lead-hunter/telegram-worker
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python session_login.py
```

The helper asks for your Telegram API ID, API Hash, phone number, login code, and (if enabled) 2-step password. Enter them only in your own Termux terminal. It then prints a private StringSession. Copy that value directly into the GitHub Actions secret named `TELEGRAM_SESSION_STRING` at the repository's [Actions secrets page](https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/settings/secrets/actions). Never send it to anyone. If a command fails, share only the error text with all phone numbers, codes, API values, and session strings removed.

After saving the secret, run the [AENZO Telegram Group Lead Scan workflow](https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/actions/workflows/telegram-scan.yml). A successful syntax check is not a real scan; confirm that the Telegram scan step itself completes.

If Termux cannot install the pinned dependencies or the Telegram login fails, stop and share the redacted error text. Do not switch to an untrusted runtime or pay for hosting.

## Run and verify
The workflow is:
https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/actions/workflows/telegram-scan.yml

It supports manual runs and a six-hour schedule. Each run scans once and exits; it does not keep a server running.

A green **Python syntax and dependency check** proves only that the code compiles and its rule tests pass. A green **AENZO Telegram Group Lead Scan** run proves a real scan only if the log shows that all credentials were configured, dependencies installed, and the Telegram scan step completed. A safe skip is not a scan.

Confirm saved records in the Supabase `public.leads` table.

## Optional hosting
The root `render.yaml` is an optional Render worker configuration using a paid instance. It is not required for GitHub Actions scanning. Do not deploy it or enable paid services without the owner's explicit approval.
