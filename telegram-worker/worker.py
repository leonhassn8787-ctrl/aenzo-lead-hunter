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
from telethon.tl.types import User

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
BOT_CHAT_IDS = list(dict.fromkeys(
    chat_id.strip()
    for chat_id in [BOT_CHAT_ID, *os.getenv("AENZO_BOT_CHAT_IDS", "").split(",")]
    if chat_id.strip()
))
POLL_SECONDS = bounded_int_env("POLL_SECONDS", 7200, 60, 86400)
LOOKBACK_DAYS = bounded_int_env("LOOKBACK_DAYS", 30, 1, 3650)
CLASSIFIER_RULES_VERSION = 26


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
CRYPTO_CONTEXT = re.compile(r"\b(web3|crypto|blockchain|solana|memecoins?|defi|cefi|cex|token|wallet|exchange|launchpad|staking|mining|rwa|gamefi|metaverse|ai agent|trading|forex|telegram|airdrop|dapp|testnet|layer[- ]?[12])\b", re.I)
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
    r"(we|i) (specialize|specialise) in (providing|proving|supplying|selling|offering) .{0,140}\b(advertising|ad|meta|tiktok|google|facebook) .{0,60}\b(accounts?|credit lines?|services?|solutions?)\b|"
    r"(we|i) (provide|offer|supply|sell) .{0,120}\b(advertising|ad|meta|tiktok|google|facebook) .{0,60}\b(accounts?|credit lines?|services?|solutions?)\b|"
    r"\b(reliable|trusted|verified) (advertising|ad) account (provider|supplier)\b|"
    r"\b(if you are|if you'?re) looking for .{0,80}\b(advertising account provider|ad account provider|account supplier)\b.{0,80}\b(contact|dm|message|reach)\b|"
    r"\bsuitable for all (products|businesses|industries)\b|"
    r"performance[- ]based collaboration.{0,180}no upfront payments?|"
    r"no upfront payments?.{0,180}(milestone|performance[- ]based|kpi)|"
    r"we (offer|provide|specialize in|are offering|can provide) (web3 |crypto )?(marketing|promotion|kol|influencer|pr|ama|community management|social media|advertising|lead generation|ad account|campaign management|growth) (services|packages|solutions|support|campaigns)|"
    r"we (help|support|work with|only deal with|deliver|supply|give you access to) (advertisers|businesses|brands|clients|media buyers|agencies|accounts|leads)|"
    r"i (offer|provide|specialize in|help|support|work with|only deal with|deliver|supply) (advertisers|businesses|brands|clients|media buyers|agencies|accounts|leads)|"
    r"we give you access to .{0,100}(database|data|lead|tool)|"
    r"(our|my) (database|data|leads|accounts|services|solutions|packages) (include|are available|available)|"
    r"fresh crypto,? investors?,? business,? depositors?.{0,100}(leads|data)|"
    r"(taboola|meta|google|tiktok|facebook) (ad )?accounts? (available|for rent|for sale)|"
    r"premium advertising network solutions|advertising network solutions|"
    r"business owners, media buyers and agencies are welcome|"
    r"(mediago|quantcast|moloco).{0,120}(programmatic advertising|traffic|lead generation)|"
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
    r"launchpad.{0,100}(no upfront|without upfront|no (upfront )?fees?|does not take upfront|do not take upfront|who (does not|doesn\'t|do not|don\'t|not) take (or tack )?(any )?upfront fees?)|"
    r"anyone looking for (a )?free (marketing|lead generation|automation) (and|\+|or).{0,80}tool|"
    r"(our|my) telegram channel provides access to .{0,100}(contact|investor|email|phone|lead) (collections|datasets|data)|"
    r"premium global contact data services|"
    r"growth network is open for new projects|"
    r"(global partners|partner recruitment).{0,300}(referral rewards|team commissions|first deposit|minimum first deposit)|"
    r"(regional|country) representatives.{0,250}(referral rewards|team commissions|first deposit)|"
    r"daily paid promotions? available|"
    r"hiring (telegram )?promoters for (daily )?paid promotions|"
    r"we are looking for promoters for paid promotions|"
    r"(head|director|manager) of sales at .{0,80}\b(agency|media|marketing|traffic|influencer)\b|"
    r"we work with (the )?(best|top|leading) .{0,100}\b(streamers?|influencers?|kols?|publishers?|affiliates?)\b|"
    r"we work with .{0,120}\b(streamers?|influencers?|kols?)\b.{0,180}\b(ftds?|high[- ]quality traffic|targeted traffic|qualified leads|paid campaigns?)\b|"
    r"if you are looking for .{0,120}\b(ftds?|high[- ]quality traffic|targeted traffic|qualified leads)\b.{0,100}\b(let.s connect|lets connect|dm me|contact us)\b|"
    r"we'?re currently taking on new .{0,80}projects looking to grow through"
    r")\b",
    re.I,
)

# Clear first-person service pitches are vendor posts, even when they mention client demand.
SELLER_PITCH_CONTEXT = re.compile(
    r"\b("
    r"(we|i) (offer|provide|deliver|sell|supply|run|manage) .{0,180}\b(kol|influencer|shilling|traffic|promotion|marketing|pr|ama|community management|social media|advertising|lead generation|campaign management|user acquisition)\b.{0,180}\b(services?|packages?|solutions?|campaigns?|clients?|projects?|registrations?|ftds?|depositors?)\b|"
    r"(we|i) (provide|offer|deliver|sell|supply|drive) .{0,260}\b(quality |high[- ]velocity |high[- ]quality |premium |real |active |targeted )?(traffic|registrations?|signups?|leads?|ftds?|first[- ]time depositors?)\b|"
    r"(traffic|lead generation) (stats|packages|services|solutions).{0,180}(price list|pricing|rates|book (your )?slot|dm|contact)|"
    r"(price list|book (your )?slot).{0,180}(traffic|targeted growth|giveaways|api integration)|"
    r"(we|i) (are|am) (a|an) .{0,50}\b(marketing|promotion|influencer|kol|traffic|advertising|growth|media) (agency|provider|supplier|team|service|network)\b|"
    r"(we|i) (are )?(looking for|seeking) (new )?(clients|projects) (to promote|for promotion|for marketing)|"
    r"looking for clients.{0,100}(marketing|promotion|kol|influencer|pr|traffic)|"
    r"(dm|contact|message) (me|us) (for )?(rates|pricing|packages|to book|for services)|"
    r"available for (paid )?(promotions?|campaigns?|marketing services)|"
    r"(marketing|kol|influencer|traffic|promotion) packages available|"
    r"we work with .{0,100}\b(projects|brands|clients)\b.{0,100}\b(promote|promotion|campaigns|traffic|leads)\b|"
    r"\b(google ppc|meta ads|facebook ads|instagram ads|telegram ads)\b.{0,180}\b(traffic|registrations?|ftds?|depositors?)\b.{0,180}\b(we provide|we offer|we deliver|our service|our traffic)\b|"
    r"\b(igaming|casino|sportsbook)\b.{0,180}\b(traffic|ftds?|first[- ]time depositors?|registrations?)\b.{0,180}\b(we provide|we offer|we deliver|across [0-9]+ geos|geo[s]?)\b|"
    r"looking for (real|genuine|active) users?.{0,100}(genuine )?engagement.{0,60}\b(x|twitter)\b|"
    r"(i|we)(?:\s+will|'ll) offer .{0,100}\b(special )?discounts?\b.{0,100}\b(dm|message|contact)\b|"
    r"(run|launch) your campaigns? .{0,100}(directly )?(on|through) our website|"
    r"test (anything|any service|any campaign) (for|at) \$?1\b"
    r")",
    re.I,
)

RECRUITMENT_BUYER_CONTEXT = re.compile(
    r"\b(our project|our team|our company|our platform|our protocol|we are hiring|we're hiring|hiring for our|for our (web3 |crypto )?(project|wallet|platform|protocol|token|community)|need (a |an )?(moderator|community manager|developer) for|looking for (a |an )?(moderator|community manager|developer) for)\b",
    re.I,
)

KOL_PROJECT_CONTEXT = re.compile(
    r"\b("
    r"(our|the) (new |upcoming |launched )?(web3|crypto|blockchain|ai|defi|cefi) (game|app|startup|project|token|launchpad|wallet|exchange|platform|ecosystem|protocol|campaign)|"
    r"(our|the) (web3 |crypto |ai |defi |cefi )?(project|token|launch|campaign|protocol|wallet|exchange|platform|community|ecosystem)|"
    r"for our (web3|crypto|token|project|launch|campaign|exchange|platform|ecosystem)|"
    r"(web3|crypto|ai agent|defi|cefi|cex) (launch|project|ecosystem|exchange|platform)|"
    r"token launch|token sale|exchange volume|web3 launch|crypto launch|paid (kol|influencer) campaign|kol campaign|influencer campaign|"
    r"budget|hire (a |an )?(kol|kols|influencer)|"
    r"(bring|attract|acquire) (traders|users|creators|builders) to (our|the|its) (project|exchange|ecosystem|platform)|"
    r"(hiring|looking for|seeking) (growth )?(marketers?|kols?|influencers?) to (bring|attract|acquire)|"
    r"(cex|exchange) kols?[, ]+.{0,100}(traders|users|campaign|promot)|"
    r"bring .{0,80}(traders|users|creators|builders).{0,60}(project|exchange|ecosystem|platform)|"
    r"hiring .{0,80}(growth )?(marketers?|kols?|influencers?).{0,100}(project|ecosystem|exchange|platform|ai agent)"
    r")\b",
    re.I,
)

# Individual creative-role hiring is not a marketing agency/service purchase.
INDIVIDUAL_CREATIVE_ROLE_CONTEXT = re.compile(
    r"\b(looking for|seeking|hiring|need|want to hire)\s+(?:an?\s+)?"
    r"(content specialists?|video editors?|copywriters?|graphic designers?|motion designers?)\b",
    re.I,
)
CAPITAL_RAISE_CONTEXT = re.compile(
    r"\b(looking for|seeking|need|raising|raise|want to raise)\b.{0,80}\b"
    r"(additional funds?|funding|investment|investors?|capital|liquidity)\b|"
    r"\b(sell|selling)\s+(the\s+)?(project|company)\b|"
    r"\bproject for sale\b|\blisting contract\b",
    re.I,
)
DIRECT_SERVICE_BUY_REQUEST_CONTEXT = re.compile(
    r"\b(looking for|need|seeking|want to hire|hiring|we need|we are looking for)\b"
    r".{0,120}\b(marketing (agency|team|partner|service|services|campaign)|"
    r"growth (agency|team|partner)|kol(s)?|influencers?|community (promotion|growth|management)|"
    r"member acquisition|pr (agency|partner|service|services)|ama (host|hosting)|content (marketing|distribution)|"
    r"video production|promotional video|giveaway campaign|airdrop campaign|"
    r"social media marketing|user acquisition|website (design|development)|"
    r"brand ambassadors?|paid campaign)\b",
    re.I,
)

NON_BUYER_CONTEXT = re.compile(
    r"\b(looking for a job|need a job|seeking (a )?job|looking for work|available for work|"
    r"open to (the )?(next|new) (opportunity|role|position)|open to opportunities|open to new projects|open to projects|"
    r"looking for (my )?(next|new) (opportunity|role|position)|seeking (a )?(new )?(role|position|opportunity)|"
    r"looking for (a )?(new )?(role|position|opportunity)|available for (a )?(new )?(role|position|opportunity)|"
    r"anyone hiring|is anyone hiring|who is hiring|job opportunities|employment opportunities|"
    r"looking to join (a |your |any )?team|"
    r"you need (marketing|promotion|kols?|influencers?) (in|for)|you should (hire|look for|find) a? ?(marketing|growth) (agency|team)|"
    r"looking for (cross[- ]promotion|co[- ]marketing|mutual promotion) (partners?|partnerships?)|"
    r"(cross[- ]promotion|co[- ]marketing|mutual promotion).{0,100}(exchange of exposure|promote each other|in return|barter|free promotion)|"
    r"(promote each other|exchange of exposure|in return for exposure|barter promotion)|"
    r"will anyone ever need (a )?(moderator|community manager|developer)( here)?|"
    r"does anyone need (a )?(moderator|community manager|developer) here|"
    r"looking for traders? in kol(s)?|"
    r"looking for bd partners|bd partners to onboard|partner recruitment|"
    r"looking for (affiliate|affiliates|ambassadors?|referral partners?|regional representatives)|"
    r"join our (affiliate|ambassador|referral|partner) program|"
    r"open to mutually beneficial collaborations|open for (pr )?collaborations|"
    r"seeking collaborations with (web3 |crypto )?(projects|communities|media partners)|"
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
    r"guest signup open|guest speakers?|join us as guest speakers|"
    r"looking for founders,? kols?,? and project representatives to join us|"
    r"looking for projects for sale|"
    r"private investors.{0,100}looking for (projects|investment opportunities)|"
    r"looking for projects to fund|"
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

def rotate_group_ids(group_ids, last_group_id=None):
    """Rotate joined-group order so message-heavy groups cannot starve the rest."""
    ids = [str(group_id) for group_id in group_ids]
    if not ids:
        return []
    try:
        start = (ids.index(str(last_group_id)) + 1) % len(ids)
    except (ValueError, TypeError):
        start = 0
    return ids[start:] + ids[:start]


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
        or INDIVIDUAL_CREATIVE_ROLE_CONTEXT.search(text)
        or (CAPITAL_RAISE_CONTEXT.search(text) and not DIRECT_SERVICE_BUY_REQUEST_CONTEXT.search(text))
        or (
            NON_BUYER_CONTEXT.search(text)
            and not (
                CRYPTO_CONTEXT.search(text)
                and re.search(
                    r"\b(early users?|early adopters?|beta testers?|product feedback|mvp testing|"
                    r"looking to hire .{0,60}(kol|kols|influencer|marketing|growth)|"
                    r"hiring .{0,60}(kol|kols|influencer|marketing|growth))\b",
                    text,
                    re.I,
                )
            )
        )
        or SELLER_AD_CONTEXT.search(text)
        or SELLER_POST_CONTEXT.search(text)
        or SELLER_PITCH_CONTEXT.search(text)
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
        r"growth agency|growth team|growth partner|community growth|community promotion|community engagement|member acquisition|pr agency|pr partner|media coverage|"
        r"press release|ama hosting|giveaway campaign|airdrop campaign|"
        r"social media management|content marketing|content distribution|content creators?|brand ambassadors?|"
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
        r"can someone help|anyone able to|could use|"
        r"struggling to|not getting enough|trying to increase|"
        r"trying to grow|want to grow|want to increase|want to attract|"
        r"we are looking for|we're looking for|we need|we are seeking|"
        r"looking to onboard|who handles|recommend a (marketing|growth|pr) agency|"
        r"partner with (a |an )?(web3 |crypto )?marketing agency|"
        r"looking for a (web3 |crypto )?marketing partner|"
        r"interested in hiring a (web3 |crypto )?marketing team)\b",
        re.I,
    )

    identified_project_context = CRYPTO_CONTEXT.search(text) or re.search(
        r"\b(project|product|app|platform|website|software|saas|digital product|"
        r"startup|brand|launch|game|exchange|wallet|protocol)\b",
        text,
        re.I,
    )
    if not identified_project_context:
        return []

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

    # KOL requests must identify a real project, campaign, or acquisition goal.
    if "KOL & Influencer Marketing" in hits and not KOL_PROJECT_CONTEXT.search(text):
        return []

    # Buyer intent and project context are checked by the shared evidence
    # verifier below. Avoid narrower legacy KOL/recruitment regex gates here:
    # they incorrectly discard genuine project-side requests with new wording.

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
            r"\b(kol|kols|influencer|influencers|marketing|promotion|promote|growth agency|growth team|growth partner|"
            r"community engagement|member acquisition|brand ambassadors?|content creators?|"
            r"advertising|pr agency|pr partner|media coverage|press release|ama hosting|"
            r"giveaway campaign|airdrop campaign|social media management|"
            r"content marketing|content distribution|brand awareness|"
            r"user acquisition|launch promotion|project promotion|paid campaign)\b",
            re.I,
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
        if strong_marketing_intent.search(text) or (
            growth_demand.search(text)
            and (CRYPTO_CONTEXT.search(text) or digital_project_context.search(text))
        ):
            hits = ["Project Promotion"]
        else:
            return []

    return hits


def verify_buyer_evidence(text):
    """Independent evidence gate: prove project context, a buyer request, and an AENZO service need."""
    if not text:
        return False
    if INDIVIDUAL_CREATIVE_ROLE_CONTEXT.search(text):
        return False
    if CAPITAL_RAISE_CONTEXT.search(text) and not DIRECT_SERVICE_BUY_REQUEST_CONTEXT.search(text):
        return False
    if SELLER_AD_CONTEXT.search(text) or SELLER_POST_CONTEXT.search(text) or SELLER_PITCH_CONTEXT.search(text):
        return False
    if NON_BUYER_CONTEXT.search(text) and not (
        CRYPTO_CONTEXT.search(text)
        and re.search(
            r"\b(early users?|early adopters?|beta testers?|product feedback|mvp testing|"
            r"looking to hire .{0,60}(kol|kols|influencer|marketing|growth)|"
            r"hiring .{0,60}(kol|kols|influencer|marketing|growth))\b",
            text, re.I,
        )
    ):
        return False

    buyer_request = BUYING_CONTEXT.search(text) or re.search(
        r"\b(we need|we're seeking|we are seeking|want to hire|ready to hire|"
        r"looking to hire|looking to work with|searching for|seeking|hiring|"
        r"can you promote|please promote|help us promote|need a partner|"
        r"anyone know|does anyone know|can someone help|anyone able to|"
        r"who can help|could use|recommend a)\b",
        text, re.I,
    )
    indirect_growth = re.search(
        r"\b(struggling to|having trouble|not getting (enough|many)|"
        r"trying to (increase|grow|attract|reach)|want to (grow|increase|attract|reach)|"
        r"could use more|how can we (get|attract|reach|grow|increase)|"
        r"what.s the best way to (get|attract|reach|grow|increase)|"
        r"looking to grow|looking to increase|want to boost|need more)\b",
        text, re.I,
    )
    service_need = re.search(
        r"\b(kol|kols|influencers?|marketing (agency|team|partner|service|services|campaign)|"
        r"paid marketing|promotion (agency|partner|service|campaign)|promote our project|"
        r"growth (agency|team|partner|service|marketing)|"
        r"community (growth|promotion|management|engagement)|"
        r"telegram (promotion|member acquisition|community growth)|member acquisition|"
        r"pr (agency|partner|service|services)|media coverage|press release|ama hosting|ama|"
        r"giveaway campaign|airdrop campaign|social media management|social media marketing|"
        r"content marketing|content distribution|content creators?|brand ambassadors?|"
        r"influencer outreach|sponsored posts?|brand awareness|"
        r"user acquisition|more users|grow users|increase users|attract users|"
        r"grow our audience|increase visibility|community engagement|"
        r"launch promotion|project promotion|advertising|paid campaign|promoters?|"
        r"website (design|development|developer)|community manager|moderators?|developers?|"
        r"beta testers?|early users?|product testing|product review|product feedback|mvp testing|"
        r"video production|graphic design|fundraising promotion|"
        r"exchange promotion|wallet promotion|gamefi promotion|"
        r"staking promotion|mining promotion)\b",
        text, re.I,
    )
    project_context = CRYPTO_CONTEXT.search(text) or re.search(
        r"\b(project|product|app|platform|website|software|saas|"
        r"digital product|startup|brand|game|exchange|wallet|"
        r"web3|crypto|blockchain|defi|cefi|cex|token|launchpad|"
        r"ai agent|gamefi|rwa|protocol)\b",
        text, re.I,
    )
    if not project_context or not service_need:
        return False
    if not buyer_request and not (indirect_growth and service_need):
        return False
    # project_context is already mandatory above. Do not apply narrower
    # KOL/recruitment wording gates here: they reject legitimate requests such
    # as "our new crypto game needs KOLs" or "hire moderators for our DeFi app".
    return True


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


def two_hour_window(anchor, now):
    """Return the latest fully completed two-hour window anchored to the first start."""
    anchor = anchor.astimezone(timezone.utc)
    now = now.astimezone(timezone.utc)
    elapsed = (now - anchor).total_seconds()
    if elapsed < 7200:
        return None
    completed_index = int(elapsed // 7200) - 1
    start = anchor + timedelta(hours=2 * completed_index)
    return start, start + timedelta(hours=2)


def message_scan_kwargs(window_start):
    """Read messages chronologically from this window start; caller stops at its end."""
    return {"offset_date": window_start, "reverse": True}

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

async def audit_current_scan_leads(client_http, scan_run_id):
    """Audit only the leads created by this exact scan run."""

    headers = supabase_headers(SUPABASE_SERVICE_ROLE_KEY)
    url = f"{SUPABASE_URL}/rest/v1/leads"
    base_params = {
        "select": "id,evidence_summary,service_need,notes,priority_score",
        "owner_id": f"eq.{SUPABASE_OWNER_ID}",
        "status": "eq.new",
        "source_scan_run_id": "eq." + str(scan_run_id),
        "order": "created_at.asc,id.asc", "limit": "200",
    }
    audited = rejected = verified = review = 0
    try:
        # Fetch every page before changing statuses. Updating rows while using
        # offset pagination would shift the remaining result set and skip leads.
        pending = []
        offset = 0
        while True:
            params = {**base_params, "offset": str(offset)}
            response = await client_http.get(url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                log.error("Post-scan audit could not load leads (%s): %s", response.status_code, response.text[:400])
                return {"audited": 0, "rejected": 0, "verified": 0, "review": 0, "ok": False}
            page = response.json()
            pending.extend(page)
            if len(page) < 200:
                break
            offset += len(page)
        for lead in pending:
            audited += 1
            evidence = str(lead.get("evidence_summary") or "").strip()
            stored_need = str(lead.get("service_need") or "").strip()
            seller = bool(SELLER_AD_CONTEXT.search(evidence) or SELLER_POST_CONTEXT.search(evidence) or SELLER_PITCH_CONTEXT.search(evidence))
            # Classification is discovery-only and cannot override the final evidence gate.
            proven = (
                len(evidence) >= 25
                and not seller
                and verify_buyer_evidence(evidence)
            )
            if not proven:
                # Clear sellers are held; ambiguous or incomplete evidence remains in manual review.
                # Preserve records: failed candidates go to manual review, never auto-reject.
                target_status = "review"
                reason = (
                    "post_scan_audit: clear_service_seller_held_for_manual_review"
                    if seller
                    else "post_scan_audit: buyer_intent_uncertain_manual_review_required"
                )
                notes = (str(lead.get("notes") or "").strip() + " | " + reason).strip(" |")[:4000]
                patch = await client_http.patch(
                    url, headers={**headers, "Prefer": "return=minimal"},
                    params={"id": "eq." + str(lead["id"]), "owner_id": "eq." + SUPABASE_OWNER_ID, "status": "eq.new"},
                    json={"status": target_status, "notes": notes}, timeout=30
                )
                if patch.status_code not in (200, 204):
                    log.error("Post-scan audit could not update lead %s (%s): %s", lead["id"], patch.status_code, patch.text[:300])
                    return {"audited": audited, "rejected": rejected, "verified": verified, "review": review, "ok": False}
                review += 1
                log.info("Post-scan audit held unverified candidate %s for manual review (%s).", lead["id"], reason)
                continue

            inferred = classify(evidence)
            repaired_need = "; ".join(inferred) if inferred else (stored_need or "Project Promotion")
            notes = str(lead.get("notes") or "").strip()
            marker = "post_scan_audit: buyer_intent_verified"
            if marker not in notes:
                notes = (notes + " | " + marker).strip(" |")
            patch_payload = {"notes": notes[:4000]}
            if repaired_need != stored_need:
                patch_payload["service_need"] = repaired_need
                repair_marker = "post_scan_audit: service_label_repaired"
                if repair_marker not in notes:
                    notes = (notes + " | " + repair_marker).strip(" |")
                patch_payload["notes"] = notes[:4000]
            if patch_payload["notes"] != str(lead.get("notes") or "").strip() or repaired_need != stored_need:
                patch = await client_http.patch(
                    url,
                    headers={**headers, "Prefer": "return=minimal"},
                    params={"id": "eq." + str(lead["id"]), "owner_id": "eq." + SUPABASE_OWNER_ID, "status": "eq.new"},
                    json=patch_payload,
                    timeout=30,
                )
                if patch.status_code not in (200, 204):
                    log.error("Could not record verified buyer audit for lead %s (%s): %s", lead["id"], patch.status_code, patch.text[:300])
                    return {"audited": audited, "rejected": rejected, "verified": verified, "review": review, "ok": False}
            verified += 1
        log.info("Post-scan evidence audit complete: %s checked, %s verified buyers kept, %s held for review; no candidates were auto-rejected.", audited, verified, review)
        return {"audited": audited, "rejected": rejected, "verified": verified, "review": review, "ok": True}
    except Exception:
        log.exception("Post-scan lead audit failed.")
        return {"audited": audited, "rejected": rejected, "verified": verified, "review": review, "ok": False}


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

def telegram_notification_block_reason(lead):
    """Fail closed: only notify when stored evidence independently passes buyer rules."""
    evidence = str(lead.get("evidence_summary") or "").strip()
    service_need = str(lead.get("service_need") or "").strip()
    if len(evidence) < 25:
        return "missing_or_too_short_evidence"
    if not service_need or service_need.lower() in {"unknown", "needs review", "n/a", "none"}:
        return "missing_service_need"
    if SELLER_AD_CONTEXT.search(evidence) or SELLER_POST_CONTEXT.search(evidence) or SELLER_PITCH_CONTEXT.search(evidence):
        return "seller_or_vendor_post"
    notes = str(lead.get("notes") or "")
    if "post_scan_audit: buyer_intent_verified" not in notes:
        return "missing_post_scan_buyer_audit"
    # Discovery classification cannot substitute for the independent audit.
    if not verify_buyer_evidence(evidence):
        return "source_evidence_does_not_prove_buyer_intent"
    return None


async def send_telegram_to_chat(http, chat_id, message, timeout=30):
    """Send to one destination so partial successes can be recorded independently."""
    if not BOT_TOKEN or not chat_id:
        return False, "Telegram bot token or chat ID is not configured."
    try:
        response = await http.post(
            "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage",
            json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
            timeout=timeout,
        )
        if response.status_code != 200 or not response.json().get("ok"):
            return False, response.text[:300]
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def recipient_key(chat_id):
    """Store a stable hash, never the raw Telegram chat ID, in delivery state."""
    return hashlib.sha256(str(chat_id).encode("utf-8")).hexdigest()[:20]


async def notify_pending_leads(http):
    summary = {
        "alerts_configured": bool(BOT_TOKEN and BOT_CHAT_IDS),
        "pending_alerts_loaded": 0,
        "alerts_delivered": 0,
        "alerts_failed": 0,
        "leads_moved_to_review": 0,
        "alert_load_error": False,
    }
    if not summary["alerts_configured"]:
        log.info("Telegram bot alerts not configured; scanning continues.")
        return summary

    headers = supabase_headers(SUPABASE_SERVICE_ROLE_KEY)
    url = SUPABASE_URL + "/rest/v1/leads"
    base_params = {
        "select": "id,company_name,service_need,priority_score,evidence_date,evidence_summary,evidence_url,telegram_group_url,contacts,outreach_english,outreach_bengali,telegram_deliveries,notes",
        "owner_id": "eq." + SUPABASE_OWNER_ID,
        "status": "eq.new",
        "telegram_notified_at": "is.null",
        "order": "created_at.asc,id.asc",
        "limit": "100",
    }

    # Load every page before changing any status; the deterministic tie-breaker
    # keeps offset pagination stable when several leads share created_at.
    pending = []
    offset = 0
    try:
        while True:
            params = {**base_params, "offset": str(offset)}
            response = await http.get(url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                log.error("Could not load pending Telegram alerts (%s): %s", response.status_code, response.text[:300])
                summary["alert_load_error"] = True
                return summary
            page = response.json()
            pending.extend(page)
            if len(page) < 100:
                break
            offset += len(page)
    except Exception:
        log.exception("Could not load pending Telegram alerts.")
        summary["alert_load_error"] = True
        return summary

    summary["pending_alerts_loaded"] = len(pending)
    log.info("Loaded %s pending Telegram alerts for strict review.", len(pending))

    for lead in pending:
        lead_id = lead.get("id")
        block_reason = telegram_notification_block_reason(lead)
        if block_reason:
            log.warning("Telegram alert blocked for lead %s by strict buyer-evidence gate: %s", lead_id, block_reason)
            try:
                old_notes = str(lead.get("notes") or "").strip()
                review_note = "telegram_gate: " + block_reason
                if review_note not in old_notes:
                    old_notes = (old_notes + " | " + review_note).strip(" |")[:4000]
                reviewed = await http.patch(
                    url,
                    headers={**headers, "Prefer": "return=minimal"},
                    params={"id": "eq." + str(lead_id), "owner_id": "eq." + SUPABASE_OWNER_ID, "status": "eq.new"},
                    json={"status": "review", "notes": old_notes},
                    timeout=30,
                )
                if reviewed.status_code not in (200, 204):
                    summary["alerts_failed"] += 1
                    log.error("Could not move blocked lead %s to manual review (%s): %s", lead_id, reviewed.status_code, reviewed.text[:300])
                else:
                    summary["leads_moved_to_review"] += 1
                    log.info("Blocked lead %s safely retained in manual review: %s", lead_id, block_reason)
            except Exception:
                summary["alerts_failed"] += 1
                log.exception("Could not move blocked lead %s to manual review.", lead_id)
            continue

        try:
            delivery_state = lead.get("telegram_deliveries") or {}
            if not isinstance(delivery_state, dict):
                delivery_state = {}
            all_delivered = True
            for chat_id in BOT_CHAT_IDS:
                key = recipient_key(chat_id)
                if delivery_state.get(key):
                    continue
                delivered, error = await send_telegram_to_chat(
                    http, chat_id, format_telegram_lead(lead), timeout=30
                )
                if not delivered:
                    all_delivered = False
                    detail = f"{key}: {error}"[:500]
                    log.error("Telegram alert failed for lead %s: %s", lead_id, detail)
                    try:
                        await http.patch(
                            url,
                            headers={**headers, "Prefer": "return=minimal"},
                            params={"id": "eq." + str(lead_id), "owner_id": "eq." + SUPABASE_OWNER_ID},
                            json={"telegram_notification_error": detail},
                            timeout=30,
                        )
                    except Exception:
                        log.exception("Could not record Telegram alert error for lead %s.", lead_id)
                    continue

                delivery_state[key] = datetime.now(timezone.utc).isoformat()
                recorded = await http.patch(
                    url,
                    headers={**headers, "Prefer": "return=minimal"},
                    params={"id": "eq." + str(lead_id), "owner_id": "eq." + SUPABASE_OWNER_ID},
                    json={"telegram_deliveries": delivery_state},
                    timeout=30,
                )
                if recorded.status_code not in (200, 204):
                    all_delivered = False
                    log.error(
                        "Telegram delivered lead %s to one chat, but per-chat delivery state could not be recorded (%s).",
                        lead_id, recorded.status_code,
                    )
                    break

            if all_delivered and all(delivery_state.get(recipient_key(chat_id)) for chat_id in BOT_CHAT_IDS):
                marked = await http.patch(
                    url,
                    headers={**headers, "Prefer": "return=minimal"},
                    params={"id": "eq." + str(lead_id), "owner_id": "eq." + SUPABASE_OWNER_ID},
                    json={"telegram_notified_at": datetime.now(timezone.utc).isoformat(), "telegram_notification_error": None},
                    timeout=30,
                )
                if marked.status_code not in (200, 204):
                    summary["alerts_failed"] += 1
                    log.error("All recipients received lead %s, but final notification timestamp could not be recorded (%s).", lead_id, marked.status_code)
                else:
                    summary["alerts_delivered"] += 1
                    log.info("Telegram alert delivered and recorded for lead %s.", lead_id)
            else:
                summary["alerts_failed"] += 1
        except Exception:
            summary["alerts_failed"] += 1
            log.exception("Telegram notification attempt failed for lead %s; it will be retried.", lead_id)

    return summary



async def scan_window_already_recorded(http, window_start):
    """Only completed windows are skipped; running/failed windows resume."""
    url = f"{SUPABASE_URL}/rest/v1/scan_runs"
    response = await http.get(url, headers=supabase_headers(SUPABASE_SERVICE_ROLE_KEY), params={
        "select": "id,status", "owner_id": "eq." + SUPABASE_OWNER_ID,
        "window_start": "eq." + window_start.isoformat(), "order": "started_at.desc", "limit": "10",
    }, timeout=20)
    if response.status_code != 200:
        raise RuntimeError(f"Could not verify scan window ({response.status_code}): {response.text[:300]}")
    return any(row.get("status") == "completed" for row in response.json())


async def start_scan_run(http, window_start, window_end):
    """Reuse a prior unfinished run instead of treating it as a completed window."""
    url = f"{SUPABASE_URL}/rest/v1/scan_runs"
    headers = supabase_headers(SUPABASE_SERVICE_ROLE_KEY)
    params = {"select": "id,status", "owner_id": "eq." + SUPABASE_OWNER_ID,
              "window_start": "eq." + window_start.isoformat(), "order": "started_at.desc", "limit": "1"}
    existing = await http.get(url, headers=headers, params=params, timeout=20)
    if existing.status_code != 200:
        raise RuntimeError(f"Could not load prior scan run ({existing.status_code}): {existing.text[:300]}")
    rows = existing.json()
    if rows:
        row = rows[0]
        if row.get("status") == "completed":
            return "completed"
        run_id = row["id"]
        resumed = await http.patch(url, headers={**headers, "Prefer": "return=minimal"},
            params={"id": "eq." + str(run_id), "owner_id": "eq." + SUPABASE_OWNER_ID},
            json={"status": "running", "finished_at": None}, timeout=20)
        if resumed.status_code not in (200, 204):
            raise RuntimeError(f"Could not resume scan run ({resumed.status_code}): {resumed.text[:300]}")
        return run_id
    headers["Prefer"] = "return=representation"
    response = await http.post(url, headers=headers, json={
        "owner_id": SUPABASE_OWNER_ID, "status": "running",
        "window_start": window_start.isoformat(), "window_end": window_end.isoformat(),
        "error_summary": json.dumps({"phase": "running"}, separators=(",", ":")),
    }, timeout=20)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Could not create scan run ({response.status_code}): {response.text[:300]}")
    rows = response.json()
    if not rows:
        raise RuntimeError("Supabase did not return the new scan run ID.")
    return rows[0]["id"]


async def finish_scan_run(http, run_id, stats):
    """Persist scan-window columns and detailed joined-group telemetry to Supabase."""
    if not run_id:
        return
    url = f"{SUPABASE_URL}/rest/v1/scan_runs"
    headers = supabase_headers(SUPABASE_SERVICE_ROLE_KEY)
    headers["Prefer"] = "return=minimal"
    telemetry = {
        "window_start": stats.get("window_start"),
        "window_end": stats.get("window_end"),
        "joined_groups_scanned": stats.get("joined_groups_scanned", 0),
        "joined_messages_processed": stats.get("joined_messages_processed", 0),
        "message_count_limit": "unlimited",
        "joined_messages_checked": stats.get("joined_messages_checked", 0),
        "joined_buyer_signals": stats.get("joined_buyer_signals", 0),
        "joined_leads_saved": stats.get("joined_leads_saved", 0),
        "joined_duplicates": stats.get("joined_duplicates", 0),
        "seller_posts": stats.get("seller_posts", 0),
        "duration_seconds": round(stats.get("duration_seconds", 0), 1),
        "scan_errors": int(stats.get("scan_errors", 0)),
        "post_scan_audit_ok": bool(stats.get("post_scan_audit_ok")),
        "post_scan_review": int(stats.get("post_scan_review", 0)),
        "alerts_configured": bool(stats.get("alerts_configured")),
        "pending_alerts_loaded": int(stats.get("pending_alerts_loaded", 0)),
        "alerts_delivered": int(stats.get("alerts_delivered", 0)),
        "alerts_failed": int(stats.get("alerts_failed", 0)),
        "leads_moved_to_review": int(stats.get("leads_moved_to_review", 0)),
        "alert_load_error": bool(stats.get("alert_load_error")),
    }
    payload = {
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed" if int(stats.get("scan_errors", 0)) > 0 or not stats.get("post_scan_audit_ok") else "completed",
        "sources_checked": int(stats.get("joined_groups_scanned", 0)),
        "leads_found": int(stats.get("buyer_signals", 0)),
        "leads_saved": int(stats.get("leads_saved", 0)),
        "error_summary": json.dumps(telemetry, separators=(",", ":"))[:3000],
    }
    try:
        response = await http.patch(
            url,
            headers=headers,
            params={"id": "eq." + str(run_id), "owner_id": "eq." + SUPABASE_OWNER_ID},
            json=payload,
            timeout=20,
        )
        if response.status_code not in (200, 204):
            log.error("Could not update Supabase scan_runs row (%s): %s", response.status_code, response.text[:300])
            return False
        return True
    except Exception:
        log.exception("Could not update Supabase scan_runs row.")
        return False


async def mark_scan_run_failed(http, run_id, error):
    """Close a started scan as failed if Telegram iteration or processing raises."""
    if not run_id:
        return
    url = f"{SUPABASE_URL}/rest/v1/scan_runs"
    headers = supabase_headers(SUPABASE_SERVICE_ROLE_KEY)
    headers["Prefer"] = "return=minimal"
    try:
        response = await http.patch(url, headers=headers, params={"id": "eq." + str(run_id), "owner_id": "eq." + SUPABASE_OWNER_ID}, json={"finished_at": datetime.now(timezone.utc).isoformat(), "status": "failed", "error_summary": json.dumps({"phase": "failed", "error": str(error)[:1500]}, separators=(",", ":"))}, timeout=20)
        if response.status_code not in (200, 204):
            log.error("Could not mark scan run %s as failed (%s): %s", run_id, response.status_code, response.text[:300])
    except Exception:
        log.exception("Could not mark scan run %s as failed.", run_id)


async def send_scan_report(http, stats, scan_run_id=None):
    """Send a compact per-run scan-usage report to the owner's Telegram chat."""
    if not BOT_TOKEN or not BOT_CHAT_IDS:
        log.info("Telegram scan reports are not configured; skipping scan report.")
        if scan_run_id:
            try:
                headers = supabase_headers(SUPABASE_SERVICE_ROLE_KEY)
                recorded = await http.patch(
                    f"{SUPABASE_URL}/rest/v1/scan_runs",
                    headers={**headers, "Prefer": "return=minimal"},
                    params={"id": "eq." + str(scan_run_id), "owner_id": "eq." + SUPABASE_OWNER_ID},
                    json={"report_delivery_error": "disabled: bot token or chat ID is not configured"},
                    timeout=20,
                )
                if recorded.status_code not in (200, 204):
                    log.error("Could not record disabled Telegram scan report delivery (%s): %s", recorded.status_code, recorded.text[:300])
            except Exception:
                log.exception("Could not record that Telegram scan report delivery is disabled.")
        return False
    minutes = int(stats.get("duration_seconds", 0)) // 60
    seconds = int(stats.get("duration_seconds", 0)) % 60
    report = (
        "📊 AENZO LABS SCAN REPORT\n\n"
        f"Joined groups available: {stats.get('joined_groups_available', 0)}\n"
        f"Joined groups selected this run: {stats.get('joined_groups_selected', 0)}\n"
        f"Two-hour window (UTC): {stats.get('window_start', 'n/a')} → {stats.get('window_end', 'n/a')}\n"
        f"Joined groups checked: {stats.get('joined_groups_scanned', 0)}\n"
        f"Joined-group messages processed: {stats.get('joined_messages_processed', 0):,}\n"
        f"Joined-group messages checked: {stats.get('joined_messages_checked', 0):,}\n"
        f"Joined-group buyer signals: {stats.get('joined_buyer_signals', 0):,}\n"
        f"Joined-group leads saved: {stats.get('joined_leads_saved', 0)}\n"
        f"Joined-group duplicate leads: {stats.get('joined_duplicates', 0)}\n"
        f"Messages processed this run: {stats.get('messages_processed', 0):,} (no message-count limit)\n"
        f"Text messages checked: {stats.get('messages_checked', 0):,}\n"
        f"Seller/vendor posts: {stats.get('seller_posts', 0):,}\n"
        f"Buyer signals: {stats.get('buyer_signals', 0):,}\n"
        f"New leads saved: {stats.get('leads_saved', 0)}\n"
        f"Duplicate leads: {stats.get('duplicates', 0)}\n"
        f"Processing errors: {stats.get('scan_errors', 0)}\n"
        f"Post-scan audit status: {'SUCCESS' if stats.get('post_scan_audit_ok') else 'FAILED — alerts withheld'}\n"
        f"Post-scan audit: {stats.get('post_scan_audited', 0)} checked | {stats.get('post_scan_verified', 0)} verified | {stats.get('post_scan_review', 0)} held for review | {stats.get('post_scan_rejected', 0)} auto-rejected\n"
        f"Telegram lead alerts: {'enabled' if stats.get('alerts_configured') else 'disabled'} | {stats.get('alerts_delivered', 0)} delivered | {stats.get('alerts_failed', 0)} failed | {stats.get('leads_moved_to_review', 0)} moved to review\n"
        f"Pending alerts loaded: {stats.get('pending_alerts_loaded', 0)} | Alert queue read error: {stats.get('alert_load_error', False)}\n"
        f"Scan duration: {minutes}m {seconds}s\n\n"
        f"Collection window (UTC): {stats.get('window_start', 'n/a')} to {stats.get('window_end', 'n/a')}\n"
        "Only joined Telegram groups are scanned. Incomplete windows resume from the last successfully processed message; windows advance only after all groups and the audit finish."
    )
    try:
        if not scan_run_id:
            log.error("Cannot persist Telegram scan report delivery without a scan run ID.")
            return False
        headers = supabase_headers(SUPABASE_SERVICE_ROLE_KEY)
        url = f"{SUPABASE_URL}/rest/v1/scan_runs"
        delivery_state = {}
        errors = []
        for chat_id in BOT_CHAT_IDS:
            key = recipient_key(chat_id)
            delivered, error = await send_telegram_to_chat(http, chat_id, report, timeout=30)
            if not delivered:
                errors.append(f"{key}: {error}")
                continue
            delivery_state[key] = datetime.now(timezone.utc).isoformat()
            saved = await http.patch(url, headers={**headers, "Prefer": "return=minimal"}, params={"id": "eq." + str(scan_run_id), "owner_id": "eq." + SUPABASE_OWNER_ID}, json={"report_deliveries": delivery_state}, timeout=30)
            if saved.status_code not in (200, 204):
                errors.append(f"{key}: delivered but database record failed ({saved.status_code})")
                log.error("Telegram scan report reached one chat but its delivery record failed.")
        all_sent = len(delivery_state) == len(BOT_CHAT_IDS) and not errors
        final_payload = {"report_delivery_error": "; ".join(errors)[:1000] if errors else None}
        if all_sent:
            final_payload["report_delivered_at"] = datetime.now(timezone.utc).isoformat()
        final = await http.patch(url, headers={**headers, "Prefer": "return=minimal"}, params={"id": "eq." + str(scan_run_id), "owner_id": "eq." + SUPABASE_OWNER_ID}, json=final_payload, timeout=30)
        if final.status_code not in (200, 204):
            log.error("Could not persist final scan report delivery status (%s).", final.status_code)
            return False
        if all_sent:
            log.info("Telegram scan report delivered and recorded for %s chat(s).", len(BOT_CHAT_IDS))
        else:
            log.error("Telegram scan report partially delivered or failed: %s", "; ".join(errors)[:500])
        return all_sent
    except Exception:
        log.exception("Could not send or record Telegram scan report.")
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
        password = getpass.getpass("Telegram 2-step verification password: ")
        await client.sign_in(password=password)
    log.info("Telegram account authorized. Keep the session file private.")

async def run(once=False):
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    session = StringSession(SESSION_STRING) if SESSION_STRING else None
    client = TelegramClient(session if session else str(SESSION_FILE), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("Telegram session is not authorized.")
    state = read_state()
    if reset_group_quality_metrics(state):
        write_state(state)
    groups_state = state.setdefault("groups", {})
    initial_start = os.getenv("INITIAL_SCAN_START_AT", "").strip()
    if initial_start:
        initial_dt = datetime.fromisoformat(initial_start.replace("Z", "+00:00"))
        if initial_dt.tzinfo is None:
            initial_dt = initial_dt.replace(tzinfo=timezone.utc)
        configured_anchor = initial_dt.astimezone(timezone.utc).isoformat()
        if state.get("initial_scan_since") != configured_anchor:
            state["initial_scan_since"] = configured_anchor
            state.setdefault("next_window_start", configured_anchor)
            write_state(state)
    elif not state.get("initial_scan_since"):
        anchor = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        state["initial_scan_since"] = anchor.isoformat()
        state["next_window_start"] = anchor.isoformat()
        write_state(state)
    anchor = datetime.fromisoformat(state["initial_scan_since"])
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    anchor = anchor.astimezone(timezone.utc)
    state.setdefault("next_window_start", anchor.isoformat())

    async with httpx.AsyncClient() as http:
        while True:
            window_start = datetime.fromisoformat(state["next_window_start"])
            if window_start.tzinfo is None:
                window_start = window_start.replace(tzinfo=timezone.utc)
            window_start = window_start.astimezone(timezone.utc)
            window_end = window_start + timedelta(hours=2)
            if datetime.now(timezone.utc) < window_end:
                log.info("Next two-hour window is still collecting until %s.", window_end.isoformat())
                break
            if await scan_window_already_recorded(http, window_start):
                state["next_window_start"] = window_end.isoformat()
                write_state(state)
                if once:
                    break
                continue

            scan_started = asyncio.get_running_loop().time()
            scan_run_id = await start_scan_run(http, window_start, window_end)
            if scan_run_id == "completed":
                state["next_window_start"] = window_end.isoformat()
                write_state(state)
                if once:
                    break
                continue

            all_progress = state.setdefault("window_progress", {})
            window_key = window_start.isoformat()
            window_progress = all_progress.setdefault(window_key, {"groups": {}})
            group_progress = window_progress.setdefault("groups", {})
            try:
                dialogs = []
                async for dialog in client.iter_dialogs():
                    entity = dialog.entity
                    if bool(getattr(dialog, "is_group", False)) and not bool(getattr(entity, "broadcast", False)):
                        dialogs.append(dialog)
                dialogs.sort(key=lambda d: group_priority(groups_state.get(str(d.entity.id), {})), reverse=True)
                dialog_map = {str(d.entity.id): d for d in dialogs}
                ordered_ids = rotate_group_ids(dialog_map.keys(), state.get("joined_group_cursor"))
                dialogs = [dialog_map[group_id] for group_id in ordered_ids]
                checked = saved = messages_checked = messages_processed = 0
                joined_messages_processed = seller_posts = buyer_signals = duplicates = 0
                run_seen_dedupe_keys = set()

                async def process_message(msg, entity, group_id, meta):
                    nonlocal saved, messages_checked, messages_processed, joined_messages_processed
                    nonlocal seller_posts, buyer_signals, duplicates
                    if not msg or not msg.date:
                        return
                    msg_date = msg.date
                    if msg_date.tzinfo is None:
                        msg_date = msg_date.replace(tzinfo=timezone.utc)
                    else:
                        msg_date = msg_date.astimezone(timezone.utc)
                    if msg_date < window_start or msg_date >= window_end:
                        return
                    messages_processed += 1
                    joined_messages_processed += 1
                    if getattr(msg, "out", False) or not msg.message:
                        return
                    text_body = msg.message.strip()
                    messages_checked += 1
                    meta["messages_seen"] = int(meta.get("messages_seen", 0)) + 1
                    if SELLER_AD_CONTEXT.search(text_body) or SELLER_POST_CONTEXT.search(text_body) or SELLER_PITCH_CONTEXT.search(text_body):
                        seller_posts += 1
                        meta["seller_ads"] = int(meta.get("seller_ads", 0)) + 1
                    services = classify(text_body)
                    if not services:
                        return
                    try:
                        sender = await msg.get_sender()
                    except Exception as exc:
                        raise RuntimeError(f"Sender lookup failed in group {group_id}, message {msg.id}: {exc}") from exc
                    if not is_human_sender(sender):
                        return
                    buyer_signals += 1
                    meta["buyer_signals"] = int(meta.get("buyer_signals", 0)) + 1
                    username = getattr(sender, "username", None)
                    group_name = (getattr(entity, "title", None) or "Telegram group").strip()
                    public_name = getattr(entity, "username", None)
                    group_url = make_message_url(entity, msg.id)
                    en, bn = make_outreach(services)
                    payload = {
                        "owner_id": SUPABASE_OWNER_ID, "source_scan_run_id": scan_run_id,
                        "company_name": "Potential project (verify)", "website": None,
                        "industry": "Web3 / Crypto", "service_need": "; ".join(services),
                        "lead_type": "potential_buyer", "priority_score": priority(text_body, services),
                        "status": "new", "evidence_summary": text_body[:3500], "evidence_url": group_url,
                        "evidence_date": msg_date.date().isoformat(),
                        "telegram_group_url": f"https://t.me/{public_name}" if public_name else group_url,
                        "contacts": extract_public_contacts(text_body, username),
                        "outreach_english": en, "outreach_bengali": bn,
                        "notes": ("Auto-detected buying-intent candidate; not independently verified. "
                            f"Source group: {group_name}. Message ID: {msg.id}. "
                            + (f"Telegram User ID: {getattr(sender, 'id', None)}. " if getattr(sender, "id", None) is not None else "Telegram User ID unavailable. ")
                            + (f"Public sender username: @{username}. " if username else "Public sender username unavailable. ")
                            + ("Direct message permalink unavailable for this group type. " if not group_url else "Message permalink recorded. ")
                            + "Verify the sender's role, project identity, and current service need before outreach."),
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
                    else:
                        raise RuntimeError(f"Lead save failed for group {group_id}, message {msg.id}; cursor will not advance.")

                for dialog in dialogs:
                    entity = dialog.entity
                    group_id = str(entity.id)
                    gp = group_progress.setdefault(group_id, {"last_message_id": 0, "done": False})
                    if gp.get("done"):
                        continue
                    meta = groups_state.setdefault(group_id, {
                        "last_seen_id": 0, "messages_seen": 0, "seller_ads": 0,
                        "buyer_signals": 0, "qualified_leads": 0, "paused_until": None,
                    })
                    kwargs = message_scan_kwargs(window_start)
                    kwargs["min_id"] = int(gp.get("last_message_id", 0) or 0)
                    async for msg in client.iter_messages(entity, **kwargs):
                        if not msg or not msg.id:
                            continue
                        if msg.date:
                            dt = msg.date
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            else:
                                dt = dt.astimezone(timezone.utc)
                            if dt >= window_end:
                                break
                        # Older boundary messages are harmlessly filtered by process_message,
                        # then checkpointed too so a boundary item cannot block resume forever.
                        # Persist after every successfully processed message; a failure leaves its ID untouched.
                        await process_message(msg, entity, group_id, meta)
                        gp["last_message_id"] = int(msg.id)
                        meta["last_seen_id"] = max(int(meta.get("last_seen_id", 0) or 0), int(msg.id))
                        write_state(state)
                    gp["done"] = True
                    checked += 1
                    state["joined_group_cursor"] = group_id
                    write_state(state)

                unfinished = [gid for gid in dialog_map if not group_progress.get(gid, {}).get("done")]
                if unfinished:
                    raise RuntimeError("Unfinished joined groups remain: " + ", ".join(unfinished[:20]))

                audit_result = await audit_current_scan_leads(http, scan_run_id)
                alert_stats = {
                    "alerts_configured": bool(BOT_TOKEN and BOT_CHAT_IDS), "pending_alerts_loaded": 0,
                    "alerts_delivered": 0, "alerts_failed": 0, "leads_moved_to_review": 0,
                    "alert_load_error": False,
                }
                if audit_result["ok"]:
                    alert_stats = await notify_pending_leads(http)
                duration_seconds = asyncio.get_running_loop().time() - scan_started
                stats = {
                    "window_start": window_start.isoformat(), "window_end": window_end.isoformat(),
                    "joined_groups_available": len(dialogs), "joined_groups_selected": len(dialogs),
                    "joined_groups_scanned": checked, "joined_messages_processed": joined_messages_processed,
                    "joined_messages_checked": messages_checked, "joined_buyer_signals": buyer_signals,
                    "joined_leads_saved": saved, "joined_duplicates": duplicates,
                    "messages_checked": messages_checked, "messages_processed": messages_processed,
                    "message_count_limit": "unlimited", "seller_posts": seller_posts,
                    "buyer_signals": buyer_signals, "leads_saved": saved, "duplicates": duplicates,
                    "duration_seconds": duration_seconds, "post_scan_audited": audit_result["audited"],
                    "post_scan_rejected": audit_result["rejected"], "post_scan_review": audit_result.get("review", 0),
                    "post_scan_verified": audit_result["verified"], "post_scan_audit_ok": audit_result["ok"],
                    "scan_errors": 0, **alert_stats,
                }
                if not audit_result["ok"]:
                    log.error("Post-scan audit failed; pending-lead notifications withheld for safety.")
                    raise RuntimeError("Post-scan audit failed; this window will resume and be audited again.")
                if not await finish_scan_run(http, scan_run_id, stats):
                    raise RuntimeError("Could not persist completed scan metrics.")
                await send_scan_report(http, stats, scan_run_id)
                state["next_window_start"] = window_end.isoformat()
                all_progress.pop(window_key, None)
                write_state(state)
                log.info("Completed two-hour window: %s groups, %s messages, %s new leads.",
                         checked, joined_messages_processed, saved)
            except Exception as exc:
                await mark_scan_run_failed(http, scan_run_id, exc)
                log.exception("Window remains incomplete; retrying from the last saved message.")
                if once:
                    raise
                retry_after = max(30, min(int(getattr(exc, "seconds", 60) or 60), 900))
                await asyncio.sleep(retry_after)
                continue
            if once:
                break
        if not once:
            next_start = datetime.fromisoformat(state["next_window_start"])
            if next_start.tzinfo is None:
                next_start = next_start.replace(tzinfo=timezone.utc)
            next_end = next_start.astimezone(timezone.utc) + timedelta(hours=2)
            seconds_until_next_window = max(1, (next_end - datetime.now(timezone.utc)).total_seconds())
            await asyncio.sleep(min(POLL_SECONDS, seconds_until_next_window))

if __name__ == "__main__":
    if "--login" in sys.argv:
        async def do_login():
            client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
            await login(client)
            await client.disconnect()
        asyncio.run(do_login())
    else:
        asyncio.run(run(once="--once" in sys.argv))
