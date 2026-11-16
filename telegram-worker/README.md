# AENZO LABS — Telegram Group Lead Hunter

## What it scans

The worker scans **only Telegram groups that the connected Telegram account has already joined and can access**. It does not search non-joined groups, channels, websites, RSS feeds, or external directories. Broadcast-only channels are excluded. It does not bypass Telegram membership or privacy controls.

It scans every available joined group in each two-hour message window. There is **no group-count cap and no message-count cap**. The two-hour setting defines the message collection window and polling cadence; it is not a limit on scan duration. If processing takes longer than two hours, the worker finishes the current window and then continues in order.

## Reliability and recovery

- Each window is stored in Supabase `public.scan_runs`.
- A persistent JSON state file on the Render disk stores each group's last successfully processed message ID.
- The worker writes its checkpoint after each message is successfully processed. If saving a lead or resolving a required sender fails, the cursor does not advance past that message.
- Interrupted or failed windows are resumed from their last saved group/message checkpoint. A window is not marked complete or advanced until every currently accessible joined group is processed and the post-scan evidence audit succeeds.
- Completed windows are skipped safely. Running or failed windows are reused rather than treated as complete.
- Before each window, the worker reconciles its local next-window cursor against the Supabase completed-window ledger. If an earlier two-hour window is missing, it rewinds to the earliest uncompleted window and backfills it instead of silently jumping ahead.
- Telegram FloodWait errors are respected for the full server-requested wait plus a small safety margin. Other transient errors retry with a delay.
- The Render disk mounted at `/data` is required to preserve the Telegram session and scan checkpoints across restarts.

The first window is anchored by `INITIAL_SCAN_START_AT` in `render.yaml`. Do not change that value after scanning has started unless intentionally resetting the scan timeline and reconciling the saved state.

## Lead quality and deduplication

The classifier looks for project-side requests for AENZO services, including KOL/influencer campaigns, community promotion, AMA hosting, PR/media visibility, giveaways/airdrops, content distribution, social media marketing, project promotion, website development, recruitment, promotional video/creative work, product testing/VERDICT, AI/automation, exchange/wallet, RWA/trading, GameFi, and mining/staking promotion.

It rejects or holds service sellers, agencies advertising their own services, traffic/lead vendors, job seekers, generic crypto discussion, funding-only or liquidity-only requests, and unrelated posts. Ambiguous candidates are retained in the manual `review` queue rather than silently discarded. The classifier is rule-based; slang, multilingual posts, and context-dependent messages can still need human review.

The worker does not invent a project name, public username, email, website, or contact link. A Telegram username is included only when it is publicly available from the message author or explicitly written in the message. Group title is not treated as a verified company identity. Candidates are labelled as potential projects and should be checked before outreach.

Deduplication uses the sender's numeric Telegram user ID when available, so one account is not sent repeatedly as a new lead even if it changes username or posts in multiple groups. If no numeric sender ID is available, the worker uses the message identity rather than guessing that two people are the same person.

## Telegram notifications

Only leads that pass the post-scan buyer-evidence audit can be sent as lead alerts. The notification gate checks the original evidence again and blocks seller/vendor posts. Each configured recipient has separate delivery tracking so a successful delivery is not repeated just because another recipient failed. Failed recipients are retried later.

The scan report records joined groups and messages processed, buyer signals, saved leads, duplicates, audit results, alert delivery, errors, and scan duration. Scan-report delivery is tracked separately from lead alerts.

## Deployment and configuration

The intended production scanner is the **Render Background Worker** defined in the root `render.yaml`. **It is not currently deployed or running.** Render requested payment information during Blueprint planning, so the paid service was deliberately left unapproved. No payment or deployment has been made. GitHub Actions is intentionally test-only: it runs syntax, dependency, and regression checks, but it does not scan Telegram or send lead alerts. Do not add a second scheduled live scanner, because two independent workers would not share the same checkpoint file.

**Use the existing Telegram account and existing AENZO alert bot from the previous setup. Do not create a new Telegram account, bot, login session, or chat destination.** When the worker is deployed later, transfer/reuse the already-created account's existing session and the same bot credentials privately in Render's environment settings. The values are intentionally not stored in this repository or exposed in chat.

Required Render environment variables (populate with the existing values):

- `TELEGRAM_API_ID` — same Telegram app/API ID already used.
- `TELEGRAM_API_HASH` — same Telegram app/API hash already used.
- `TELEGRAM_SESSION_STRING` — the existing account's session string; alternatively, mount/copy its already-authenticated session file to the persistent disk. Do not run a new login unless the existing session is confirmed unavailable and the user explicitly approves.
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (server-side secret key only)
- `SUPABASE_OWNER_ID`

Existing AENZO bot notifications (reuse the already connected bot and same private chat):

- `AENZO_BOT_TOKEN` — existing bot token.
- `AENZO_BOT_CHAT_ID` — existing primary private chat ID.
- `AENZO_BOT_CHAT_IDS` — only if additional destinations were already configured; do not add new chats.

Other settings:

- `POLL_SECONDS=7200` — two-hour worker polling interval.
- `INITIAL_SCAN_START_AT` — fixed initial UTC anchor configured in `render.yaml`.
- `STATE_FILE=/data/scan_state.json` and `SESSION_FILE=/data/aenzo_telegram.session`.
- `LOOKBACK_DAYS` — retained as a bounded configuration setting; window progression is driven by the persisted anchor and checkpoints.

Never share Telegram API credentials, login codes, two-step passwords, bot tokens, Supabase service-role keys, or StringSession values in chat, screenshots, source control, or public files. A Telegram StringSession grants access to the Telegram account and must be protected like a password.

## Android / Termux session setup

The previous Telegram account/session must be reused. Do not run `session_login.py` or request a new login code as part of the normal deployment. If the already-authenticated session is only present as a Termux `.session` file, securely transfer that existing file to the Render persistent disk; if its existing StringSession is already available, use that same value in Render's private environment settings. If neither existing form can be located, stop and ask the user before attempting any new Telegram login.

## Tests and verification

GitHub Actions runs the regression suite on pushes, pull requests, and manual test runs. It does not run the production scanner. A passing test suite confirms code behaviour only; it does not prove that Render is deployed or that Telegram is connected.

For live verification, check the Render worker deployment and logs, then confirm fresh completed rows in Supabase `public.scan_runs`. A successful window should show all currently accessible joined groups processed, no scan errors, and a successful post-scan audit.
