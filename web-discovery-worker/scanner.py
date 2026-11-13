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
    r"mainnet|testnet|"
    r"product launch|new product|beta launch|public launch|"
    r"partnership|expansion|ecosystem fund|builder program|hackathon)\b", re.I
)
RELEVANT = re.compile(
    r"\b(web3|crypto|blockchain|defi|cefi|wallet|exchange|token|"
    r"ai agent|artificial intelligence|saas|gamefi|rwa|dapp|"
    r"metaverse|stablecoin|launchpad|onchain|bitcoin|ethereum|solana)\b", re.I
)
BUYING = re.compile(
    r"\b(looking for (?:a |an |the )?(?:kol|kols|marketing|growth|community|pr|influencer|agency|team|partner|promotion)|"
    r"need (?:a |an |the )?(?:kol|kols|marketing|growth|community|pr|influencer|agency|team|partner|promotion)|"
    r"need help with (?:our )?(?:marketing|growth|community|promotion)|"
    r"hiring (?:a |an )?(?:marketing|growth|community|pr|influencer)|"
    r"seeking (?:a |an )?(?:marketing|growth|community|pr|influencer|agency|partner)|"
    r"want to hire (?:a |an )?(?:marketing|growth|community|pr|influencer)|"
    r"looking to hire (?:a |an )?(?:marketing|growth|community|pr|influencer))\b", re.I
)
INCIDENT = re.compile(r"\b(breach|hack(?:ed|ing)?|exploit(?:ed)?|attack(?:ed)?|scam|fraud|lawsuit|vulnerability|outage|liquidation|liquidated|price prediction|market update|rug pull|phishing|stolen funds|drained|compromised|data leak|security incident|bankruptcy|insolvency|investigation)\b", re.I)
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

def filter_enabled_sources(source_configs, source_rows):
    """Only scan configured sources explicitly enabled in the owner's source table."""
    active_names = {
        row.get("source_name")
        for row in (source_rows or [])
        if row.get("is_active") is True and row.get("source_name")
    }
    return [source for source in source_configs if source["name"] in active_names]


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
    if VENDOR.search(text) or INCIDENT.search(text) or GENERIC_DIRECTORY.search(title):
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

import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_PAGE_BYTES = 1_200_000
MAX_REDIRECTS = 5
MAX_ENRICH_PER_RUN = 8
ROLE_PATTERNS = [
    ("Founder", re.compile(r"\b(founder|co-founder)\b", re.I)),
    ("CEO", re.compile(r"\b(chief executive officer|ceo)\b", re.I)),
    ("Business Development", re.compile(r"\b(business development|bizdev|bd lead|bd manager)\b", re.I)),
    ("Marketing", re.compile(r"\b(marketing director|head of marketing|marketing manager|cmo)\b", re.I)),
]

def validate_public_url(url):
    """Allow only public HTTP(S) destinations; re-check every redirect hop."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Blocked non-public URL")
    host = parsed.hostname.rstrip(".").lower()
    if host in ("localhost",) or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Blocked local hostname")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except Exception as exc:
        raise ValueError("Could not resolve public host") from exc
    if not addresses:
        raise ValueError("No public address")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global:
            raise ValueError("Blocked private or reserved network address")
    return url

class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS
    max_repeats = MAX_REDIRECTS
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        validate_public_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)

SAFE_OPENER = urllib.request.build_opener(SafeRedirectHandler)

def safe_fetch(url, limit=MAX_PAGE_BYTES):
    validate_public_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "AENZO-LeadHunter/1.0 (+public business contact research)", "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/atom+xml;q=0.9,*/*;q=0.5"})
    with SAFE_OPENER.open(req, timeout=12) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        body = response.read(limit + 1)
        if len(body) > limit:
            body = body[:limit]
        return response.geturl(), content_type, body

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.anchors = []
        self._anchor = None
        self._script_type = ""
        self._script_parts = []
        self.jsonld = []
        self.text_parts = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            value = attrs.get("content", "").strip()
            if key and value:
                self.meta[key] = value
        elif tag == "a" and attrs.get("href"):
            self._anchor = {"href": attrs["href"], "text": ""}
        elif tag == "script" and "ld+json" in attrs.get("type", "").lower():
            self._script_type = "jsonld"
            self._script_parts = []
    def handle_endtag(self, tag):
        if tag == "a" and self._anchor is not None:
            self.anchors.append(self._anchor)
            self._anchor = None
        elif tag == "script" and self._script_type == "jsonld":
            raw = "".join(self._script_parts).strip()
            if raw:
                try:
                    self.jsonld.append(json.loads(raw))
                except Exception:
                    pass
            self._script_type = ""
            self._script_parts = []
    def handle_data(self, data):
        if self._anchor is not None:
            self._anchor["text"] += " " + data
        if self._script_type == "jsonld":
            self._script_parts.append(data)
        if data.strip():
            self.text_parts.append(data.strip())

def parse_page(url, body):
    parser = PageParser()
    parser.feed(body.decode("utf-8", "replace"))
    title = clean_text(parser.meta.get("og:title") or parser.meta.get("twitter:title") or "")
    if not title:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body.decode("utf-8", "replace"), re.I | re.S)
        title = clean_text(title_match.group(1)) if title_match else ""
    canonical = ""
    for a in parser.anchors:
        if a["href"].startswith("http"):
            pass
    return {
        "title": title,
        "site_name": parser.meta.get("og:site_name", ""),
        "description": parser.meta.get("description", ""),
        "anchors": parser.anchors,
        "jsonld": parser.jsonld,
        "text": clean_text(" ".join(parser.text_parts))[:30000],
    }

def project_terms(title):
    stop = {"web3","crypto","blockchain","startup","company","raises","raised","funding","funds","series","seed","round","launch","launches","launching","project","token","million","billion","back","backs","announces","announced","new","the","and","for","with","from","into","as","a","an","to","of","on","in","at","by","its","their","wallet","exchange","protocol","platform","network","app"}
    words = re.findall(r"\b[A-Z][A-Za-z0-9&.-]{2,}\b", title or "")
    return [w.lower() for w in words if w.lower() not in stop][:5]

def is_social_host(host):
    host = (host or "").lower()
    return any(x in host for x in ("t.me","telegram.me","x.com","twitter.com","linkedin.com","discord.gg","discord.com","youtube.com","youtu.be","medium.com","github.com"))

def structured_urls(data):
    found = []
    stack = data if isinstance(data, list) else [data]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            typ = item.get("@type", "")
            if isinstance(typ, list):
                typ = " ".join(typ)
            if any(t in str(typ).lower() for t in ("organization","corporation","person","softwareapplication","product")):
                for key in ("url","sameAs","email","telephone","name","jobTitle"):
                    value = item.get(key)
                    if isinstance(value, list):
                        found.extend(v for v in value if isinstance(v, str))
                    elif isinstance(value, str):
                        found.append(value)
            stack.extend(v for v in item.values() if isinstance(v, (dict,list)))
    return found

def role_people(text):
    results = []
    patterns = [
        re.compile(r"\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})\s*(?:,|[-–|])\s*(Founder|Co-Founder|CEO|Chief Executive Officer|Head of Marketing|Marketing Director|Marketing Manager|Business Development|BD Lead|BD Manager)\b"),
        re.compile(r"\b(Founder|Co-Founder|CEO|Chief Executive Officer|Head of Marketing|Marketing Director|Marketing Manager|Business Development|BD Lead|BD Manager)\s*[:\-–]\s*([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})\b"),
        re.compile(r"\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})\s+(Founder(?:\s*&\s*CEO)?|Co-Founder|CEO|Head of Marketing|Marketing Director|Marketing Manager|Business Development|BD Lead|BD Manager)\b"),
    ]
    for pattern in patterns:
        for match in pattern.finditer(text or ""):
            if match.lastindex == 2:
                if match.group(1).lower() in ("founder","co-founder","ceo","chief executive officer","head of marketing","marketing director","marketing manager","business development","bd lead","bd manager"):
                    role, name = match.group(1), match.group(2)
                else:
                    name, role = match.group(1), match.group(2)
                if len(name.split()) >= 2:
                    results.append((name.strip(), role.strip()))
    unique = []
    seen = set()
    for name, role in results:
        key = (name.lower(), role.lower())
        if key not in seen:
            seen.add(key)
            unique.append((name, role))
    return unique[:12]

def extract_contacts(page_url, page):
    contacts = []
    seen = set()
    text = page["text"]
    def add(kind, value, url, role=None, evidence=None):
        value = (value or "").strip()
        key = (kind, value.lower())
        if value and key not in seen:
            seen.add(key)
            contacts.append({"type":kind,"value":value,"url":url,"role":role,"verification":"found_on_official_site","evidence":(evidence or "")[:240]})
    for name, role in role_people(text):
        add("person", name, page_url, role, name + " — " + role)
    for email in re.findall(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text):
        if not any(x in email.lower() for x in ("example.com","sentry.io","wixpress.com")):
            add("email", email, page_url, None, "Email displayed on official website")
    for anchor in page["anchors"]:
        target = urljoin(page_url, anchor["href"])
        parsed = urlsplit(target)
        host = parsed.netloc.lower()
        label = clean_text(anchor["text"])
        if "mailto:" in anchor["href"].lower():
            email = anchor["href"].split(":",1)[1].split("?",1)[0]
            add("email", email, page_url, None, "mailto link on official website")
        elif host and ("t.me" in host or "telegram.me" in host):
            add("telegram", target, page_url, None, "Linked from official website")
        elif host and ("x.com" in host or "twitter.com" in host):
            if not re.search(r"/(share|intent|search)(/|$)", parsed.path, re.I):
                add("x", target, page_url, None, "Linked from official website")
        elif host and "linkedin.com" in host:
            add("linkedin", target, page_url, None, "Linked from official website")
    return contacts

def choose_official_site(source_url, source_page, title, source_name):
    source_host = (urlsplit(source_url).hostname or "").lower()
    terms = project_terms(title)
    scored = {}
    for anchor in source_page["anchors"]:
        href = urljoin(source_url, anchor["href"])
        p = urlsplit(href)
        host = (p.hostname or "").lower()
        if p.scheme not in ("http","https") or not host or host == source_host or is_social_host(host):
            continue
        if any(x in host for x in ("google.com","news.google.com","coindesk.com","producthunt.com","crunchbase.com","rootdata.com","cryptorank.io","vcbacked.co","dappradar.com","tgeindex.com","projectstartups.com","meridial.io","grants.watch","hacklist.io","openvc.app")):
            continue
        label = clean_text(anchor["text"]).lower()
        score = sum(2 for term in terms if term in label)
        if source_name == "Product Hunt" and re.search(r"\b(visit website|website|official site|visit site)\b", label):
            score += 3
        if terms and any(term in host.split(".")[-2] for term in terms):
            score += 2
        if score:
            scored[host] = max(scored.get(host, (0, href)), (score, href))
    if not scored:
        return None
    host, (score, href) = max(scored.items(), key=lambda item:item[1][0])
    if score < (3 if source_name == "Product Hunt" else 2):
        return None
    return href

def find_official_site_from_related_news(title, original_url, source_name):
    """Use another public publisher's copy when the primary article blocks crawlers."""
    terms = project_terms(title)
    focus = terms[-1] if terms else title.split()[0]
    queries = [
        '"' + focus + ' Insure" website',
        '"' + focus + ' Insure" funding',
        '"' + focus + '" crypto insurer announcement',
    ]
    original_host = (urlsplit(original_url).hostname or "").lower()
    for query in queries:
        rss_url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q":query,"hl":"en-US","gl":"US","ceid":"US:en"})
        try:
            _, _, rss_body = safe_fetch(rss_url, 900000)
            items = parse_feed(rss_body)
        except Exception:
            continue
        for item in items[:10]:
            try:
                article_url, content_type, body = safe_fetch(item["url"], 900000)
                article_host = (urlsplit(article_url).hostname or "").lower()
                if not article_host or article_host == original_host:
                    continue
                if "html" not in content_type and not body.lstrip().lower().startswith((b"<!doctype html",b"<html")):
                    continue
                page = parse_page(article_url, body)
                official = choose_official_site(article_url, page, title, source_name)
                if official:
                    return official, article_url
            except Exception:
                continue
    return None, None


def search_official_site(title):
    """Try public search result pages; candidate domains are verified again by site metadata."""
    terms = project_terms(title)
    queries = [
        "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": (title + " official website").strip()}),
        "https://www.google.com/search?" + urllib.parse.urlencode({"q": (title + " official website").strip(), "num": "10"}),
        "https://www.bing.com/search?" + urllib.parse.urlencode({"q": (title + " official website").strip()}),
    ]
    excluded = ("duckduckgo.com","google.com","bing.com","yahoo.com","coindesk.com","producthunt.com","crunchbase.com","rootdata.com","cryptorank.io","vcbacked.co","dappradar.com","tgeindex.com","projectstartups.com","meridial.io","grants.watch","hacklist.io","openvc.app")
    for search_url in queries:
        try:
            final_url, content_type, body = safe_fetch(search_url, 900000)
            page = parse_page(final_url, body)
        except Exception:
            continue
        scored = {}
        for item in page["anchors"]:
            href = urljoin(final_url, item["href"])
            parsed = urlsplit(href)
            params = urllib.parse.parse_qs(parsed.query)
            for key in ("uddg","q","url"):
                if key in params and params[key][0].startswith(("http://","https://")):
                    href = urllib.parse.unquote(params[key][0])
                    parsed = urlsplit(href)
                    break
            host = (parsed.hostname or "").lower()
            if parsed.scheme not in ("http","https") or not host or is_social_host(host):
                continue
            if any(x in host for x in excluded):
                continue
            label = clean_text(item["text"]).lower()
            domain_parts = host.split(".")
            score = sum(2 for term in terms if term in label)
            score += sum(2 for term in terms if term in domain_parts)
            if score:
                scored[host] = max(scored.get(host,(0,href)),(score,href))
        if scored:
            host, (score, href) = max(scored.items(),key=lambda item:item[1][0])
            if score >= 2:
                return href
    return None

def enrich_candidate(candidate):
    result = {"project_website":None,"project_name":None,"resolved_evidence_url":None,"public_contacts":[],"enrichment_status":"failed","enrichment_error":None,"buyer_intent_status":candidate.get("buyer_intent_status","unverified")}
    try:
        resolved_url = candidate["evidence_url"]
        source_page = {"title":"","site_name":"","description":"","anchors":[],"jsonld":[],"text":""}
        try:
            resolved_url, content_type, body = safe_fetch(candidate["evidence_url"])
            if "html" in content_type or body.lstrip().lower().startswith((b"<!doctype html",b"<html")):
                result["resolved_evidence_url"] = resolved_url
                source_page = parse_page(resolved_url, body)
        except urllib.error.HTTPError as exc:
            # Preserve the final redirected publisher URL even when its page blocks automated access.
            result["resolved_evidence_url"] = exc.geturl()
            resolved_url = exc.geturl()
        except Exception as exc:
            result["enrichment_error"] = "Source page fetch failed: " + str(exc)[:150]
        official_url = choose_official_site(resolved_url, source_page, candidate.get("title",""), candidate.get("source_name",""))
        if not official_url:
            official_url, alternate_evidence = find_official_site_from_related_news(candidate.get("title",""), resolved_url, candidate.get("source_name",""))
            if alternate_evidence:
                result["resolved_evidence_url"] = alternate_evidence
        if not official_url:
            official_url = search_official_site(candidate.get("title",""))
        if not official_url:
            result["enrichment_status"] = "partial"
            result["enrichment_error"] = result.get("enrichment_error") or "Could not verify an official project website from the source page or public search results."
            return result
        official_url, official_type, official_body = safe_fetch(official_url)
        if "html" not in official_type and not official_body.lstrip().lower().startswith((b"<!doctype html",b"<html")):
            result["enrichment_status"] = "partial"
            return result
        official_page = parse_page(official_url, official_body)
        terms = project_terms(candidate.get("title",""))
        identity_text = (official_page["title"] + " " + official_page["site_name"] + " " + official_page["description"]).lower()
        identity_match = any(term in identity_text for term in terms)
        # A strong, named outbound link from the evidence page plus a functioning HTML site is required.
        # Product Hunt's explicit "Visit website" CTA is accepted as directory-provided association.
        if not identity_match and candidate.get("source_name") != "Product Hunt":
            result["enrichment_status"] = "partial"
            return result
        result["project_website"] = official_url
        result["project_name"] = official_page["site_name"] or official_page["title"] or None
        pages = [(official_url, official_page)]
        base = urlsplit(official_url)
        for path in ("/about","/about-us","/team","/our-team","/leadership","/contact","/contact-us","/company"):
            target = urlunsplit((base.scheme,base.netloc,path,"",""))
            try:
                u, ct, data = safe_fetch(target, 450000)
                if "html" in ct or data.lstrip().lower().startswith((b"<!doctype html",b"<html")):
                    pages.append((u,parse_page(u,data)))
            except Exception:
                pass
        contacts = []
        seen = set()
        for page_url, page in pages:
            for contact in extract_contacts(page_url,page):
                key = (contact["type"],contact["value"].lower())
                if key not in seen:
                    seen.add(key)
                    contacts.append(contact)
        result["public_contacts"] = contacts[:40]
        result["enrichment_status"] = "completed"
        # Explicit buyer intent must be supported by a real request in the fetched public evidence.
        combined = candidate.get("title","") + " " + candidate.get("summary","")
        need = extract_marketing_need(combined)
        result["buyer_intent_status"] = "explicit_need" if need else "no_explicit_need"
        result["marketing_need"] = need
    except Exception as exc:
        result["enrichment_status"] = "failed"
        result["enrichment_error"] = str(exc)[:220]
    return result

def main():
    started = datetime.now(timezone.utc)
    run = api("POST", "scan_runs", {"owner_id": OWNER_ID, "status": "running"}, "return=representation")
    run_id = run[0]["id"]
    existing = api("GET", "lead_sources?select=id,source_name,is_active&owner_id=eq." + OWNER_ID)
    source_ids = {row["source_name"]: row["id"] for row in (existing or [])}
    active_sources = filter_enabled_sources(SOURCES, existing or [])
    checked = 0
    candidates = []
    errors = []
    cutoff = started - timedelta(days=LOOKBACK_DAYS)

    if not active_sources:
        errors.append("No active configured discovery sources are enabled.")

    for source in active_sources:
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

    # Enrich newly inserted and previously pending candidates with public official-site evidence.
    # Contact details are only kept when found on a site linked by the source page.
    pending_query = "discovery_candidates?select=id,title,summary,evidence_url,source_name,buyer_intent_status&owner_id=eq." + OWNER_ID + "&review_status=eq.new&order=created_at.desc&limit=" + str(MAX_ENRICH_PER_RUN)
    pending = api("GET", pending_query + "&enrichment_status=eq.pending") or []
    failed = api("GET", pending_query + "&enrichment_status=eq.failed") or []
    partial = api("GET", pending_query + "&enrichment_status=eq.partial&project_website=is.null") or []
    pending = (pending + failed + partial)[:MAX_ENRICH_PER_RUN]
    enriched_count = 0
    enriched_rows = []
    for candidate in (pending or []):
        details = enrich_candidate(candidate)
        details["enriched_at"] = datetime.now(timezone.utc).isoformat()
        api("PATCH", "discovery_candidates?id=eq." + candidate["id"] + "&owner_id=eq." + OWNER_ID, details)
        enriched_rows.append({"title":candidate.get("title","Project candidate"), **details})
        enriched_count += 1

    finished = datetime.now(timezone.utc)
    api("PATCH", "scan_runs?id=eq." + run_id, {
        "finished_at": finished.isoformat(),
        "status": "failed" if checked == 0 else "completed",
        "sources_checked": checked,
        "leads_found": len(candidates),
        "leads_saved": len(inserted),
        "error_summary": ("; ".join(errors)[:3000] if errors else None),
    })
    lines = [
        "AENZO LABS — Web Discovery Scan",
        f"Sources checked: {checked}/{len(active_sources)}",
        f"Potential signals found: {len(candidates)}",
        f"New candidates saved: {len(inserted)}",
        f"Candidates enriched: {enriched_count}",
        "Only explicit marketing requests are buyer-intent signals; funding/launch news remains unverified.",
    ]
    for row in inserted[:8]:
        lines.append("• New candidate — " + row["source_name"] + ": " + row["title"][:100] + "\n" + row["evidence_url"])
    for row in enriched_rows[:8]:
        site = row.get("project_website") or "Official website not verified"
        contacts = ", ".join((item.get("type","contact") + ": " + item.get("value","")) for item in row.get("public_contacts",[])[:4]) or "No public contacts verified"
        lines.append("• Enriched — " + row.get("title","Project")[:90] + "\n" + site + "\n" + contacts)
    if errors:
        lines.append("Feed errors: " + "; ".join(errors[:5]))
    report = "\n".join(lines)
    print(report)
    if inserted or enriched_rows or errors:
        telegram_send(report)
    if checked == 0:
        raise SystemExit("No web sources could be checked; inspect feed/network errors.")

if __name__ == "__main__":
    main()
