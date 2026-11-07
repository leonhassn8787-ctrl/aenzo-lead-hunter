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
BOT_TOKEN = os.getenv("AENZO_BOT_TOKEN", "").strip()
BOT_CHAT_ID = os.getenv("AENZO_BOT_CHAT_ID", "").strip()
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "600"))
MAX_MESSAGES_PER_GROUP = int(os.getenv("MAX_MESSAGES_PER_GROUP", "200"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "30"))

# Signals that indicate a project may need one or more AENZO services.
SIGNALS = {
    "KOL & Influencer Marketing": [
        r"looking for (kol|kols|influencer|influencers)",
        r"searching for (kol|kols|influencer|influencers)",
        r"want to hire (kol|kols|influencer|influencers)",
        r"looking to hire (an? )?(external )?(kol|influencer|marketing|growth) (agency|team)",
        r"need help with (our )?(kol|influencer) campaign",
        r"need (kols|influencers)", r"kol campaign", r"influencer campaign",
        r"(crypto|web3) influencer (marketing|campaign|promotion)",
        r"anyone know (a |any )?(good )?(kol|influencer|influencers)",
        r"(need|looking for) someone to (run|manage) (our )?(kol|influencer) campaign",
    ],
    "Community Promotion": [
        r"looking for (community|telegram) (growth|promotion|marketing)",
        r"need (community|telegram) (growth|promotion|marketing)",
        r"need telegram community (growth|promotion|marketing)",
        r"grow our (telegram )?community", r"community growth (agency|partner|service)",
        r"telegram group promotion",
        r"help us grow (our )?(telegram )?community",
        r"(telegram|community) (group )?(is )?(quiet|inactive|small).*(grow|users|members|engagement)",
        r"anyone know (a |any )?(community growth|telegram promotion) (agency|team|partner)",
    ],
    "AMA Hosting & Engagement": [
        r"looking for ama", r"need ama (host|hosting|partner)",
        r"ama collaboration", r"(host|hosting) an ama",
    ],
    "PR & Media Visibility": [
        r"looking for pr", r"need pr (agency|service|support)",
        r"media coverage", r"press release", r"crypto pr (agency|services|campaign)",
        r"get (our )?(project|brand|token) featured", r"need more media exposure",
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
        r"help us grow our (twitter|x) account",
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
        r"need someone to (build|design|develop) our website",
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
        r"looking for (promotion|marketing) for our (ai agent|trading bot|saas|automation tool)",
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
BUYING_CONTEXT = re.compile(r"\b(struggling to (get|attract|reach|grow|increase)|having trouble (getting|attracting|reaching|growing)|not getting (enough|many) (users|registrations|signups|members|engagement|traction)|could use more|how can we (get|attract|reach|grow|increase)|what.s the best way to (get|attract|reach|grow|increase)|looking for|looking to work with|looking to grow|looking to increase|looking to boost|looking to attract|looking to reach|looking to get|in search of|trying to find|trying to grow|trying to increase|trying to reach|want to grow|want to increase|want to boost|want to attract|want to reach|need|needs|need more|seeking|hiring|searching for|want to hire|want someone to|need someone to|need a team|need a hand|any recommendation|recommend a|recommendations for|can anyone recommend|anyone know|does anyone know|who can help|can anyone help|anyone able to|someone who can|anyone experienced in|could use|need help with|help us|partner with|any agency|suggest a)\b", re.I)
CRYPTO_CONTEXT = re.compile(r"\b(web3|crypto|blockchain|defi|cefi|token|wallet|exchange|launchpad|staking|mining|rwa|gamefi|metaverse|ai agent|trading|forex|telegram|airdrop|dapp|testnet)\b", re.I)
# Posts selling tools, accounts, traffic, or services are vendors—not buyers.
# This catches ads that contain phrases such as "looking for an account" while
# the author is actually offering rentals or inventory.
SELLER_AD_CONTEXT = re.compile(
    r"\b("
    r"rental\s*(\+|and|&)\s*purchase options|"
    r"(meta|tiktok|facebook|google) ads? accounts? (for rent|available|for sale)|"
    r"(account|accounts) (rental|rentals|for rent|for purchase|for sale)|"
    r"(i|we) have .{0,100} (options|accounts|services|packages) available|"
    r"(available|offering) (rental|rent|purchase) options|"
    r"dm me your (platform|niche).{0,80}(check|confirm) availability|"
    r"(rent|rental|lease|purchase) options available|"
    r"we help (advertisers|businesses|brands|clients|agencies)|"
    r"available support.{0,250}(ad account|campaign|tracking|landing.page|advertising)|"
    r"ad account setup|campaign creation.{0,40}optimization|"
    r"tracking.{0,40}conversion setup|landing.page configuration|"
    r"technical advertising support|whatsapp api|"
    r"whatsapp messaging.{0,30}marketing tools|meta.{0,15}google ads solutions|"
    r"tiktok ads accounts|blue tick solutions|fresh facebook accounts|"
    r"bm[0-9]{1,4}\b|from 5 to 1,000 ad accounts|"
    r"fast setup.{0,50}scalable solutions|"
    r"stop struggling to find the right business tools|"
    r"for serious advertising projects"
    r")\b",
    re.I,
)

SELLER_POST_CONTEXT = re.compile(
    r"\b(we (offer|provide|specialize in|are offering|can provide)|"
    r"our (agency|company|team) (offers|provides|specializes in|is offering)|"
    r"available for paid promotions|kol services available|"
    r"marketing packages available|dm us for rates|contact us for pricing)\b",
    re.I,
)

NON_BUYER_CONTEXT = re.compile(
    r"\b(looking for a job|need a job|seeking (a )?job|looking for work|available for work|"
    r"hire me|anyone hiring me|free airdrop|airdrop claim|claim (my )?airdrop|"
    r"token price prediction|price prediction|trading signals|wallet (is )?(not working|stuck)|"
    r"account (is )?(locked|suspended)|"
    r"we (offer|provide|specialize in|are offering|can provide|can help (with|you))|"
    r"we are (a|an) [a-z -]{1,50}(agency|service provider|marketing team|growth team|pr firm)|"
    r"our (agency|company|team) (offers|provides|specializes in|is offering|can provide)|"
    r"(dm|message|contact) (me|us) (for|to get) (rates|pricing|packages|details|collaboration)|"
    r"(our|my) (services|packages|plans|rates|pricing) (include|start|are|for)|"
    r"(available|open) for (collaborations|partnerships|paid promotions|promo| ama|marketing campaigns)|"
    r"(kol|influencer|shilling|marketing|promotion|pr|ama|community management|social media) (services|packages|agency|team|campaigns) (available|offered|provided)|"
    r"(we have|we run|we manage) (a )?(large )?(telegram )?(community|network|influencer network|kol network) (for|to promote|promotion)|"
    r"(promote|promotion|shill|advertise) your (project|token|coin|brand|website|app) (with|through|via) (us|our)|"
    r"we help (web3|crypto|blockchain) projects|"
    r"verified leads|high-converting.*leads|lead categories|country-targeted leads|"
    r"phone and email leads|phone & email leads|order today.*leads|"
    r"available tokens on pinksale|pinksale presale|marketing tax|marketing wallet|"
    r"recommended developers|create a (standard|baby|buyback) token|"
    r"buy(s|ing)? usdt|sell(ing)? usdt|usdt arbitrage|arbitrage partner|"
    r"cash deposits|hacker funds?|mixed funds?|equity funds?|gaming funds?|"
    r"upi/?imps|cash app transfer|paypal transfer|bank transfer|"
    r"cloned cards?|linkables?|fullz|bank drops?|carding|cvv|"
    r"exchange rate premium|daily demand for usdt|daily earnings|"
    r"large number of (indian )?customers|"
    r"welcome to .{0,80}partner.{0,40}pinksale|"
    r"recognized with kyc,? audit and doxx badge)\b",
    re.I,
)

def read_state():
    """Load versioned scan state and migrate the previous flat cursor map safely."""
    try:
        raw = json.loads(STATE_FILE.read_text())
    except Exception:
        raw = {}
    if isinstance(raw, dict) and raw.get("version") == 2 and isinstance(raw.get("groups"), dict):
        return raw
    groups = {}
    if isinstance(raw, dict):
        for group_id, last_seen in raw.items():
            try:
                groups[str(group_id)] = {
                    "last_seen_id": max(0, int(last_seen)),
                    "messages_seen": 0,
                    "seller_ads": 0,
                    "buyer_signals": 0,
                    "qualified_leads": 0,
                    "paused_until": None,
                }
            except (TypeError, ValueError):
                continue
    return {"version": 2, "groups": groups}

def write_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE_FILE)

def group_priority(meta):
    """Prefer groups with proven buyer signals while mildly penalizing vendor-heavy groups."""
    return (
        min(int(meta.get("qualified_leads", 0)), 100) * 100
        + min(int(meta.get("buyer_signals", 0)), 200) * 10
        - min(int(meta.get("seller_ads", 0)), 200)
    )

def should_pause_group(meta):
    """Only snooze a group after a meaningful sample dominated by seller ads."""
    messages = int(meta.get("messages_seen", 0))
    sellers = int(meta.get("seller_ads", 0))
    qualified = int(meta.get("qualified_leads", 0))
    return qualified == 0 and messages >= 200 and sellers / max(messages, 1) >= 0.35

def classify(text):
    """Return only messages with a clear request for an AENZO-relevant service."""
    if not text or NON_BUYER_CONTEXT.search(text) or SELLER_AD_CONTEXT.search(text):
        return []

    # Technical hiring/help (e.g. token launch specialists) is not automatically
    # a marketing lead. Keep these out unless a separate marketing request exists.
    technical_only = re.compile(
        r"\b(specialist|specialists|developer|developers|programmer|programmers|"
        r"auditor|auditors|smart contract|solidity|transfer hook|token[- ]?2022|"
        r"rpc|node operator|liquidity provider|market maker|arbitrage|"
        r"buy usdt|sell usdt|usdt exchange|cash deposit|cvv|carding)\b",
        re.I,
    )
    marketing_intent = re.compile(
        r"\b(kol|kols|influencer|influencers|marketing|promotion|promote|"
        r"community growth|community promotion|pr agency|media coverage|"
        r"press release|ama hosting|giveaway campaign|airdrop campaign|"
        r"social media management|content marketing|content distribution|"
        r"brand awareness|user acquisition|grow our audience|increase visibility|audience|user base|users|traction|attract users|more users|signups|registrations|"
        r"launch promotion|project promotion|advertising|paid campaign)\b",
        re.I,
    )
    buyer_intent = re.compile(
        r"\b(looking for|looking to hire|searching for|seeking|need|needs|want to hire|"
        r"hiring|want to work with|looking to work with|need help with|"
        r"can anyone recommend|does anyone know|anyone know|who can help|"
        r"can someone help|anyone able to|partner with|could use|"
        r"struggling to|not getting enough|trying to increase|"
        r"trying to grow|want to grow|want to increase|want to attract)\b",
        re.I,
    )

    hits = [
        name for name, patterns in COMPILED.items()
        if any(pattern.search(text) for pattern in patterns)
    ]

    # A named AENZO service plus explicit buyer language is required.
    # Indirect growth-pain messages are accepted only when the text clearly
    # mentions marketing, visibility, audience, acquisition, or promotion.
    indirect_growth = (
        re.search(
            r"\b(struggling to|having trouble|not getting (enough|many)|"
            r"trying to (increase|grow|attract|reach)|want to (grow|increase|attract|reach)|"
            r"could use more|how can we (get|attract|reach|grow|increase)|"
            r"what.s the best way to (get|attract|reach|grow|increase))\b",
            text,
            re.I,
        )
        and marketing_intent.search(text)
    )
    if not buyer_intent.search(text) and not indirect_growth:
        return []

    # Do not turn technical token-launch requests into marketing prospects.
    if technical_only.search(text) and not marketing_intent.search(text):
        return []

    if not hits and marketing_intent.search(text):
        hits = ["Project Promotion"]

    return hits

def make_message_url(entity, message_id):
    """Build only Telegram permalink formats supported by the group type."""
    public_name = getattr(entity, "username", None)
    if public_name:
        return f"https://t.me/{public_name}/{message_id}"
    if bool(getattr(entity, "megagroup", False)):
        return f"https://t.me/c/{entity.id}/{message_id}"
    return None


def extract_public_contacts(message_text, sender_username=None):
    """Extract only contact details explicitly visible in the message or sender profile."""
    contacts = []
    seen = set()

    def add(kind, value, url=None, source="message text"):
        identity = (kind, value.casefold())
        if value and identity not in seen:
            seen.add(identity)
            item = {"type": kind, "value": value, "source": source}
            if url:
                item["url"] = url
            contacts.append(item)

    if sender_username:
        add("telegram", "@" + sender_username, "https://t.me/" + sender_username, "message author")

    # Capture explicitly written Telegram handles in the message body as well
    # as the author; never infer handles from project or company names.
    for handle in re.findall(r"(?<![\w/])@([A-Za-z][A-Za-z0-9_]{4,31})", message_text or ""):
        add("telegram", "@" + handle, "https://t.me/" + handle, "message text")

    urls = re.findall(r"https?://[^\s<>()]+", message_text or "", flags=re.I)
    for raw_url in urls:
        url = raw_url.rstrip(".,;:!?)]}")
        if re.search(r"(?:^|//)(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,15})(?:[/?#]|$)", url, re.I):
            add("x", url, url)
        elif re.search(r"(?:^|//)(?:www\.)?(?:wa\.me|api\.whatsapp\.com)/", url, re.I):
            add("whatsapp", url, url)
        elif re.search(r"(?:^|//)(?:www\.)?t\.me/([A-Za-z][A-Za-z0-9_]{4,})(?:[/?#]|$)", url, re.I):
            add("telegram", url, url)
        elif not re.search(r"(?:^|//)(?:www\.)?(?:x\.com|twitter\.com|t\.me|wa\.me|api\.whatsapp\.com)/", url, re.I):
            add("website", url, url)

    for email in re.findall(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", message_text or "", flags=re.I):
        add("email", email)

    return contacts


def is_human_sender(sender):
    """Only accept a resolved, non-bot Telegram sender."""
    return sender is not None and not bool(getattr(sender, "bot", False))


def priority(text, hits):
    """Conservative 0-100 ranking; score reflects evidence, not certainty."""
    score = 35
    if re.search(r"\b(looking for|looking to work with|looking to grow|looking to increase|trying to find|trying to grow|want to grow|want to increase|need|needs|seeking|hiring|want to hire|want someone to|need someone to|searching for|anyone know|does anyone know|can anyone recommend|can anyone help|anyone able to|need help with|help us|partner with)\b", text, re.I):
        score += 20
    if re.search(r"\b(budget|paid|payment|pricing|quote|rates|cost)\b", text, re.I):
        score += 15
    if re.search(r"\b(urgent|asap|this week|immediately|ready to hire)\b", text, re.I):
        score += 10
    if re.search(r"\b(dm me|contact me|send proposal|share your portfolio)\b", text, re.I):
        score += 10
    # Multiple independently matched service categories add only a small bonus.
    score += min(10, max(0, len(hits) - 1) * 3)
    return min(score, 95)

def dedupe(group_id, message_id, sender_id=None, message_text=None):
    """Deduplicate repeated long advertisements globally and short requests per author."""
    if message_text:
        normalized = re.sub(r"\s+", " ", message_text.casefold()).strip()
        normalized = re.sub(r"[^\w ]", "", normalized)
        if normalized and len(normalized) >= 100:
            identity = f"telegram-long-content:{normalized}"
            return hashlib.sha256(identity.encode()).hexdigest()
        if normalized and sender_id is not None:
            identity = f"telegram-author:{sender_id}:{normalized}"
            return hashlib.sha256(identity.encode()).hexdigest()
    return hashlib.sha256(f"telegram:{group_id}:{message_id}".encode()).hexdigest()

def make_outreach(services):
    """Create a concise service-specific opener without inventing project details."""
    primary = services[0] if services else "Web3 marketing"
    openers = {
        "KOL & Influencer Marketing": (
            "your KOL and influencer campaign",
            "আপনার KOL ও ইনফ্লুয়েন্সার ক্যাম্পেইন",
        ),
        "Community Promotion": (
            "Telegram community growth and promotion",
            "Telegram কমিউনিটি গ্রোথ ও প্রমোশন",
        ),
        "AMA Hosting & Engagement": (
            "AMA hosting and community engagement",
            "AMA আয়োজন ও কমিউনিটি এনগেজমেন্ট",
        ),
        "PR & Media Visibility": (
            "PR and media visibility",
            "PR ও মিডিয়া প্রচার",
        ),
        "Giveaways & Airdrops": (
            "a giveaway or airdrop campaign",
            "গিভঅ্যাওয়ে বা এয়ারড্রপ ক্যাম্পেইন",
        ),
        "Content Distribution & Marketing": (
            "content distribution and marketing",
            "কনটেন্ট ডিস্ট্রিবিউশন ও মার্কেটিং",
        ),
        "Social Media Marketing": (
            "social media marketing and management",
            "সোশ্যাল মিডিয়া মার্কেটিং ও ম্যানেজমেন্ট",
        ),
        "Project Promotion": (
            "project promotion and growth marketing",
            "প্রজেক্ট প্রমোশন ও গ্রোথ মার্কেটিং",
        ),
        "Website Design & Development": (
            "website design and development",
            "ওয়েবসাইট ডিজাইন ও ডেভেলপমেন্ট",
        ),
        "Recruitment": (
            "community, moderation or developer recruitment",
            "কমিউনিটি, মডারেশন বা ডেভেলপার নিয়োগ",
        ),
        "Video & Creative Production": (
            "promotional video and creative production",
            "প্রমোশনাল ভিডিও ও ক্রিয়েটিভ তৈরি",
        ),
        "Project Review / VERDICT": (
            "product testing and structured user feedback",
            "প্রোডাক্ট টেস্টিং ও পরিকল্পিত ইউজার ফিডব্যাক",
        ),
        "Fundraising / Launch Promotion": (
            "launch and fundraising visibility",
            "লঞ্চ ও ফান্ডরেইজিং প্রচার",
        ),
        "AI / Automation Promotion": (
            "AI and automation product promotion",
            "AI ও অটোমেশন প্রোডাক্ট প্রমোশন",
        ),
        "Exchange / Wallet Promotion": (
            "exchange or wallet user acquisition and promotion",
            "এক্সচেঞ্জ বা ওয়ালেটের ইউজার সংগ্রহ ও প্রমোশন",
        ),
        "RWA / Trading Promotion": (
            "RWA and trading-sector marketing",
            "RWA ও ট্রেডিং-সেক্টর মার্কেটিং",
        ),
        "GameFi / Casino Promotion": (
            "GameFi and gaming project promotion",
            "GameFi ও গেমিং প্রজেক্ট প্রমোশন",
        ),
        "Mining / Staking Promotion": (
            "mining and staking user growth",
            "মাইনিং ও স্টেকিং ইউজার গ্রোথ",
        ),
    }
    english_need, bengali_need = openers.get(
        primary, ("Web3 marketing and growth", "Web3 মার্কেটিং ও গ্রোথ")
    )
    en = (
        f"Hi! I came across your message about {english_need}. "
        "AENZO LABS provides Web3 and crypto marketing support, including targeted campaigns "
        "and community growth. Would you be open to receiving a short proposal based on your requirements?"
    )
    bn = (
        f"হ্যালো! {bengali_need} বিষয়ে আপনার পোস্টটি দেখেছি। "
        "AENZO LABS Web3 ও ক্রিপ্টো মার্কেটিং, টার্গেটেড ক্যাম্পেইন এবং কমিউনিটি গ্রোথে সহায়তা করে। "
        "আপনার প্রয়োজন অনুযায়ী একটি সংক্ষিপ্ত প্রস্তাব পেতে কি আগ্রহী?"
    )
    return en, bn

def supabase_headers(secret_key):
    """New Supabase sb_secret keys are API keys, not JWT bearer tokens."""
    return {
        "apikey": secret_key,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def message_scan_kwargs(last_seen, cutoff):
    """Fetch oldest unseen messages first so batches cannot skip busy-group traffic."""
    kwargs = {
        "limit": MAX_MESSAGES_PER_GROUP,
        "min_id": last_seen,
        "reverse": True,
    }
    # The initial batch is bounded to recent history. Later batches must finish
    # any backlog even if messages have aged past LOOKBACK_DAYS.
    if not last_seen:
        kwargs["offset_date"] = cutoff
    return kwargs


async def save_lead(client_http, payload):
    headers = supabase_headers(SUPABASE_SERVICE_ROLE_KEY)
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

def format_telegram_lead(lead):
    contacts = lead.get('contacts') or []
    contact_lines = []
    for item in contacts[:8]:
        kind = str(item.get('type') or 'contact').upper()
        value = str(item.get('value') or '')
        url = str(item.get('url') or '')
        if value or url:
            contact_lines.append('- ' + kind + ': ' + (value or url) + ((' — ' + url) if url and url != value else ''))
    evidence = str(lead.get('evidence_summary') or '')
    if len(evidence) > 1000:
        evidence = evidence[:1000].rstrip() + '…'
    return ('NEW AENZO LABS LEAD\n\n' +
        'Project/group: ' + str(lead.get('company_name') or 'Potential project (verify)') + '\n' +
        'Service needed: ' + str(lead.get('service_need') or 'Needs review') + '\n' +
        'Priority: ' + str(lead.get('priority_score', '—')) + '/100\n' +
        'Date: ' + str(lead.get('evidence_date') or '—') + '\n\n' +
        'Evidence:\n' + (evidence or 'No message text') + '\n\n' +
        'Source: ' + str(lead.get('evidence_url') or 'Unavailable') + '\n' +
        'Group: ' + str(lead.get('telegram_group_url') or 'Unavailable') + '\n\n' +
        'Public contacts:\n' + ('\n'.join(contact_lines) if contact_lines else 'No public contact found') + '\n\n' +
        'Outreach English:\n' + str(lead.get('outreach_english') or 'Review first') + '\n\n' +
        'বাংলা অর্থ:\n' + str(lead.get('outreach_bengali') or 'পর্যালোচনা করুন') + '\n\n' +
        'Potential lead only. Verify the project and buyer intent before outreach.')[:3900]

async def notify_pending_leads(http):
    if not BOT_TOKEN or not BOT_CHAT_ID:
        log.info('Telegram bot alerts not configured; scanning continues.')
        return
    headers = supabase_headers(SUPABASE_SERVICE_ROLE_KEY)
    url = SUPABASE_URL + '/rest/v1/leads'
    params = {'select': 'id,company_name,service_need,priority_score,evidence_date,evidence_summary,evidence_url,telegram_group_url,contacts,outreach_english,outreach_bengali', 'owner_id': 'eq.' + SUPABASE_OWNER_ID, 'status': 'eq.new', 'telegram_notified_at': 'is.null', 'order': 'created_at.asc', 'limit': '25'}
    try:
        response = await http.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            log.error('Could not load pending Telegram alerts: %s', response.text[:300])
            return
        pending = response.json()
    except Exception:
        log.exception('Could not load pending Telegram alerts.')
        return
    for lead in pending:
        lead_id = lead.get('id')
        try:
            sent = await http.post('https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage', json={'chat_id': BOT_CHAT_ID, 'text': format_telegram_lead(lead), 'disable_web_page_preview': True}, timeout=30)
            if sent.status_code != 200 or not sent.json().get('ok'):
                detail = sent.text[:500]
                log.error('Telegram alert failed for lead %s: %s', lead_id, detail)
                await http.patch(url, headers=headers, params={'id': 'eq.' + str(lead_id)}, json={'telegram_notification_error': detail}, timeout=30)
                continue
            await http.patch(url, headers=headers, params={'id': 'eq.' + str(lead_id)}, json={'telegram_notified_at': datetime.now(timezone.utc).isoformat(), 'telegram_notification_error': None}, timeout=30)
            log.info('Telegram alert delivered for lead %s.', lead_id)
        except Exception:
            log.exception('Telegram notification attempt failed for lead %s; it will be retried.', lead_id)


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
    if SESSION_STRING:
        try:
            session = StringSession(SESSION_STRING)
        except Exception as exc:
            raise RuntimeError(
                "TELEGRAM_SESSION_STRING is invalid or truncated. Generate a fresh "
                "Telethon StringSession with telegram-worker/session_login.py and "
                "replace the GitHub Actions secret. Never paste the session into chat."
            ) from exc
        client = TelegramClient(session, API_ID, API_HASH)
    else:
        client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("Telegram session is not authorized. Run 'python worker.py --login' in an interactive shell first.")
    state = read_state()
    groups_state = state.setdefault("groups", {})
    async with httpx.AsyncClient() as http:
        while True:
            checked = 0
            saved = 0
            paused = 0
            cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
            now = datetime.now(timezone.utc)
            dialogs = []
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                # Scan every accessible group; broadcast-only channels are excluded.
                if not bool(getattr(dialog, "is_group", False)) or bool(getattr(entity, "broadcast", False)):
                    continue
                dialogs.append(dialog)

            # Groups with a history of genuine buyer signals are checked first.
            dialogs.sort(
                key=lambda dialog: group_priority(
                    groups_state.get(str(dialog.entity.id), {})
                ),
                reverse=True,
            )

            for dialog in dialogs:
                entity = dialog.entity
                group_id = str(entity.id)
                meta = groups_state.setdefault(group_id, {
                    "last_seen_id": 0,
                    "messages_seen": 0,
                    "seller_ads": 0,
                    "buyer_signals": 0,
                    "qualified_leads": 0,
                    "paused_until": None,
                })
                last_seen = int(meta.get("last_seen_id", 0))
                pause_value = meta.get("paused_until")
                if pause_value:
                    try:
                        pause_until = datetime.fromisoformat(pause_value)
                        if pause_until.tzinfo is None:
                            pause_until = pause_until.replace(tzinfo=timezone.utc)
                    except (TypeError, ValueError):
                        pause_until = now
                    if pause_until > now:
                        paused += 1
                        continue
                    # Re-sample a previously snoozed group instead of excluding it forever.
                    meta.update({
                        "messages_seen": 0,
                        "seller_ads": 0,
                        "buyer_signals": 0,
                        "qualified_leads": 0,
                        "paused_until": None,
                    })

                newest_seen = last_seen
                group_write_failed = False
                async for msg in client.iter_messages(entity, **message_scan_kwargs(last_seen, cutoff)):
                    if not msg:
                        continue
                    newest_seen = max(newest_seen, int(msg.id))
                    if getattr(msg, "out", False):
                        continue
                    if not msg.message or not msg.date:
                        continue
                    if not last_seen and msg.date.replace(tzinfo=timezone.utc) < cutoff:
                        continue

                    text_body = msg.message.strip()
                    meta["messages_seen"] = int(meta.get("messages_seen", 0)) + 1
                    if SELLER_AD_CONTEXT.search(text_body) or SELLER_POST_CONTEXT.search(text_body):
                        meta["seller_ads"] = int(meta.get("seller_ads", 0)) + 1

                    services = classify(text_body)
                    if not services:
                        continue
                    meta["buyer_signals"] = int(meta.get("buyer_signals", 0)) + 1
                    try:
                        sender = await msg.get_sender()
                    except Exception:
                        log.exception("Could not resolve message author in group %s, message %s.", group_id, msg.id)
                        group_write_failed = True
                        continue
                    if not is_human_sender(sender):
                        continue
                    username = getattr(sender, "username", None) if sender else None
                    group_name = (getattr(entity, "title", None) or "Telegram group").strip()
                    public_name = getattr(entity, "username", None)
                    group_url = make_message_url(entity, msg.id)
                    en, bn = make_outreach(services)
                    payload = {
                        "owner_id": SUPABASE_OWNER_ID,
                        "company_name": f"Potential project (verify) — {group_name}"[:250],
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
                        "contacts": extract_public_contacts(text_body, username),
                        "outreach_english": en,
                        "outreach_bengali": bn,
                        "notes": (
                            "Auto-detected buying-intent candidate; not independently verified. "
                            f"Source group: {group_name}. Message ID: {msg.id}. "
                            + (f"Public sender username: @{username}. " if username else "Public sender username unavailable. ")
                            + ("Direct message permalink unavailable for this group type. " if not group_url else "Message permalink recorded. ")
                            + "Verify the sender's role, project identity, and current service need before outreach."
                        ),
                        "dedupe_key": dedupe(group_id, msg.id, getattr(sender, "id", None), text_body),
                    }
                    save_status = await save_lead(http, payload)
                    if save_status == "saved":
                        saved += 1
                        meta["qualified_leads"] = int(meta.get("qualified_leads", 0)) + 1
                    elif save_status == "duplicate":
                        meta["qualified_leads"] = int(meta.get("qualified_leads", 0)) + 1
                    elif save_status == "error":
                        group_write_failed = True

                if not group_write_failed:
                    meta["last_seen_id"] = max(last_seen, newest_seen)
                else:
                    log.warning("Keeping cursor unchanged for group %s so failed writes can be retried.", group_id)

                # Vendor-heavy groups are snoozed for seven days, then sampled again.
                if should_pause_group(meta):
                    meta["paused_until"] = (now + timedelta(days=7)).isoformat()
                    log.info("Temporarily snoozing low-quality vendor-heavy group %s for 7 days.", group_id)

                checked += 1
                if checked % 10 == 0:
                    write_state(state)

            write_state(state)
            await notify_pending_leads(http)
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
