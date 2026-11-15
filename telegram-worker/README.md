# AENZO LABS — Telegram Group Lead Hunter

## Purpose
This worker has exactly one discovery source: **groups the connected Telegram account has already joined**. It scans accessible messages in those groups only. It does not search non-joined public groups, channels, websites, directories, RSS feeds, or other external sources.

It does not bypass membership, privacy, or access controls. Only groups visible to the connected account can be scanned. Broadcast-only channels are excluded. Telegram may rate-limit message-history requests; saved per-group cursors allow the next run to resume.

It looks for messages that request AENZO LABS services or show a relevant Web3 growth/partnership need, then stores:
- the original message text as evidence and its UTC date;
- a Telegram message link when that group type supports one;
- the sender's public Telegram username and any explicitly posted X, WhatsApp, email, Telegram, or website contact details; each is labelled as sourced from the message or author and is not independently verified;
- detected service categories, a conservative priority score, and English outreach with a Bengali meaning;
- a stable deduplication key based on Telegram's numeric user ID: the same account is not sent as a second new lead, even if it changes username or posts again; different user IDs remain separate even when their wording is identical. If no numeric sender ID is available, the message is kept separate rather than guessing identity from a username.

A group title is not treated as a verified company name. Unverified identities are labelled **Potential project (verify)**. Every candidate needs human review before outreach.

## Accuracy and scan limits
- Detection accepts direct AENZO service requests and relevant Web3 project growth/partnership opportunities; an explicit budget or payment promise is not required. Generic crypto discussion, generic upcoming-token-launch signals, USDT/arbitrage/payment promotions, job-seeking, bot posts, free media/vendor offers, agency sales pitches (including influencer/streamer networks selling FTDs or traffic), affiliate/partner recruitment ads, and paid-promotion reseller recruitment are excluded. Indirect growth problems are accepted only when marketing/audience/visibility context is present. This is rule-based, not a full language model: slang-heavy, multilingual, or context-dependent requests can still be missed or misclassified. Review every candidate before outreach.
- Each GitHub Actions run selects up to 200 groups already joined by the connected Telegram account. If fewer than 200 groups are joined, it selects all of them. If more than 200 are joined, the selected set rotates between runs so other groups also get scanned.
- There is no fixed message-count cap per run and no per-group message cap. Each run checks messages whose Telegram timestamps fall strictly inside one two-hour window: window start inclusive, window end exclusive. The worker reads oldest-first and stops at the window end; it does not use old message-ID cursors to replay history.
- The two-hour windows are anchored at 2026-11-16 01:04:35 Saudi Arabia time. The first complete window is 01:04:35–03:04:35; the scheduled run at about 03:10 reports that window. The next run checks only 03:04:35–05:04:35, then 05:04:35–07:04:35, continuously.
- If a scheduled run is delayed or missed, expired windows are skipped and the worker checks only the latest completed two-hour window. If a run is interrupted or a message cannot be saved, that expired window is not replayed later; the scan report/log must be checked for failures. This deliberately follows the owner's no-old-backlog rule.
- Before scanning, the worker checks Supabase `scan_runs` for the exact `window_start`. A database unique index on `(owner_id, window_start)` makes claiming a window atomic, so overlapping runs cannot both scan it. Exact `window_start` and `window_end` are stored as timestamp columns. If another run already claimed that window—even if it was interrupted—the second run skips it. If Supabase cannot verify or record the window, scanning stops rather than risk an untracked duplicate.
- The post-scan buyer-evidence audit fetches every page of `new` leads before changing any status. This avoids skipping rows when more than 200 leads are waiting for audit; only after the complete audit succeeds are pending Telegram alerts considered.
- Up to 200 joined groups are selected per run, rotating the selected group set across runs when more than 200 groups are joined. Groups not selected in a particular run are not scanned in that window.
- The worker ignores messages sent by the account owner, bot accounts, and anonymous group/channel identities that cannot be verified as a human user.
- No public username, project identity, or link is invented.

## Required private configuration
The scheduled GitHub Actions workflow needs these six repository secrets for scanning joined groups only, plus two optional secrets for Telegram lead alerts:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_STRING`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` — the modern Supabase `sb_secret_...` key, server-side only
- `SUPABASE_OWNER_ID`
- `AENZO_BOT_TOKEN` — BotFather token for your private AENZO notification bot
- `AENZO_BOT_CHAT_ID` — your private chat ID with that bot
- At least one chat ID is required for automatic Telegram alerts. If the bot token is present but no chat ID is configured, scanning continues but alerts are disabled; the workflow now prints a warning.

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

After saving the secret, run the [AENZO Telegram Group Lead Scan workflow](https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/actions/workflows/telegram-scan.yml). A successful syntax check is not a real scan; confirm that the Telegram scan step itself completes. The GitHub Actions job tests the qualification rules before scanning. GitHub Actions selects up to 200 joined groups per run and has no fixed message-count cap. It runs every two hours at :10 Saudi Arabia time, checks only the latest completed two-hour message window, and has a 110-minute job timeout. The optional Render configuration is separate and should remain inactive while GitHub Actions is scanning, or duplicate scans and extra Telegram rate-limit pressure may result.

If Termux cannot install the pinned dependencies or the Telegram login fails, stop and share the redacted error text. Do not switch to an untrusted runtime or pay for hosting.

## Run and verify
The workflow is:
https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/actions/workflows/telegram-scan.yml

It supports manual runs and a two-hour schedule aligned to Saudi Arabia time. Each run scans up to 200 groups already joined by the connected Telegram account, with no fixed message-count cap, then exits; it does not keep a server running. Use either GitHub Actions or the optional Render worker as the active scanner, not both, to avoid duplicate Telegram scanning and unnecessary rate-limit pressure. When `AENZO_BOT_TOKEN` and at least one chat ID are configured, it sends saved leads whose status is `new` and whose `telegram_notified_at` is empty, with evidence, source link, public contacts, priority, and English/Bengali outreach. It loads all pending rows page by page without a fixed lead-count cap. Delivery is tracked separately for each configured chat using a one-way hash of the chat ID, so a successful recipient is not sent the same lead again just because another recipient failed. The overall notification timestamp is set only after every configured recipient has received the lead. Unsent recipients are retried on later scans. **Existing records are not automatically marked as handled.** Before enabling bot alerts for the first time, review old records: any historical row still marked `new` with an empty notification timestamp will be sent. Rejected records are excluded.

The scan window has a database-level unique guard. Per-chat lead alert delivery and scan-report delivery are recorded in Supabase; report delivery errors remain visible on the corresponding `scan_runs` row. A scan with message-save/author-resolution errors or a failed post-scan audit is marked `failed`, not cleanly completed. A green **Python syntax and dependency check** proves only that the code compiles and its rule tests pass. A green **AENZO Telegram Group Lead Scan** run proves a real scan only if the log shows that all credentials were configured, dependencies installed, and the Telegram scan step completed. A safe skip is not a scan.

Confirm saved records in the Supabase `public.leads` table.

## Optional hosting
The root `render.yaml` is an optional Render worker configuration using a paid instance. It is not required for GitHub Actions scanning. Do not deploy it or enable paid services without the owner's explicit approval.
