import asyncio
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aenzo-telegram-worker")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE = os.getenv("TELEGRAM_PHONE", "").strip()
SESSION_FILE = Path(os.getenv("SESSION_FILE", "/data/aenzo_telegram.session"))
STATE_FILE = Path(os.getenv("STATE_FILE", "/data/scan_state.json"))
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_OWNER_ID = os.environ["SUPABASE_OWNER_ID"]
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "600"))
MAX_MESSAGES_PER_GROUP = int(os.getenv("MAX_MESSAGES_PER_GROUP", "200"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "30"))

# Signals that indicate a project may need one or more AENZO services.
SIGNALS = {
    "KOL & Influencer Marketing": [r"looking for (kol|influencer)", r"need (kols|influencers)", r"kol campaign", r"influencer campaign"],
    "Community Promotion": [r"looking for (community|telegram) (growth|promotion|marketing)", r"need (community|telegram) (growth|promotion)", r"grow our community"],
    "AMA Hosting & Engagement": [r"looking for ama", r"need ama (host|hosting|partner)", r"ama collaboration"],
    "PR & Media Visibility": [r"looking for pr", r"need pr (agency|service|support)", r"media coverage", r"press release"],
    "Giveaways & Airdrops": [r"looking for (airdrop|giveaway) (partner|campaign|support)", r"need (airdrop|giveaway)"],
    "Content & Social Media Marketing": [r"looking for (marketing|content) agency", r"need (social media|content) marketing", r"marketing partner"],
    "Project Promotion": [r"looking for (promotion|marketing) (agency|partner|service)", r"need project promotion", r"promote our project"],
    "Website Design & Development": [r"looking for (web|website) (developer|development|agency)", r"need website (design|development)", r"build our website"],
    "Recruitment": [r"looking for (community manager|moderator|developer)", r"hiring (community manager|moderator|developer)", r"need moderators"],
    "Video & Creative Production": [r"looking for (video|creative) (agency|team|partner)", r"need (promo video|video production)"],
    "Project Review / VERDICT": [r"looking for (project|product) review", r"need testers", r"looking for beta testers"],
}
COMPILED = {name: [re.compile(p, re.I) for p in patterns] for name, patterns in SIGNALS.items()}
BUYING_CONTEXT = re.compile(r"\b(looking for|need|seeking|hiring|searching for|want to hire|any recommendation|recommend a|partner with|agency|service provider)\b", re.I)
CRYPTO_CONTEXT = re.compile(r"\b(web3|crypto|blockchain|defi|cefi|token|wallet|exchange|launchpad|staking|mining|rwa|gamefi|metaverse|ai agent|trading|forex|telegram|airdrop|dapp|testnet)\b", re.I)

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
    hits = [name for name, patterns in COMPILED.items() if any(p.search(text) for p in patterns)]
    if not hits and BUYING_CONTEXT.search(text) and CRYPTO_CONTEXT.search(text):
        hits = ["Project Promotion"]
    if not hits or not (BUYING_CONTEXT.search(text) or any(x in text.lower() for x in ("looking for", "need ", "seeking", "hiring", "recommend"))):
        return []
    return hits

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
        return False
    if lookup.json():
        return False
    response = await client_http.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code in (200, 201):
        return True
    log.warning("Supabase insert failed (%s): %s", response.status_code, response.text[:500])
    return False

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
        password = input("Enter your Telegram 2-step verification password (input hidden by terminal if supported): ")
        await client.sign_in(password=password)
    log.info("Telegram account authorized. Keep the session file private.")

async def run():
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
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
                async for msg in client.iter_messages(entity, limit=MAX_MESSAGES_PER_GROUP, min_id=last_seen):
                    if not msg or not msg.message or not msg.date:
                        continue
                    if msg.date.replace(tzinfo=timezone.utc) < cutoff:
                        continue
                    newest_seen = max(newest_seen, int(msg.id))
                    text_body = msg.message.strip()
                    services = classify(text_body)
                    if not services:
                        continue
                    sender = await msg.get_sender()
                    username = getattr(sender, "username", None) if sender else None
                    group_name = (getattr(entity, "title", None) or "Telegram group").strip()
                    public_name = getattr(entity, "username", None)
                    if public_name:
                        group_url = f"https://t.me/{public_name}/{msg.id}"
                    else:
                        raw_id = str(entity.id)
                        group_url = f"https://t.me/c/{raw_id}/{msg.id}" if raw_id else None
                    sender_contact = f"https://t.me/{username}" if username else None
                    project = group_name[:250]
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
                        "evidence_date": msg.date.astimezone(timezone.utc).isoformat(),
                        "telegram_group_url": f"https://t.me/{public_name}" if public_name else group_url,
                        "contacts": ([{"type": "telegram", "username": username, "url": sender_contact, "source": "message author"}] if username else []),
                        "outreach_english": en,
                        "outreach_bengali": bn,
                        "notes": "Automatically detected from a member-written Telegram group message. Verify project identity and need before outreach.",
                        "dedupe_key": dedupe(group_id, msg.id),
                    }
                    if await save_lead(http, payload):
                        saved += 1
                state[group_id] = max(last_seen, newest_seen)
                checked += 1
                if checked % 10 == 0:
                    write_state(state)
            write_state(state)
            log.info("Scan complete: %s groups checked; %s new leads saved.", checked, saved)
            await asyncio.sleep(POLL_SECONDS)

if __name__ == "__main__":
    if "--login" in sys.argv:
        async def do_login():
            client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
            await login(client)
            await client.disconnect()
        asyncio.run(do_login())
    else:
        asyncio.run(run())
