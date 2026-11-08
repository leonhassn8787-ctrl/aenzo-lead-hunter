import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
OWNER_ID = os.environ["SUPABASE_OWNER_ID"]
BOT_TOKEN = os.getenv("AENZO_BOT_TOKEN", "").strip()
BOT_CHAT_ID = os.getenv("AENZO_BOT_CHAT_ID", "").strip()
LOOKBACK_DAYS = int(os.getenv("WEB_LOOKBACK_DAYS", "10"))
MAX_ITEMS_PER_SOURCE = int(os.getenv("WEB_MAX_ITEMS_PER_SOURCE", "35"))
HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": "Bearer " + SERVICE_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def google_news(domain, terms):
    query = f"site:{domain} ({terms})"
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return "https://news.google.com/rss/search?" + params

# Official public RSS feeds are used where available. For directory sites without
# a verified public feed/API key, Google News RSS is only a discovery index.
SOURCES = [
    {"name": "RootData", "url": "https://www.rootdata.com/", "feed": google_news("rootdata.com", "funding OR fundraising OR launch OR project"), "kind": "funding_signal"},
    {"name": "CryptoRank", "url": "https://cryptorank.io/funding-rounds", "feed": google_news("cryptorank.io", "funding OR fundraising OR launchpad OR token sale"), "kind": "funding_signal"},
    {"name": "VCBacked", "url": "https://www.vcbacked.co/directory/industries/web3", "feed": google_news("vcbacked.co", "web3 startup OR funding OR portfolio"), "kind": "funding_signal"},
    {"name": "Product Hunt", "url": "https://www.producthunt.com/", "feed": "https://www.producthunt.com/feed", "kind": "product_launch"},
    {"name": "DappRadar", "url": "https://dappradar.com/narratives/icos", "feed": google_news("dappradar.com", "new dapp OR launch OR blockchain game OR token"), "kind": "launch_signal"},
    {"name": "TGE Index", "url": "https://tgeindex.com/tge/", "feed": google_news("tgeindex.com", "upcoming TGE OR token generation event OR launch"), "kind": "token_launch"},
    {"name": "CoinDesk", "url": "https://www.coindesk.com/", "feed": "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml", "kind": "news_signal"},
    {"name": "Crunchbase", "url": "https://www.crunchbase.com/", "feed": google_news("crunchbase.com", "web3 OR crypto OR AI startup funding raised"), "kind": "funding_signal"},
    {"name": "ProjectStartups", "url": "https://projectstartups.com/pages/crypto-web3/", "feed": google_news("projectstartups.com", "crypto OR web3 startup funding launch"), "kind": "funding_signal"},
    {"name": "Meridial", "url": "https://meridial.io/intelligence/funding", "feed": google_news("meridial.io", "crypto funding OR web3 funding"), "kind": "funding_signal"},
    {"name": "Grants Watch", "url": "https://grants.watch/", "feed": google_news("grants.watch", "web3 OR blockchain OR crypto grant"), "kind": "grant_signal"},
    {"name": "HackList", "url": "https://hacklist.io/", "feed": google_news("hacklist.io", "web3 hackathon OR blockchain hackathon OR project"), "kind": "ecosystem_signal"},
    {"name": "OpenVC", "url": "https://www.openvc.app/investor-lists/web3-investors", "feed": google_news("openvc.app", "web3 startup OR crypto startup OR portfolio"), "kind": "funding_signal"},
]

POSITIVE = re.compile(
    r"\b(raised|raises|raising|funding|fundraise|seed round|series [a-d]|"
    r"grant|grants|accelerator|incubator|launches|launched|launching|"
    r"mainnet|testnet|token generation|tge|token sale|ido|ico|ieo|"
    r"product launch|new product|beta launch|public launch|"
    r"partnership|expansion|ecosystem fund|builder program|hackathon)\b", re.I
)
RELEVANT = re.compile(
    r"\b(web3|crypto|blockchain|defi|cefi|wallet|exchange|token|"
    r"ai agent|artificial intelligence|saas|gamefi|rwa|dapp|"
    r"metaverse|stablecoin|launchpad|onchain|bitcoin|ethereum|solana)\b", re.I
)
BUYING = re.compile(
    r"\\b(looking for (?:a |an |the )?(?:kol|kols|marketing|growth|community|pr|influencer|agency|team|partner|promotion)|"
    r"need (?:a |an |the )?(?:kol|kols|marketing|growth|community|pr|influencer|agency|team|partner|promotion)|"
    r"need help with (?:our )?(?:marketing|growth|community|promotion)|"
    r"hiring (?:a |an )?(?:marketing|growth|community|pr|influencer)|"
    r"seeking (?:a |an )?(?:marketing|growth|community|pr|influencer|agency|partner)|"
    r"want to hire (?:a |an )?(?:marketing|growth|community|pr|influencer)|"
    r"looking to hire (?:a |an )?(?:marketing|growth|community|pr|influencer))\\b", re.I
)
INCIDENT = re.compile(r"\\b(breach|hack|exploit|attack|scam|fraud|lawsuit|vulnerability|outage|liquidation|liquidated|price prediction|market update)\\b", re.I)
GENERIC_DIRECTORY = re.compile(r"funding rounds, token sale review & tokenomics analysis", re.I)
VENDOR = re.compile(
    r"\b(we offer|we provide|our services|marketing packages|"
    r"available for promotion|dm for rates|buy our|sell our)\b", re.I
)

def api(method, path, payload=None, prefer=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = dict(HEADERS)
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(SUPABASE_URL + "/rest/v1/" + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=35) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw else None

def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()

def parse_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return None

def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = root.findall(".//item")
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//atom:entry", ns)
    output = []
    for item in items[:MAX_ITEMS_PER_SOURCE]:
        def get_text(names):
            for name in names:
                found = item.find(name)
                if found is not None and found.text:
                    return found.text.strip()
            return ""
        title = get_text(["title", "{http://www.w3.org/2005/Atom}title"])
        link = get_text(["link", "{http://www.w3.org/2005/Atom}link"])
        if not link:
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            if atom_link is not None:
                link = atom_link.attrib.get("href", "")
        summary = get_text(["description", "summary", "{http://www.w3.org/2005/Atom}summary", "content"])
        published = get_text(["pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"])
        if title and link.startswith("http"):
            output.append({"title": clean_text(title)[:500], "summary": clean_text(summary)[:3000], "url": link, "published": parse_date(published)})
    return output

def classify(item, kind):
    title = item["title"]
    text = title + " " + item["summary"]
    if not RELEVANT.search(text) or not POSITIVE.search(text):
        return None
    if VENDOR.search(text) or INCIDENT.search(title) or GENERIC_DIRECTORY.search(title):
        return None
    score = 38
    if re.search(r"\b(raised|raises|funding|seed round|series [a-d]|grant|accelerator)\b", text, re.I):
        score += 22
    if re.search(r"\b(launches|launched|launching|mainnet|testnet|tge|token sale|ido|ico|product launch)\b", text, re.I):
        score += 18
    if BUYING.search(text):
        score += 20
    if re.search(r"\$\s?\d|\b(million|million|billion)\b", text, re.I):
        score += 5
    return min(score, 90)

def extract_marketing_need(text):
    match = BUYING.search(text or "")
    return match.group(0) if match else None

def telegram_send(text):
    if not BOT_TOKEN or not BOT_CHAT_ID:
        return
    body = urllib.parse.urlencode({"chat_id": BOT_CHAT_ID, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.loads(response.read().decode())
        if not payload.get("ok"):
            raise RuntimeError("Telegram notification failed")

def main():
    started = datetime.now(timezone.utc)
    run = api("POST", "scan_runs", {"owner_id": OWNER_ID, "status": "running"}, "return=representation")
    run_id = run[0]["id"]
    existing = api("GET", "lead_sources?select=id,source_name&owner_id=eq." + OWNER_ID)
    source_ids = {row["source_name"]: row["id"] for row in (existing or [])}
    checked = 0
    candidates = []
    errors = []
    cutoff = started - timedelta(days=LOOKBACK_DAYS)

    for source in SOURCES:
        try:
            request = urllib.request.Request(source["feed"], headers={"User-Agent": "AENZO-LeadHunter/1.0 (+public RSS discovery)"})
            with urllib.request.urlopen(request, timeout=30) as response:
                feed_items = parse_feed(response.read())
            checked += 1
            source_id = source_ids.get(source["name"])
            for item in feed_items:
                if item["published"] and item["published"] < cutoff:
                    continue
                score = classify(item, source["kind"])
                if score is None:
                    continue
                dedupe = hashlib.sha256(item["url"].split("#")[0].rstrip("/").encode()).hexdigest()
                candidates.append({
                    "owner_id": OWNER_ID,
                    "source_id": source_id,
                    "source_name": source["name"],
                    "title": item["title"],
                    "summary": item["summary"][:2500] or "Public project/funding/launch signal. Verify official project details and actual marketing need.",
                    "evidence_url": item["url"],
                    "published_at": item["published"].isoformat() if item["published"] else None,
                    "signal_type": source["kind"],
                    "signal_score": score,
                    "buyer_intent_status": "explicit_need" if extract_marketing_need(item["title"] + " " + item["summary"]) else "no_explicit_need",
                    "marketing_need": extract_marketing_need(item["title"] + " " + item["summary"]),
                    "public_contacts": [],
                    "enrichment_status": "pending",
                    "review_status": "new",
                    "dedupe_key": dedupe,
                })
            if source_id:
                api("PATCH", "lead_sources?id=eq." + source_id, {"last_checked_at": datetime.now(timezone.utc).isoformat()})
        except Exception as exc:
            errors.append(source["name"] + ": " + str(exc)[:180])

    inserted = []
    # Small batches prevent request-size limits and preserve idempotent exact-URL dedupe.
    for offset in range(0, len(candidates), 40):
        batch = candidates[offset:offset + 40]
        if batch:
            rows = api("POST", "discovery_candidates?on_conflict=owner_id,dedupe_key", batch, "resolution=ignore-duplicates,return=representation")
            inserted.extend(rows or [])

    finished = datetime.now(timezone.utc)
    api("PATCH", "scan_runs?id=eq." + run_id, {
        "finished_at": finished.isoformat(),
        "status": "completed" if not errors else "completed",
        "sources_checked": checked,
        "leads_found": len(candidates),
        "leads_saved": len(inserted),
        "error_summary": ("; ".join(errors)[:3000] if errors else None),
    })
    lines = [
        "AENZO LABS — Web Discovery Scan",
        f"Sources checked: {checked}/{len(SOURCES)}",
        f"Potential signals found: {len(candidates)}",
        f"New candidates saved: {len(inserted)}",
        "Only explicit marketing requests are buyer-intent signals; funding/launch news remains unverified.",
    ]
    for row in inserted[:8]:
        lines.append("• " + row["source_name"] + ": " + row["title"][:100] + "\n" + row["evidence_url"])
    if errors:
        lines.append("Feed errors: " + "; ".join(errors[:5]))
    report = "\n".join(lines)
    print(report)
    if inserted or errors:
        telegram_send(report)
    if checked == 0:
        raise SystemExit("No web sources could be checked; inspect feed/network errors.")

if __name__ == "__main__":
    main()
