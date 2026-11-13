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
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.functions.messages import SearchGlobalRequest
from telethon.tl.types import InputMessagesFilterEmpty, InputPeerEmpty, User

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aenzo-telegram-worker")


def bounded_int_env(name, default, minimum, maximum):
    """Parse numeric worker settings safely and keep them inside supported limits."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        log.warning("Invalid %s; using default %s.", name, default)
        return default
    if value < minimum or value > maximum:
        clamped = max(minimum, min(value, maximum))
        log.warning("%s=%s is outside %s..%s; using %s.", name, value, minimum, maximum, clamped)
        return clamped
    return value


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
POLL_SECONDS = bounded_int_env("POLL_SECONDS", 7200, 60, 86400)
LOOKBACK_DAYS = bounded_int_env("LOOKBACK_DAYS", 30, 1, 3650)
GLOBAL_SEARCH_MAX_PAGES = bounded_int_env("GLOBAL_SEARCH_MAX_PAGES", 3, 1, 20)
SCAN_BUDGET_SECONDS = bounded_int_env("SCAN_BUDGET_SECONDS", 1320, 60, 1500)
MAX_MESSAGES_PER_RUN = bounded_int_env("MAX_MESSAGES_PER_RUN", 100, 1, 1000)
MAX_PUBLIC_MESSAGES_PER_RUN = min(bounded_int_env("MAX_PUBLIC_MESSAGES_PER_RUN", 50, 1, 100), MAX_MESSAGES_PER_RUN)
CLASSIFIER_RULES_VERSION = 9
GLOBAL_GROUP_SEARCH_QUERIES = [
    "looking for crypto marketing",
    "looking for beta testers",
    "looking for KOL",
    "need marketing agency",
    "looking for community growth",
    "looking for Telegram promotion",
    "looking for PR or AMA",
    "looking for project promotion",
    "need social media marketing",
    "need beta testing team",
    "looking for influencer marketing",
    "need community manager",
    "looking for website developer",
    "need AMA host",
    "looking for airdrop partner",
    "looking for launch promotion",
    "need web3 marketing agency",
    "looking for growth agency",
    "need user acquisition",
    "looking for paid promotion",
    "hiring Telegram promoters",
    "looking for Telegram promoters",
    "looking for promoters",
    "looking for CEX KOLs",
    "looking for BD partners",
    "onboard KOLs",
    "looking for AMA partnerships",
    "open to co-marketing",
    "looking for early users",
    "looking for growth marketers",
    "need crypto marketing partner",
    "looking for community management",
    "need influencer campaign",
    "looking for brand awareness",
    "need project visibility",
    "looking for marketing manager",
    "need KOL marketing",
    "need influencer marketing agency",
    "looking for crypto influencers",
    "looking for Web3 KOLs",
    "need Telegram community growth",
    "looking for Telegram marketing",
    "need community promotion",
    "looking for crypto PR agency",
    "need crypto media coverage",
    "looking for AMA host",
    "need AMA promotion",
    "looking for a marketing partner",
    "need a growth marketing team",
    "looking for Web3 promotion",
    "need token launch marketing",
    "looking for exchange listing marketing",
    "need crypto social media manager",
    "looking for content marketing agency",
    "need project awareness campaign",
    "looking for airdrop marketing",
    "need user growth campaign",
    "looking for paid KOL campaign",
    "need influencer outreach",
    "looking for crypto advertising",
    "need blockchain marketing services",
    "need KOLs for token launch",
    "seeking crypto KOL agency",
    "looking to book web3 influencers",
    "need influencers to promote our token",
    "want to run paid crypto influencer campaign",
    "looking for crypto Twitter promotion",
    "need X account growth for our project",
    "looking for Telegram member acquisition",
    "need real Telegram users for project",
    "looking for community engagement campaign",
    "need to increase Telegram activity",
    "seeking Discord community growth service",
    "need Discord moderators for our project",
    "looking for Web3 community manager agency",
    "need crypto project PR distribution",
    "looking for blockchain press release service",
    "want our crypto project featured in media",
    "seeking crypto news publication coverage",
    "need an AMA campaign for our token",
    "looking for crypto spaces host",
    "need a partner to organize project AMA",
    "looking for token launch campaign manager",
    "need marketing for upcoming TGE",
    "seeking pre-TGE marketing support",
    "looking for exchange listing PR campaign",
    "need exchange announcement promotion",
    "seeking wallet user acquisition campaign",
    "need users for our crypto wallet",
    "looking for DeFi protocol marketing",
    "need DeFi community growth",
    "seeking GameFi user acquisition",
    "need players for our blockchain game",
    "looking for NFT project marketing agency",
    "need NFT collection promotion",
    "seeking RWA project marketing partner",
    "need marketing for our AI crypto project",
    "looking for AI agent user acquisition",
    "need SaaS product launch promotion",
    "seeking trading platform marketing agency",
    "need forex trading community promotion",
    "looking for staking platform promotion",
    "need mining platform user acquisition",
    "seeking airdrop campaign management",
    "need giveaway campaign promotion",
    "looking for crypto content creators",
    "need sponsored posts for our project",
    "seeking paid crypto media partnerships",
    "looking for Web3 brand ambassador campaign",
    "need marketing support for our fundraising",
    "seeking external team for product review",
]

# Signals that indicate a project may need one or more AENZO services.
SIGNALS = {
    "KOL & Influencer Marketing": [
        r"looking for (kol|kols|influencer|influencers)",
        r"searching for (kol|kols|influencer|influencers)",
        r"want to hire (kol|kols|influencer|influencers)",
        r"looking to hire (kol|kols|influencer|influencers)",
        r"looking to hire (an? )?(external )?(kol|influencer|marketing|growth) (agency|team)",
        r"need help with (our )?(kol|influencer) campaign",
        r"need (kols|influencers)", r"kol campaign", r"influencer campaign",
        r"(crypto|web3) influencer (marketing|campaign|promotion)",
        r"anyone know (a |any )?(good )?(kol|influencer|influencers)",
        r"looking for (a |an )?(cex |crypto )?(kol|kols|influencer|influencers)",
        r"hiring (growth )?(marketers?|kols?|influencers?)",
        r"looking for .{0,100}(kol|kols|influencer|influencers)",
        r"onboard .{0,60}(kol|kols|influencer|influencers)",
        r"(we are |we're )?(looking for|seeking) (a |an )?(kol|influencer) (agency|partner|team)",
        r"need (a |an )?(kol|influencer) (agency|partner|team|campaign)",
        r"(need|looking for) someone to (run|manage) (our )?(kol|influencer) campaign",
    ],
    "Community Promotion": [
        r"looking for (community|telegram) (growth|promotion|marketing)",
        r"need (community|telegram) (growth|promotion|marketing)",
        r"need telegram community (growth|promotion|marketing)",
        r"grow our (telegram )?community", r"community growth (agency|partner|service)",
        r"telegram group promotion",
        r"looking for (telegram )?(promoter|promoters)",
        r"looking for (a )?(promoter|promoters)",
        r"hiring (telegram )?(promoter|promoters)",
        r"need (telegram )?(promoter|promoters)",
        r"paid promotions? (for|on) (our )?telegram",
        r"help us grow (our )?(telegram )?community",
        r"(telegram|community) (group )?(is )?(quiet|inactive|small).*(grow|users|members|engagement)",
        r"anyone know (a |any )?(community growth|telegram promotion) (agency|team|partner)",
        r"(looking for|seeking) (a |an )?(community management|community growth) (agency|partner|team)",
        r"need (a |an )?(community management|community growth) (agency|partner|team)",
    ],
    "AMA Hosting & Engagement": [
        r"looking for ama", r"need ama (host|hosting|partner)",
        r"ama collaboration", r"ama partnership", r"(host|hosting) an ama",
    ],
    "PR & Media Visibility": [
        r"looking for pr", r"looking for (a |an )?pr (agency|partner|service|firm|support)",
        r"need (a |an )?pr (agency|partner|service|firm|support)",
        r"seeking (a |an )?pr (agency|partner|service|firm|support)",
        r"need pr (agency|service|support)",
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
        r"(need|seeking) (a |an )?(web3 |crypto )?marketing (agency|partner|team)",
        r"looking for (a |an )?(web3 |crypto )?growth (agency|partner|team)",
        r"need (a |an )?growth (agency|partner|team)",
    ],
    "Social Media Marketing": [
        r"need social media (marketing|management|promotion)",
        r"looking for social media (marketing|management|agency)",
        r"(manage|grow) our (twitter|x|social media)",
        r"help us grow our (twitter|x) account",
    ],
    "Project Promotion": [
        r"looking for (promotion|marketing) (agency|partner|service)",
        r"(need|seeking) (a |an )?(marketing|growth) partner",
        r"looking for (paid promotion|project visibility|brand awareness)",
        r"need (more )?(project visibility|brand awareness|user acquisition)",
        r"(looking for|need) (a |an )?user acquisition (agency|partner|team|service)",
        r"need project promotion", r"promote our project",
        r"cross[- ]marketing", r"co[- ]marketing", r"joint campaign",
        r"pr collaboration", r"x partnership", r"twitter partnership",
        r"(open to|looking for|seeking|interested in) .{0,80}(collaboration|collaborations|partnership|partnerships)",
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
        r"looking for (a |an )?(community manager|moderator|developer|blockchain developer|frontend developer|backend developer)",
        r"hiring (a |an )?(community manager|moderator|developer|blockchain developer|frontend developer|backend developer)",
        r"need (a |an )?(community manager|moderator|developer)",
        r"need moderators", r"recruiting (community|telegram) moderators",
    ],
    "Video & Creative Production": [
        r"looking for (video|creative) (agency|team|partner)",
        r"need (promo video|video production)",
        r"looking for (motion graphics|video editing|graphic design)",
    ],
    "Project Review / VERDICT": [
        r"looking for (project|product) review",
        r"(need|looking for|hiring) (a )?(beta testing|product testing|qa testing) (agency|team|partner|service)",
        r"need (an? )?(external )?(team|agency|partner) to (test|review|evaluate) (our )?(app|game|platform|website|product)",
        r"looking for (an? )?(external )?(team|agency|partner) to (test|review|evaluate) (our )?(app|game|platform|website|product)",
        r"need professional (beta )?testing (services|support|team)",
        r"looking for (early )?(users|adopters) to (try|test|use) (our )?(mvp|app|platform|product)",
        r"looking for (beta )?testers? for (our )?(web3|crypto|blockchain|ai|defi|cefi|trading|wallet|launchpad)",
        r"need (early )?(users|adopters) for (our )?(web3|crypto|blockchain|ai|defi|cefi|trading|wallet|launchpad)",
        r"looking for product feedback from (early )?users",
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
CRYPTO_CONTEXT = re.compile(r"\b(web3|crypto|blockchain|solana|memecoins?|defi|cefi|token|wallet|exchange|launchpad|staking|mining|rwa|gamefi|metaverse|ai agent|trading|forex|telegram|airdrop|dapp|testnet|layer[- ]?[12])\b", re.I)
# Posts selling tools, accounts, traffic, or services are vendors—not buyers.
# This catches ads that contain phrases such as "looking for an account" while
# the author is actually offering rentals or inventory.
SELLER_AD_CONTEXT = re.compile(
    r"\b("
    r"rental\s*(\+|and|&)\s*purchase options|"
    r"looking for (reliable )?(advertising|ad account|lead generation) (solutions|options|services) for your campaigns?|"
    r"need help with (ad accounts?|advertising accounts?|campaign approvals?|account setup|campaign setup|tracking|performance)|"
    r"looking for (stable and high.performing )?(advertising|ad) accounts?|"
    r"(purchase options|rental solutions).{0,100}(account|advertising)|"
    r"(account|accounts).{0,100}(purchase options|rental solutions)|"
    r"we only deal with (verified )?accounts|"
    r"available lead categories|high.converting.{0,40}leads|niche.targeted leads|"
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
    r"\b("
    r"we (offer|provide|specialize in|are offering|can provide) (web3 |crypto )?(marketing|promotion|kol|influencer|pr|ama|community management|social media|advertising|lead generation|ad account|campaign management|growth) (services|packages|solutions|support|campaigns)|"
    r"we (help|support|work with|only deal with|deliver|supply|give you access to) (advertisers|businesses|brands|clients|media buyers|agencies|accounts|leads)|"
    r"i (offer|provide|specialize in|help|support|work with|only deal with|deliver|supply) (advertisers|businesses|brands|clients|media buyers|agencies|accounts|leads)|"
    r"we give you access to .{0,100}(database|data|lead|tool)|"
    r"(our|my) (database|data|leads|accounts|services|solutions|packages) (include|are available|available)|"
    r"fresh crypto,? investors?,? business,? depositors?.{0,100}(leads|data)|"
    r"(taboola|meta|google|tiktok|facebook) (ad )?accounts? (available|for rent|for sale)|"
    r"(premium|verified|agency|network) advertising accounts?|" 
    r"ad accounts? (available|options|rental|purchase)|"
    r"looking to buy (ad|advertising) accounts?|" 
    r"(database tool|private database|premium lead samples|data drops)|"
    r"we help set up multi.user call cent(re|er) ops|" 
    r"(account options|campaign support|account setup|technical support).{0,150}(available|dm|contact|pricing)|"
    r"serious buyers only|dm to discuss availability|reliable supplier|"
    r"available lead categories|high.converting.{0,40}leads|niche.targeted leads|"
    r"fresh (crypto|investor|business|consumer|email|phone) leads|"
    r"(i|we) can (help|provide|offer|run|manage) .{0,100}(kol|influencer|marketing|promotion|pr|ama|community|social media|advertising|leads|traffic)|"
    r"(i|we) have .{0,100}(kol|influencer|shilling|telegram|community) (network|community|group|team|services|packages)|"
    r"(i|we) can (promote|market|shill|advertise) your (project|token|coin|brand|website|app)|"
    r"(i|we) will (promote|market|shill|advertise) your (project|token|coin|brand|website|app)|"
    r"(looking for|seeking) (new )?(clients|projects) (to promote|for promotion|for marketing)|"
    r"looking for clients.{0,100}(marketing|promotion|kol|pr)|"
    r"i (offer|provide|specialize in|help|support|work with) (advertisers|businesses|brands|clients|media buyers|agencies)|"
    r"i specialize in (traffic|campaign|advertising|lead|marketing|growth)|"
    r"our (agency|company|team) (offers|provides|specializes in|is offering|can provide)|"
    r"available for paid promotions|available for one-time orders|long-term business partnerships|kol services available|"
    r"marketing packages available|dm us for rates|contact us for pricing|"
    r"we'?ve got you covered|"
    r"(ad accounts?|advertising accounts?|business leads|crypto leads|targeted leads|traffic|business data|campaign data) (available|for rent|for sale|solutions)|"
    r"available (ad accounts?|advertising accounts?|targeted traffic|business leads|crypto leads|business data|campaign data|services|solutions|packages)|"
    r"get (targeted|campaign.ready|organized) (leads|business data|campaign data)|"
    r"lead generation (data|services|solutions) available|"
    r"our services|supported campaigns|"
    r"looking for .{0,180} (i have|we have) (a (large )?(kol|influencer|telegram|community) (network|team|group)|available (accounts|leads|services|solutions|packages)|the solution|the right solution)|"
    r"looking for .{0,180} (we offer|we provide|let'?s get you set up)|"
    r"looking for targeted traffic and potential customers for your platform|"
    r"digital marketing solutions tailored to your campaign goals|"
    r"we\'?re offering (this )?(collaboration|project features?|social media cross.promotion|cross.promotion|pr collaboration) (free|for free|at no cost)|"
    r"offering (free )?(project features?|social media cross.promotion|cross.promotion|pr collaborations?)|"
    r"i create .{0,140}(promotional content|ugc content|product promotion content|ai influencer models)|"
    r"i\'?m open to:?.{0,180}(ugc content creation|product promotions|paid partnerships|ai influencer marketing)|"
    r"launchpad.{0,100}(no upfront|without upfront|no (upfront )?fees?|does not take upfront|do not take upfront|who (does not|doesn\'t|do not|don\'t|not) take (or tack )?(any )?upfront fees?)"
    r")\b",
    re.I,
)

NON_BUYER_CONTEXT = re.compile(
    r"\b(looking for a job|need a job|seeking (a )?job|looking for work|available for work|"
    r"open to (the )?(next|new) (opportunity|role|position)|open to opportunities|"
    r"looking for (my )?(next|new) (opportunity|role|position)|seeking (a )?(new )?(role|position|opportunity)|"
    r"looking for (a )?(new )?(role|position|opportunity)|available for (a )?(new )?(role|position|opportunity)|"
    r"anyone hiring|is anyone hiring|who is hiring|job opportunities|employment opportunities|"
    r"looking to join (a |your |any )?team|"
    r"hire me|anyone hiring me|free airdrop|airdrop claim|claim (my )?airdrop|"
    r"token price prediction|price prediction|trading signals|"
    r"wallet (is )?(not working|stuck)|"
    r"account (is )?(locked|suspended)|"
    r"we are (a|an) [a-z -]{1,50}(agency|service provider|marketing team|growth team|pr firm)|"
    r"our (agency|company|team) (offers|provides|specializes in|is offering|can provide)|"
    r"(dm|message|contact) (me|us) (for|to get) (rates|pricing|packages|details|collaboration)|"
    r"(our|my) (services|packages|plans|rates|pricing) (include|start|are|for)|"
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
        raw.setdefault("global_search", {})
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
    return {"version": 2, "groups": groups, "global_search": {}}

def write_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE_FILE)


def reset_group_quality_metrics(state):
    """Reset stale quality counters after classifier changes without losing scan cursors."""
    if int(state.get("classifier_rules_version", 0) or 0) >= CLASSIFIER_RULES_VERSION:
        return False
    for meta in state.setdefault("groups", {}).values():
        meta.update({
            "messages_seen": 0,
            "seller_ads": 0,
            "buyer_signals": 0,
            "qualified_leads": 0,
            "paused_until": None,
        })
    state["classifier_rules_version"] = CLASSIFIER_RULES_VERSION
    return True


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
    """Return direct and plausible AENZO prospects; seller and job-seeker posts remain excluded."""
    if (
        not text
        or (
            NON_BUYER_CONTEXT.search(text)
            and not (
                CRYPTO_CONTEXT.search(text)
                and re.search(
                    r"\b(early users?|early adopters?|beta testers?|product feedback|mvp testing|"
                    r"pr collaborations?|x partnerships?|twitter partnerships?|cross[- ]marketing|"
                    r"co[- ]marketing|joint campaigns?|ama partnerships?)\b",
                    text,
                    re.I,
                )
            )
        )
        or SELLER_AD_CONTEXT.search(text)
        or SELLER_POST_CONTEXT.search(text)
    ):
        return []

    # Technical hiring/help (e.g. token launch specialists) is not automatically
    # a marketing lead. Keep these out unless a separate marketing request exists.
    technical_only = re.compile(
        r"\b(auditor|auditors|smart contract|solidity|transfer hook|token[- ]?2022|"
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
        r"launch promotion|project promotion|advertising|paid campaign|promoter|promoters|"
        r"cross[- ]marketing|co[- ]marketing|collaboration|partnership|joint campaign|"
        r"early users?|early adopters?|beta testers?|product feedback|mvp testing)\b",
        re.I,
    )
    buyer_intent = re.compile(
        r"\b(looking for|looking to hire|searching for|seeking|need|needs|want to hire|"
        r"hiring|want to work with|looking to work with|need help with|"
        r"can anyone recommend|does anyone know|anyone know|who can help|"
        r"can someone help|anyone able to|partner with|could use|"
        r"struggling to|not getting enough|trying to increase|"
        r"trying to grow|want to grow|want to increase|want to attract|"
        r"we are looking for|we're looking for|we need|we are seeking|"
        r"looking to onboard|who handles|recommend a (marketing|growth|pr) agency|"
        r"open to|open for|interested in (a |an )?(partnership|collaboration|cross[- ]marketing))\b",
        re.I,
    )

    hits = [
        name for name, patterns in COMPILED.items()
        if any(pattern.search(text) for pattern in patterns)
    ]

    # Require a request/buying cue: direct AENZO service requests and relevant
    # Web3 growth/partnership opportunities qualify without a stated budget.
    # Indirect growth-pain messages still need marketing, visibility, audience,
    # acquisition, or promotion context.
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

    # Generic app beta-testing requests are not AENZO prospects. Keep early-user,
    # beta-tester, and feedback requests only when a crypto/Web3 project is named.
    beta_feedback_request = re.search(
        r"\b(early users?|early adopters?|beta testers?|product feedback|mvp testing)\b",
        text,
        re.I,
    )
    if beta_feedback_request and not CRYPTO_CONTEXT.search(text):
        return []

    if not hits and marketing_intent.search(text):
        strong_marketing_intent = re.compile(
            r"\b(kol|kols|influencer|influencers|marketing|promotion|promote|"
            r"advertising|pr agency|media coverage|press release|ama hosting|"
            r"giveaway campaign|airdrop campaign|social media management|"
            r"content marketing|content distribution|brand awareness|"
            r"user acquisition|launch promotion|project promotion|paid campaign)\b",
            re.I,
        )
        partnership_opportunity = (
            re.search(r"\b(collaboration|collaborations|partnership|partnerships|cross[- ]marketing|co[- ]marketing|joint campaign)\b", text, re.I)
            and CRYPTO_CONTEXT.search(text)
        )
        growth_demand = re.compile(
            r"\b(users?|user base|audience|traction|signups|registrations|"
            r"engagement|members|visibility|early users?|early adopters?|beta testers?|product feedback)\b",
            re.I,
        )
        digital_project_context = re.compile(
            r"\b(project|product|app|platform|website|software|saas|digital product|"
            r"startup|brand|launch|game)\b",
            re.I,
        )
        # Generic "looking for users" posts are not enough. Accept indirect
        # growth requests only when the post identifies a digital/Web3 project.
        if strong_marketing_intent.search(text) or partnership_opportunity or (
            growth_demand.search(text)
            and (CRYPTO_CONTEXT.search(text) or digital_project_context.search(text))
        ):
            hits = ["Project Promotion"]
        else:
            return []

    return hits

def public_message_cursor_key(message):
    """Stable cursor ordering for public search results spanning multiple Telegram groups."""
    return (
        int(message.date.timestamp()),
        repr(getattr(message, "peer_id", None)),
        int(getattr(message, "id", 0) or 0),
    )


def public_cursor_is_after(message, cursor):
    if not isinstance(cursor, dict):
        return True
    try:
        previous = (int(cursor["date"]), str(cursor["peer"]), int(cursor["message_id"]))
    except (KeyError, TypeError, ValueError):
        return True
    return public_message_cursor_key(message) > previous


def store_public_cursor(query_meta, message):
    stamp, peer, message_id = public_message_cursor_key(message)
    query_meta["cursor"] = {"date": stamp, "peer": peer, "message_id": message_id}


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
    """Only accept a real Telegram user, excluding bots and anonymous group/channel identities."""
    return isinstance(sender, User) and not bool(getattr(sender, "bot", False))


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
    """One lead per verified Telegram account; similar wording from other users stays separate."""
    if sender_id is not None:
        identity = f"telegram-user:{sender_id}"
    else:
        # Without a stable Telegram ID, do not infer identity from a username or text.
        identity = f"telegram-message:{group_id}:{message_id}"
    return hashlib.sha256(identity.encode()).hexdigest()

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
        "min_id": last_seen,
        "reverse": True,
    }
    # The initial batch is bounded to recent history. Later batches must finish
    # any backlog even if messages have aged past LOOKBACK_DAYS.
    if not last_seen:
        kwargs["offset_date"] = cutoff
    return kwargs

def rotate_global_search_queries(queries, start_index=0):
    """Rotate query order so a busy early phrase cannot starve later search phrases."""
    if not queries:
        return []
    start = int(start_index or 0) % len(queries)
    return [
        ((start + offset) % len(queries), queries[(start + offset) % len(queries)])
        for offset in range(len(queries))
    ]


async def fetch_global_group_messages(client, query, min_date, max_date):
    """Search public groups with recursive date windows so busy queries do not starve."""
    async def fetch_window(window_min, window_max, depth=0):
        collected = []
        offset_rate = 0
        offset_peer = InputPeerEmpty()
        offset_id = 0
        saturated = False

        for _ in range(GLOBAL_SEARCH_MAX_PAGES):
            result = await client(SearchGlobalRequest(
                q=query,
                filter=InputMessagesFilterEmpty(),
                min_date=window_min,
                max_date=window_max,
                offset_rate=offset_rate,
                offset_peer=offset_peer,
                offset_id=offset_id,
                limit=100,
                groups_only=True,
            ))
            batch = list(getattr(result, "messages", []) or [])
            if not batch:
                return collected, True
            collected.extend(batch)

            next_rate = getattr(result, "next_rate", None)
            if len(batch) < 100 or next_rate is None:
                return collected, True

            last_message = batch[-1]
            try:
                offset_peer = await client.get_input_entity(last_message.peer_id)
            except Exception:
                log.exception("Could not resolve global-search pagination peer for query %r.", query)
                return collected, False
            offset_id = int(last_message.id)
            offset_rate = int(next_rate)
        else:
            saturated = True

        # A full page limit means this time range may contain more than 300
        # matches. Split it into overlapping halves and merge by message identity.
        # The one-second overlap avoids gaps at Telegram's date-boundary semantics.
        if saturated:
            if depth >= 24 or window_max - window_min <= 1:
                log.warning(
                    "Global search could not fully page query %r in one-second window %s..%s.",
                    query, window_min, window_max,
                )
                return collected, False
            midpoint = (window_min + window_max) // 2
            if midpoint <= window_min or midpoint >= window_max:
                return collected, False

            log.info(
                "Global search result cap reached for %r; splitting date window %s..%s.",
                query, window_min, window_max,
            )
            left, left_complete = await fetch_window(window_min, midpoint, depth + 1)
            right, right_complete = await fetch_window(midpoint, window_max, depth + 1)
            unique = {}
            for message in left + right:
                key = (repr(getattr(message, "peer_id", None)), int(getattr(message, "id", 0) or 0))
                unique.setdefault(key, message)
            merged = sorted(
                unique.values(),
                key=lambda message: (
                    int(message.date.timestamp()) if getattr(message, "date", None) else 0,
                    repr(getattr(message, "peer_id", None)),
                    int(getattr(message, "id", 0) or 0),
                ),
            )
            return merged, left_complete and right_complete

        return collected, True

    return await fetch_window(int(min_date), int(max_date))


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
                await http.patch(
                    url,
                    headers=headers,
                    params={'id': 'eq.' + str(lead_id), 'owner_id': 'eq.' + SUPABASE_OWNER_ID},
                    json={'telegram_notification_error': detail},
                    timeout=30,
                )
                continue
            marked = await http.patch(
                url,
                headers=headers,
                params={'id': 'eq.' + str(lead_id), 'owner_id': 'eq.' + SUPABASE_OWNER_ID},
                json={'telegram_notified_at': datetime.now(timezone.utc).isoformat(), 'telegram_notification_error': None},
                timeout=30,
            )
            if marked.status_code not in (200, 204):
                log.error(
                    'Telegram delivered lead %s, but notification timestamp could not be saved (%s). '
                    'It may be sent again on a later scan.',
                    lead_id, marked.status_code,
                )
                continue
            log.info('Telegram alert delivered and recorded for lead %s.', lead_id)
        except Exception:
            log.exception('Telegram notification attempt failed for lead %s; it will be retried.', lead_id)



async def send_scan_report(http, stats):
    """Send a compact per-run scan-usage report to the owner's Telegram chat."""
    if not BOT_TOKEN or not BOT_CHAT_ID:
        log.info("Telegram scan reports are not configured; skipping scan report.")
        return
    minutes = int(stats.get("duration_seconds", 0)) // 60
    seconds = int(stats.get("duration_seconds", 0)) % 60
    report = (
        "📊 AENZO LABS SCAN REPORT\n\n"
        f"Joined groups available: {stats.get('joined_groups_available', 0)}\n"
        f"Joined groups checked: {stats.get('joined_groups_scanned', 0)}\n"
        f"Joined groups paused: {stats.get('groups_paused', 0)}\n"
        f"Non-joined public groups with qualified signals: {stats.get('public_groups_found', 0)}\n"
        f"Public groups with qualified buyer signals: {stats.get('public_groups_with_buyer_signals', 0)}\n"
        f"Public messages processed: {stats.get('public_messages_processed', 0):,} / {MAX_PUBLIC_MESSAGES_PER_RUN:,}\n"
        f"Public text messages checked: {stats.get('public_messages_checked', 0):,}\n"
        f"Public buyer signals: {stats.get('public_buyer_signals', 0):,}\n"
        f"Public leads saved: {stats.get('public_leads_saved', 0)}\n"
        f"Public duplicate leads: {stats.get('public_duplicates', 0)}\n"
        f"Joined-group messages checked: {stats.get('joined_messages_checked', 0):,}\n"
        f"Joined-group buyer signals: {stats.get('joined_buyer_signals', 0):,}\n"
        f"Joined-group leads saved: {stats.get('joined_leads_saved', 0)}\n"
        f"Joined-group duplicate leads: {stats.get('joined_duplicates', 0)}\n"
        f"Global search queries completed: {stats.get('global_queries_completed', 0)}\n"
        f"Global search queries incomplete: {stats.get('global_queries_incomplete', 0)}\n"
        f"Messages processed this run: {stats.get('messages_processed', 0):,} / {MAX_MESSAGES_PER_RUN:,}\n"
        f"Text messages checked: {stats.get('messages_checked', 0):,}\n"
        f"Seller/vendor posts: {stats.get('seller_posts', 0):,}\n"
        f"Buyer signals: {stats.get('buyer_signals', 0):,}\n"
        f"New leads saved: {stats.get('leads_saved', 0)}\n"
        f"Duplicate leads: {stats.get('duplicates', 0)}\n"
        f"Scan duration: {minutes}m {seconds}s\n\n"
        "Note: message count is the number actually processed in this run; "
        "older messages are not intentionally rescanned."
    )
    try:
        response = await http.post(
            "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage",
            json={"chat_id": BOT_CHAT_ID, "text": report, "disable_web_page_preview": True},
            timeout=30,
        )
        if response.status_code != 200 or not response.json().get("ok"):
            log.error("Telegram scan report failed: %s", response.text[:500])
        else:
            log.info("Telegram scan report delivered.")
    except Exception:
        log.exception("Could not send Telegram scan report.")


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
    if reset_group_quality_metrics(state):
        write_state(state)
    groups_state = state.setdefault("groups", {})
    async with httpx.AsyncClient() as http:
        while True:
            scan_started = asyncio.get_running_loop().time()
            checked = 0
            saved = 0
            paused = 0
            messages_checked = 0
            messages_processed = 0
            seller_posts = 0
            buyer_signals = 0
            duplicates = 0
            public_duplicates = 0
            run_seen_dedupe_keys = set()
            run_seen_public_messages = set()
            cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
            now = datetime.now(timezone.utc)
            dialogs = []
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                # Scan every accessible group; broadcast-only channels are excluded.
                if not bool(getattr(dialog, "is_group", False)) or bool(getattr(entity, "broadcast", False)):
                    continue
                dialogs.append(dialog)

            public_messages_processed = 0
            public_messages_checked = 0
            public_buyer_signals = 0
            public_leads_saved = 0

            # PRIORITY 1: search accessible public groups without joining.
            # Joined groups are scanned only after this targeted buyer-intent pass.
            global_search_state = state.setdefault("global_search", {})
            global_group_ids = set()
            joined_group_ids = {str(dialog.entity.id) for dialog in dialogs}
            global_search_complete = 0
            global_search_incomplete = 0

            query_start_index = int(state.get("global_search_query_index", 0) or 0)
            for query_index, query in rotate_global_search_queries(GLOBAL_GROUP_SEARCH_QUERIES, query_start_index):
                if public_messages_processed >= MAX_PUBLIC_MESSAGES_PER_RUN or messages_processed >= MAX_MESSAGES_PER_RUN:
                    state["global_search_query_index"] = query_index
                    write_state(state)
                    log.info("Public-search message budget reached; remaining public queries resume next run.")
                    break
                if asyncio.get_running_loop().time() - scan_started >= SCAN_BUDGET_SECONDS:
                    state["global_search_query_index"] = query_index
                    write_state(state)
                    log.info("Public search time budget reached; remaining queries resume next run.")
                    break
                query_meta = global_search_state.setdefault(query, {})
                previous_scan = int(query_meta.get("last_scanned_at", 0) or 0)
                cursor = query_meta.get("cursor")
                cursor_date = int(cursor.get("date", 0) or 0) if isinstance(cursor, dict) else 0
                query_min_date = max(
                    int(cutoff.timestamp()),
                    cursor_date - 2 if cursor_date else (previous_scan - 2 if previous_scan else int(cutoff.timestamp())),
                )
                query_max_date = int(now.timestamp())
                if query_min_date >= query_max_date:
                    state["global_search_query_index"] = (query_index + 1) % len(GLOBAL_GROUP_SEARCH_QUERIES)
                    write_state(state)
                    continue

                try:
                    global_messages, complete = await fetch_global_group_messages(
                        client, query, query_min_date, query_max_date
                    )
                except FloodWaitError as exc:
                    log.warning(
                        "Telegram global group search rate-limited for %s seconds on query %r; cursor retained.",
                        exc.seconds, query,
                    )
                    if exc.seconds <= 60:
                        await asyncio.sleep(exc.seconds)
                    global_search_incomplete += 1
                    state["global_search_query_index"] = (query_index + 1) % len(GLOBAL_GROUP_SEARCH_QUERIES)
                    write_state(state)
                    continue
                except Exception:
                    log.exception("Global public-group search failed for query %r; cursor retained.", query)
                    global_search_incomplete += 1
                    state["global_search_query_index"] = (query_index + 1) % len(GLOBAL_GROUP_SEARCH_QUERIES)
                    write_state(state)
                    continue

                if not complete:
                    log.warning(
                        "Global group search was incomplete for query %r; processing available messages "
                        "but retaining the query cursor so remaining results are retried.",
                        query,
                    )

                # Even an incomplete search can contain useful messages. Process
                # the partial page set, but never advance its cursor until complete.
                query_failed = not complete
                for msg in global_messages:
                    if public_messages_processed >= MAX_PUBLIC_MESSAGES_PER_RUN or messages_processed >= MAX_MESSAGES_PER_RUN:
                        query_failed = True
                        break
                    if asyncio.get_running_loop().time() - scan_started >= SCAN_BUDGET_SECONDS:
                        query_failed = True
                        break
                    if not msg or not getattr(msg, "date", None):
                        continue
                    if not public_cursor_is_after(msg, cursor):
                        continue
                    if getattr(msg, "out", False):
                        store_public_cursor(query_meta, msg)
                        continue
                    if int(msg.date.timestamp()) < query_min_date:
                        continue

                    public_message_key = (
                        repr(getattr(msg, "peer_id", None)),
                        int(getattr(msg, "id", 0) or 0),
                    )
                    if public_message_key in run_seen_public_messages:
                        store_public_cursor(query_meta, msg)
                        continue
                    run_seen_public_messages.add(public_message_key)
                    messages_processed += 1
                    public_messages_processed += 1

                    text_body = (getattr(msg, "message", None) or "").strip()
                    if not text_body:
                        store_public_cursor(query_meta, msg)
                        continue
                    messages_checked += 1
                    public_messages_checked += 1
                    if SELLER_AD_CONTEXT.search(text_body) or SELLER_POST_CONTEXT.search(text_body):
                        seller_posts += 1
                    services = classify(text_body)
                    if not services:
                        store_public_cursor(query_meta, msg)
                        if messages_processed % 25 == 0:
                            write_state(state)
                        continue
                    buyer_signals += 1
                    public_buyer_signals += 1

                    try:
                        entity = await client.get_entity(msg.peer_id)
                        sender = await msg.get_sender()
                    except Exception:
                        log.exception("Could not resolve public-group message or author %s.", getattr(msg, "id", "?"))
                        query_failed = True
                        break

                    if entity is None or bool(getattr(entity, "broadcast", False)):
                        store_public_cursor(query_meta, msg)
                        continue
                    if not is_human_sender(sender):
                        store_public_cursor(query_meta, msg)
                        continue

                    group_id = str(entity.id)
                    global_group_ids.add(group_id)
                    username = getattr(sender, "username", None)
                    group_name = (getattr(entity, "title", None) or "Public Telegram group").strip()
                    public_name = getattr(entity, "username", None)
                    group_url = make_message_url(entity, msg.id)
                    en, bn = make_outreach(services)
                    sender_id = getattr(sender, "id", None)
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
                            "Auto-detected candidate from Telegram global group search; not independently verified. "
                            f"Source group: {group_name}. Message ID: {msg.id}. "
                            + (f"Telegram User ID: {sender_id}. " if sender_id is not None else "Telegram User ID unavailable. ")
                            + (f"Public sender username: @{username}. " if username else "Public sender username unavailable. ")
                            + ("Direct message permalink unavailable for this group type. " if not group_url else "Message permalink recorded. ")
                            + "Verify the sender's role, project identity, and current service need before outreach."
                        ),
                        "dedupe_key": dedupe(group_id, msg.id, sender_id, text_body),
                    }
                    if payload["dedupe_key"] in run_seen_dedupe_keys:
                        save_status = "duplicate"
                    else:
                        save_status = await save_lead(http, payload)
                        if save_status in ("saved", "duplicate"):
                            run_seen_dedupe_keys.add(payload["dedupe_key"])
                    if save_status == "saved":
                        saved += 1
                        public_leads_saved += 1
                    elif save_status == "duplicate":
                        duplicates += 1
                        public_duplicates += 1
                    else:
                        query_failed = True
                        break
                    store_public_cursor(query_meta, msg)
                    if messages_processed % 25 == 0:
                        write_state(state)

                if query_failed:
                    global_search_state[query] = query_meta
                    write_state(state)
                    global_search_incomplete += 1
                    if public_messages_processed >= MAX_PUBLIC_MESSAGES_PER_RUN or messages_processed >= MAX_MESSAGES_PER_RUN:
                        state["global_search_query_index"] = query_index
                        write_state(state)
                        log.info("Public-search budget reached; cursor saved and joined-group scan will use the remaining message budget.")
                        break
                    state["global_search_query_index"] = (query_index + 1) % len(GLOBAL_GROUP_SEARCH_QUERIES)
                    write_state(state)
                    continue

                global_search_state[query] = {"last_scanned_at": query_max_date}
                state["global_search_query_index"] = (query_index + 1) % len(GLOBAL_GROUP_SEARCH_QUERIES)
                write_state(state)
                global_search_complete += 1


            # Groups with a history of genuine buyer signals are checked first.
            dialogs.sort(
                key=lambda dialog: group_priority(
                    groups_state.get(str(dialog.entity.id), {})
                ),
                reverse=True,
            )

            for dialog in dialogs:
                if messages_processed >= MAX_MESSAGES_PER_RUN:
                    log.info("Per-run message limit reached; remaining joined groups resume next run.")
                    break
                if asyncio.get_running_loop().time() - scan_started >= SCAN_BUDGET_SECONDS:
                    log.info("Scan time budget reached; remaining joined groups resume next run.")
                    break
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
                messages_since_checkpoint = 0
                async for msg in client.iter_messages(entity, **message_scan_kwargs(last_seen, cutoff)):
                    if messages_processed >= MAX_MESSAGES_PER_RUN:
                        break
                    if asyncio.get_running_loop().time() - scan_started >= SCAN_BUDGET_SECONDS:
                        break
                    if not msg:
                        continue

                    # Checkpoint only the previous batch before processing this message.
                    # If the worker stops mid-message, this message remains eligible for retry.
                    if messages_since_checkpoint >= 25 and not group_write_failed:
                        meta["last_seen_id"] = max(last_seen, newest_seen)
                        write_state(state)
                        messages_since_checkpoint = 0

                    newest_seen = max(newest_seen, int(msg.id))
                    messages_since_checkpoint += 1
                    public_message_key = (repr(getattr(msg, "peer_id", None)), int(getattr(msg, "id", 0) or 0))
                    if public_message_key in run_seen_public_messages:
                        continue
                    run_seen_public_messages.add(public_message_key)
                    messages_processed += 1
                    if getattr(msg, "out", False):
                        continue
                    if not msg.message or not msg.date:
                        continue
                    if not last_seen and msg.date.replace(tzinfo=timezone.utc) < cutoff:
                        continue

                    text_body = msg.message.strip()
                    messages_checked += 1
                    meta["messages_seen"] = int(meta.get("messages_seen", 0)) + 1
                    if SELLER_AD_CONTEXT.search(text_body) or SELLER_POST_CONTEXT.search(text_body):
                        seller_posts += 1
                        meta["seller_ads"] = int(meta.get("seller_ads", 0)) + 1

                    services = classify(text_body)
                    if not services:
                        continue
                    buyer_signals += 1
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
                            + (f"Telegram User ID: {getattr(sender, 'id', None)}. " if getattr(sender, "id", None) is not None else "Telegram User ID unavailable. ")
                            + (f"Public sender username: @{username}. " if username else "Public sender username unavailable. ")
                            + ("Direct message permalink unavailable for this group type. " if not group_url else "Message permalink recorded. ")
                            + "Verify the sender's role, project identity, and current service need before outreach."
                        ),
                        "dedupe_key": dedupe(group_id, msg.id, getattr(sender, "id", None), text_body),
                    }
                    if payload["dedupe_key"] in run_seen_dedupe_keys:
                        save_status = "duplicate"
                    else:
                        save_status = await save_lead(http, payload)
                        if save_status in ("saved", "duplicate"):
                            run_seen_dedupe_keys.add(payload["dedupe_key"])
                    if save_status == "saved":
                        saved += 1
                        meta["qualified_leads"] = int(meta.get("qualified_leads", 0)) + 1
                    elif save_status == "duplicate":
                        duplicates += 1
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


            newly_discovered_groups = global_group_ids - joined_group_ids
            log.info(
                "Global public-group search: %s queries completed, %s incomplete, %s new groups discovered.",
                global_search_complete, global_search_incomplete, len(newly_discovered_groups),
            )

            write_state(state)
            await notify_pending_leads(http)
            duration_seconds = asyncio.get_running_loop().time() - scan_started
            await send_scan_report(http, {
                "joined_groups_available": len(dialogs),
                "joined_groups_scanned": checked,
                "groups_paused": paused,
                "public_groups_found": len(newly_discovered_groups),
                "global_queries_completed": global_search_complete,
                "global_queries_incomplete": global_search_incomplete,
                "public_groups_with_buyer_signals": len(global_group_ids),
                "public_messages_processed": public_messages_processed,
                "public_messages_checked": public_messages_checked,
                "public_buyer_signals": public_buyer_signals,
                "public_leads_saved": public_leads_saved,
                "joined_messages_checked": messages_checked - public_messages_checked,
                "joined_buyer_signals": buyer_signals - public_buyer_signals,
                "joined_leads_saved": saved - public_leads_saved,
                "public_duplicates": public_duplicates,
                "joined_duplicates": duplicates - public_duplicates,
                "messages_checked": messages_checked,
                "messages_processed": messages_processed,
                "seller_posts": seller_posts,
                "buyer_signals": buyer_signals,
                "leads_saved": saved,
                "duplicates": duplicates,
                "duration_seconds": duration_seconds,
            })
            log.info(
                "Scan complete: %s/%s joined groups checked; %s total messages processed (%s cap, %s public budget); %s public messages; %s text messages checked; %s new leads saved; %.1fs.",
                checked, len(dialogs), messages_processed, MAX_MESSAGES_PER_RUN, MAX_PUBLIC_MESSAGES_PER_RUN, public_messages_processed, messages_checked, saved, duration_seconds
            )
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
