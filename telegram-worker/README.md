# AENZO LABS — Telegram Group Lead Hunter

## Purpose
This worker has two Telegram group discovery paths:

- **Joined groups:** scans new accessible messages in every group the account owner has already joined.
- **Non-joined public groups:** uses Telegram's user-only global group message search (messages.searchGlobal, with groups_only) to discover matching messages from accessible public groups without joining them. Search queries are focused on AENZO buyer-intent phrases; this is not an exhaustive dump of every public group or every message.

It does not bypass membership, privacy, or access controls. Private groups remain inaccessible unless the account is a member. Telegram may rate-limit global searches, and some public groups/messages may not appear in search.

It looks for messages that request AENZO LABS services or show a relevant Web3 growth/partnership need, then stores:
- the original message text as evidence and its UTC date;
- a Telegram message link when that group type supports one;
- the sender's public Telegram username and any explicitly posted X, WhatsApp, email, Telegram, or website contact details; each is labelled as sourced from the message or author and is not independently verified;
- detected service categories, a conservative priority score, and English outreach with a Bengali meaning;
- a stable deduplication key based on Telegram's numeric user ID: the same account is not sent as a second new lead, even if it changes username or posts again; different user IDs remain separate even when their wording is identical. If no numeric sender ID is available, the message is kept separate rather than guessing identity from a username.

A group title is not treated as a verified company name. Unverified identities are labelled **Potential project (verify)**. Every candidate needs human review before outreach.

## Accuracy and scan limits
- Detection accepts direct AENZO service requests and relevant Web3 project growth/partnership opportunities; an explicit budget or payment promise is not required. Generic crypto discussion, generic upcoming-token-launch signals, USDT/arbitrage/payment promotions, job-seeking, bot posts, free media/vendor offers, and agency self-advertising are excluded. Indirect growth problems are accepted only when marketing/audience/visibility context is present. This is rule-based, not a full language model: slang-heavy, multilingual, or context-dependent requests can still be missed or misclassified. Review every candidate before outreach.
- Each scan run processes at most `MAX_MESSAGES_PER_RUN` unique incoming messages across public search and joined groups (default 100). Public search runs first with its own `MAX_PUBLIC_MESSAGES_PER_RUN` budget (default 50), leaving capacity for joined groups in the same run. Both public-search cursors and joined-group message cursors are saved so the next two-hour run resumes where it stopped. The first joined-group scan checks accessible history from the last `LOOKBACK_DAYS` days. Each GitHub Actions run still has a 30-minute job timeout.
- Joined-group messages are processed oldest-first. The saved per-group message cursor resumes any remaining backlog on the next run.
- Global public-group searches run against a list of buyer-intent phrases. A per-query timestamp is saved only after all result pages complete, so an interrupted or rate-limited query is retried rather than silently skipped.
- The global search pass is incremental by query time and uses Telegram's regular global group search. It does not use the separate paid global public-channel post-search method.
- If saving or resolving a candidate fails, that group's cursor is held so the failed message can be retried.
- The worker ignores messages sent by the account owner, bot accounts, and anonymous group/channel identities that cannot be verified as a human user.
- No public username, project identity, or link is invented.

## Required private configuration
The scheduled GitHub Actions workflow needs these six repository secrets for scanning, plus two optional secrets for Telegram lead alerts:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_STRING`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` — the modern Supabase `sb_secret_...` key, server-side only
- `SUPABASE_OWNER_ID`
- `AENZO_BOT_TOKEN` — BotFather token for your private AENZO notification bot
- `AENZO_BOT_CHAT_ID` — your private chat ID with that bot

The Supabase secret key is sent only in the `apikey` header. It is not a JWT and must not be sent as `Authorization: Bearer`.

Add or update secrets here:
https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/settings/secrets/actions

Never send API credentials, Telegram login codes, 2-step passwords, or the StringSession to ChatGPT, a public file, a screenshot, or a chat. A Telegram StringSession grants access to the Telegram account and must be treated like a password. The workflow checks that all required secrets are present, validates the Telegram session format, then performs live checks that the Telegram account is authorized and the Supabase `public.leads` table is reachable with the configured key. The group scan runs only if those checks pass. A successful preflight is not itself proof that messages were scanned or leads were saved; confirm the scan log and inspect `public.leads` for new records.

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
python -m pip install -r requirements.txt
python session_login.py
```

The helper asks for your Telegram API ID, API Hash, phone number, login code, and (if enabled) 2-step password. Enter them only in your own Termux terminal. It then prints a private StringSession. Copy that value directly into the GitHub Actions secret named `TELEGRAM_SESSION_STRING` at the repository's [Actions secrets page](https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/settings/secrets/actions). Never send it to anyone. If a command fails, share only the error text with all phone numbers, codes, API values, and session strings removed.

After saving the secret, run the [AENZO Telegram Group Lead Scan workflow](https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/actions/workflows/telegram-scan.yml). A successful syntax check is not a real scan; confirm that the Telegram scan step itself completes. The GitHub Actions job tests the qualification rules before scanning. The scheduled worker currently uses `GLOBAL_SEARCH_MAX_PAGES=3` per date window, recursively splits saturated date windows, and caps each run at 100 unique messages. The GitHub Actions schedule is every two hours; the optional Render worker uses the same two-hour interval.

If Termux cannot install the pinned dependencies or the Telegram login fails, stop and share the redacted error text. Do not switch to an untrusted runtime or pay for hosting.

## Run and verify
The workflow is:
https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/actions/workflows/telegram-scan.yml

It supports manual runs and a two-hour schedule. Each run scans once and exits; it does not keep a server running. Use either GitHub Actions or the optional Render worker as the active scanner, not both, to avoid duplicate Telegram scanning and unnecessary rate-limit pressure. When `AENZO_BOT_TOKEN` and `AENZO_BOT_CHAT_ID` are configured, it sends saved leads whose status is `new` and whose `telegram_notified_at` is empty, with evidence, source link, public contacts, priority, and English/Bengali outreach. It sends up to 25 pending leads per scan; unsent alerts remain pending and are retried on later scans. **Existing records are not automatically marked as handled.** Before enabling bot alerts for the first time, review old records: any historical row still marked `new` with an empty notification timestamp will be sent. Rejected records are excluded.

A green **Python syntax and dependency check** proves only that the code compiles and its rule tests pass. A green **AENZO Telegram Group Lead Scan** run proves a real scan only if the log shows that all credentials were configured, dependencies installed, and the Telegram scan step completed. A safe skip is not a scan.

Confirm saved records in the Supabase `public.leads` table.

## Optional hosting
The root `render.yaml` is an optional Render worker configuration using a paid instance. It is not required for GitHub Actions scanning. Do not deploy it or enable paid services without the owner's explicit approval.
