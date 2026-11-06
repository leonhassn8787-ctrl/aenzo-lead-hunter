# AENZO LABS — Telegram Group Lead Hunter

## Purpose
This worker scans only Telegram group conversations that the account owner has already joined and can access. It excludes broadcast channels and does not bypass membership, privacy, or access controls.

It looks for public messages that appear to request AENZO LABS services, then stores:
- the original message text as evidence and its UTC date;
- a Telegram message link when that group type supports one;
- the sender's public Telegram username only when Telegram exposes it;
- detected service categories, a conservative priority score, and English outreach with a Bengali meaning;
- a stable deduplication key.

A group title is not treated as a verified company name. Unverified identities are labelled **Potential project (verify)**. Every candidate needs human review before outreach.

## Accuracy and scan limits
- Detection is rule-based. It can miss real requests and may flag irrelevant messages.
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

Never send API credentials, Telegram login codes, 2-step passwords, or the StringSession to ChatGPT, a public file, a screenshot, or a chat. A Telegram StringSession grants access to the Telegram account and must be treated like a password.

## Telegram login helper
`telegram-worker/session_login.py` creates a StringSession in an interactive Python environment controlled by the account owner. It prompts privately for the API ID, API Hash, phone number, login code, and (if enabled) 2-step password, then prints the StringSession for the owner to add directly to the GitHub secret.

There is currently no verified phone-only, no-code login path in this repository. Do not use Codespaces, Colab, Termux, Pydroid, or a paid runtime as a workaround. If no trusted computer or suitable private runtime is available, leave `TELEGRAM_SESSION_STRING` unset until a safe login method is available. The scanner will safely skip until all six secrets exist.

## Run and verify
The workflow is:
https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/actions/workflows/telegram-scan.yml

It supports manual runs and a six-hour schedule. Each run scans once and exits; it does not keep a server running.

A green **Python syntax and dependency check** proves only that the code compiles and its rule tests pass. A green **AENZO Telegram Group Lead Scan** run proves a real scan only if the log shows that all credentials were configured, dependencies installed, and the Telegram scan step completed. A safe skip is not a scan.

Confirm saved records in the Supabase `public.leads` table.

## Optional hosting
The root `render.yaml` is an optional Render worker configuration using a paid instance. It is not required for GitHub Actions scanning. Do not deploy it or enable paid services without the owner's explicit approval.
