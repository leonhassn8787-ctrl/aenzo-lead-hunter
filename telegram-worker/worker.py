import asyncio
import hashlib
import getpass
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aenzo-telegram-worker")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE = os.getenv("TELEGRAM_PHONE", "").strip()
SESSION_FILE = Path(os.getenv("SESSION_FILE", "aenzo_telegram.session"))
SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING", "").strip()
STATE_FILE = Path(os.getenv("STATE_FILE", "/data/scan_state.json"))
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_OWNER_ID = os.environ["SUPABASE_OWNER_ID"]
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "600"))
MAX_MESSAGES_PER_GROUP = int(os.getenv("MAX_MESSAGES_PER_GROUP", "200"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "30"))

# Signals that indicate a project may need one or more AENZO services.
SIGNALS = {
    "KOL & Influencer Marketing": [
        r"looking for (kol|kols|influencer|influencers)",
        r"need (kols|influencers)", r"kol campaign", r"influencer campaign",
        r"(crypto|web3) influencer (marketing|campaign|promotion)",
    ],
    "Community Promotion": [
        r"looking for (community|telegram) (growth|promotion|marketing)",
        r"need (community|telegram) (growth|promotion|marketing)",
        r"need telegram community (growth|promotion|marketing)",
        r"grow our (telegram )?community", r"community growth (agency|partner|service)",
        r"telegram group promotion",
    ],
    "AMA Hosting & Engagement": [
        r"looking for ama", r"need ama (host|hosting|partner)",
        r"ama collaboration", r"(host|hosting) an ama",
    ],
    "PR & Media Visibility": [
        r"looking for pr", r"need pr (agency|service|support)",
        r"media coverage", r"press release", r"crypto pr (agency|services|campaign)",
    ],
    "Giveaways & Airdrops": [
        r"looking for (airdrop|giveaway) (partner|campaign|support)",
        r"need (airdrop|giveaway)", r"need (an? )?(airdrop|giveaway) campaign",
        r"(airdrop|giveaway) campaign (manager|partner|support)",
    ],
    "Content Distribution & Marketing": [
        r"looking for (content distribution|content marketing)",
        r"need (content distribution|content marketing)",
        r"content distribution (partner|service|agency)",
        r"looking for (marketing|content) agency",
    ],
    "Social Media Marketing": [
        r"need social media (marketing|management|promotion)",
        r"looking for social media (marketing|management|agency)",
        r"(manage|grow) our (twitter|x|social media)",
    ],
    "Project Promotion": [
        r"looking for (promotion|marketing) (agency|partner|service)",
        r"need project promotion", r"promote our project",
        r"looking for a marketing partner", r"project marketing campaign",
        r"upcoming launch (promotion|marketing)",
    ],
    "Website Design & Development": [
        r"looking for (web|website) (developer|development|agency)",
        r"need website (design|development)", r"build our website",
        r"website redesign (agency|developer|team)",
    ],
    "Recruitment": [
        r"looking for (community manager|moderator|developer)",
        r"hiring (community manager|moderator|developer)",
        r"need moderators", r"recruiting (community|telegram) moderators",
    ],
    "Video & Creative Production": [
        r"looking for (video|creative) (agency|team|partner)",
        r"need (promo video|video production)",
        r"looking for (motion graphics|video editing|graphic design)",
    ],
    "Project Review / VERDICT": [
        r"looking for (project|product) review", r"need testers",
        r"looking for beta testers", r"need (app|game|platform|website) testers",
        r"looking for product feedback",
    ],
    "Fundraising / Launch Promotion": [
        r"looking for (fundraising|launch) (marketing|promotion|partner)",
        r"need (fundraising|launch) promotion",
        r"pre[- ]launch marketing (agency|partner|support)",
    ],
    "AI / Automation Promotion": [
        r"looking for (ai|automation) (marketing|promotion|growth)",
        r"need (ai agent|bot|saas) (promotion|marketing|users|growth)",
        r"(promote|market) our (ai agent|trading bot|saas|automation tool)",
    ],
    "Exchange / Wallet Promotion": [
        r"looking for (exchange|wallet) (marketing|promotion|growth)",
        r"need (exchange|wallet) (users|promotion|marketing|community)",
        r"(promote|market) our (crypto )?(exchange|wallet)",
    ],
    "RWA / Trading Promotion": [
        r"looking for (rwa|tokenization|forex|trading) (marketing|promotion|community)",
        r"need (rwa|tokenization|forex|trading) (marketing|promotion|growth)",
    ],
    "GameFi / Casino Promotion": [
        r"looking for (gamefi|gaming|metaverse|casino) (marketing|promotion|kol|community)",
        r"need (gamefi|gaming|metaverse|casino) (promotion|marketing|users|community)",
    ],
    "Mining / Staking Promotion": [
        r"looking for (mining|staking) (marketing|promotion|community)",
        r"need (mining|staking) (users|promotion|marketing|community)",
    ],
}
COMPILED = {name: [re.compile(p, re.I) for p in patterns] for name, patterns in SIGNALS.items()}
BUYING_CONTEXT = re.compile(r"\b(looking for|need|seeking|hiring|searching for|want to hire|any recommendation|recommend a|partner with|agency|service provider)\b", re.I)
CRYPTO_CONTEXT = re.compile(r"\b(web3|crypto|blockchain|defi|cefi|token|wallet|exchange|launchpad|staking|mining|rwa|gamefi|metaverse|ai agent|trading|forex|telegram|airdrop|dapp|testnet)\b", re.I)
NON_BUYER_CONTEXT = re.compile(
    r"\b(looking for a job|need a job|seeking (a )?job|looking for work|available for work|"
    r"hire me|anyone hiring me|free airdrop|airdrop claim|claim (my )?airdrop|"
    r"token price prediction|price prediction|trading signals|wallet (is )?(not working|stuck)|"
    r"account (is )?(locked|suspended))\b",
    re.I,
)

def read_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}

def write_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE_FILE)

def classify(text):
    # Exclude common non-buyer chatter before applying service-intent rules.
    # This is deliberately conservative; uncertain messages are not promoted.
    if NON_BUYER_CONTEXT.search(text):
        return []
    hits = [name for name, patterns in COMPILED.items() if any(p.search(text) for p in patterns)]
    if not hits and BUYING_CONTEXT.search(text) and CRYPTO_CONTEXT.search(text):
        hits = ["Project Promotion"]
    if not hits or not (BUYING_CONTEXT.search(text) or any(x in text.lower() for x in ("looking for", "need ", "seeking", "hiring", "recommend"))):
        return []
    return hits

def make_message_url(entity, message_id):
    """Build only Telegram permalink formats supported by the group type."""
    public_name = getattr(entity, "username", None)
    if public_name:
        return f"https://t.me/{public_name}/{message_id}"
    if bool(getattr(entity, "megagroup", False)):
        return f"https://t.me/c/{entity.id}/{message_id}"
    return None


def is_human_sender(sender):
    """Return False for bot accounts; unknown senders remain reviewable."""
    return not bool(sender and getattr(sender, "bot", False))


def priority(text, hits):
    score = 48 + min(24, 8 * len(hits))
    if re.search(r"\b(budget|paid|payment|urgent|asap|ready to hire|dm me)\b", text, re.I):
        score += 15
    if re.search(r"\b(looking for|need|hiring|seeking)\b", text, re.I):
        score += 8
    return min(score, 95)

def dedupe(group_id, message_id):
    return hashlib.sha256(f"telegram:{group_id}:{message_id}".encode()).hexdigest()

def make_outreach(project, services):
    service_text = ", ".join(services[:3])
    en = (f"Hi! I noticed your message about {service_text}. "
          "AENZO LABS helps Web3 and crypto projects with growth, community promotion, "
          "KOL campaigns, PR, AMAs and tailored marketing. Would you be open to discussing "
          "your current goals and requirements?")
    bn = (f"হ্যালো! {service_text} বিষয়ে আপনার পোস্টটি দেখেছি। "
          "AENZO LABS Web3 ও ক্রিপ্টো প্রজেক্টকে কমিউনিটি প্রমোশন, KOL ক্যাম্পেইন, PR, AMA "
          "এবং কাস্টম মার্কেটিংয়ে সহায়তা করে। আপনার বর্তমান প্রয়োজন ও লক্ষ্য নিয়ে কি কথা বলা যাবে?")
    return en, bn

async def save_lead(client_http, payload):
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    url = f"{SUPABASE_URL}/rest/v1/leads"
    try:
        lookup = await client_http.get(
            url,
            headers=headers,
            params={
                "select": "id",
                "owner_id": f"eq.{SUPABASE_OWNER_ID}",
                "dedupe_key": "eq." + str(payload["dedupe_key"]),
                "limit": "1",
            },
            timeout=30,
        )
        if lookup.status_code != 200:
            log.warning("Supabase duplicate check failed (%s): %s", lookup.status_code, lookup.text[:300])
            return "error"
        if lookup.json():
            return "duplicate"
        response = await client_http.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in (200, 201):
            return "saved"
        # A concurrent scan may insert the same unique dedupe key after our
        # lookup. Treat the database's unique-conflict response as a duplicate.
        if response.status_code == 409:
            return "duplicate"
        log.warning("Supabase insert failed (%s): %s", response.status_code, response.text[:500])
        return "error"
    except Exception:
        log.exception("Supabase request failed; this message will be retried.")
        return "error"

async def login(client):
    await client.connect()
    if await client.is_user_authorized():
        log.info("Telegram session is already authorized.")
        return
    if not PHONE:
        raise RuntimeError("Set TELEGRAM_PHONE before first login.")
    sent = await client.send_code_request(PHONE)
    code = input("Enter the Telegram login code sent to your Telegram app: ").strip()
    try:
        await client.sign_in(phone=PHONE, code=code, phone_code_hash=sent.phone_code_hash)
    except SessionPasswordNeededError:
        password = getpass.getpass("Telegram 2-step verification password: ")
        await client.sign_in(password=password)
    log.info("Telegram account authorized. Keep the session file private.")

async def run(once=False):
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    client = (TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
              if SESSION_STRING else TelegramClient(str(SESSION_FILE), API_ID, API_HASH))
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("Telegram session is not authorized. Run 'python worker.py --login' in an interactive shell first.")
    state = read_state()
    async with httpx.AsyncClient() as http:
        while True:
            checked = 0
            saved = 0
            cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                # Only group conversations: exclude broadcast channels.
                is_group = bool(getattr(dialog, "is_group", False))
                if not is_group or bool(getattr(entity, "broadcast", False)):
                    continue
                group_id = str(entity.id)
                last_seen = int(state.get(group_id, 0))
                newest_seen = last_seen
                group_write_failed = False
                async for msg in client.iter_messages(entity, limit=MAX_MESSAGES_PER_GROUP, min_id=last_seen):
                    if not msg:
                        continue
                    # Advance past every Telegram update, including service and
                    # non-text messages, so quiet groups are not rescanned forever.
                    newest_seen = max(newest_seen, int(msg.id))
                    # Never treat messages sent by the account owner as client leads.
                    # The cursor still advances so the same own message is not rechecked.
                    if getattr(msg, "out", False):
                        continue
                    if not msg.message or not msg.date:
                        continue
                    if msg.date.replace(tzinfo=timezone.utc) < cutoff:
                        continue
                    text_body = msg.message.strip()
                    services = classify(text_body)
                    if not services:
                        continue
                    try:
                        sender = await msg.get_sender()
                    except Exception:
                        # Do not silently lose a lead if Telegram temporarily
                        # cannot resolve its author; retry this group's cursor.
                        log.exception("Could not resolve message author in group %s, message %s.", group_id, msg.id)
                        group_write_failed = True
                        continue
                    # Ignore bot-authored posts: they are often automated ads or
                    # scraper output, not a reliable expression of a buyer's intent.
                    if not is_human_sender(sender):
                        continue
                    username = getattr(sender, "username", None) if sender else None
                    group_name = (getattr(entity, "title", None) or "Telegram group").strip()
                    public_name = getattr(entity, "username", None)
                    # Private basic groups have no reliable permalink format.
                    group_url = make_message_url(entity, msg.id)
                    sender_contact = f"https://t.me/{username}" if username else None
                    project = f"Potential project (verify) — {group_name}"[:250]
                    en, bn = make_outreach(project, services)
                    payload = {
                        "owner_id": SUPABASE_OWNER_ID,
                        "company_name": project,
                        "website": None,
                        "industry": "Web3 / Crypto",
                        "service_need": "; ".join(services),
                        "lead_type": "potential_buyer",
                        "priority_score": priority(text_body, services),
                        "status": "new",
                        "evidence_summary": text_body[:3500],
                        "evidence_url": group_url,
                        "evidence_date": msg.date.astimezone(timezone.utc).date().isoformat(),
                        "telegram_group_url": f"https://t.me/{public_name}" if public_name else group_url,
                        "contacts": ([{"type": "telegram", "username": username, "url": sender_contact, "source": "message author"}] if username else []),
                        "outreach_english": en,
                        "outreach_bengali": bn,
                        "notes": "Automatically detected from a member-written Telegram group message. Verify project identity and need before outreach.",
                        "dedupe_key": dedupe(group_id, msg.id),
                    }
                    save_status = await save_lead(http, payload)
                    if save_status == "saved":
                        saved += 1
                    elif save_status == "error":
                        group_write_failed = True
                # Do not move this group's cursor past any message whose lead
                # could not be checked/saved; the next run will retry it.
                if not group_write_failed:
                    state[group_id] = max(last_seen, newest_seen)
                else:
                    log.warning("Keeping cursor unchanged for group %s so failed writes can be retried.", group_id)
                checked += 1
                if checked % 10 == 0:
                    write_state(state)
            write_state(state)
            log.info("Scan complete: %s groups checked; %s new leads saved.", checked, saved)
            if once:
                break
            await asyncio.sleep(POLL_SECONDS)

if __name__ == "__main__":
    if "--login" in sys.argv:
        async def do_login():
            client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
            await login(client)
            await client.disconnect()
        asyncio.run(do_login())
    else:
        asyncio.run(run(once="--once" in sys.argv))
