import os
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("SUPABASE_OWNER_ID", "00000000-0000-0000-0000-000000000000")

import scanner

class ScannerTests(unittest.TestCase):
    def test_source_catalog_contains_thirteen_requested_sources(self):
        names = {source["name"] for source in scanner.SOURCES}
        self.assertEqual(len(names), 13)
        self.assertIn("Product Hunt", names)
        self.assertIn("CoinDesk", names)
        self.assertNotIn("ChainJobs", names)

    def test_parse_rss_item(self):
        xml = b"""<?xml version='1.0'?><rss><channel><item><title>Web3 startup raised $8 million funding</title><link>https://example.com/story</link><description>A blockchain project raised seed funding.</description><pubDate>Sun, 08 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
        rows = scanner.parse_feed(xml)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://example.com/story")
        self.assertIsNotNone(rows[0]["published"])

    def test_funding_signal_is_candidate_not_lead(self):
        item = {"title": "Web3 startup raised $8 million funding", "summary": "A blockchain company raised a seed round."}
        score = scanner.classify(item, "funding_signal")
        self.assertGreaterEqual(score, 50)

    def test_explicit_marketing_need_is_detected_separately(self):
        self.assertIsNotNone(scanner.extract_marketing_need("We are looking for a marketing agency for our Web3 wallet."))
        self.assertIsNotNone(scanner.extract_marketing_need("Need help with our community growth."))
        self.assertIsNone(scanner.extract_marketing_need("Our Web3 startup raised $8 million."))
    
    def test_official_site_requires_named_source_link(self):
        source_html = b'<html><body><a href="https://soter.example/">Soter</a><a href="https://random.example/">Click</a></body></html>'
        page = scanner.parse_page("https://news.example/story", source_html)
        self.assertEqual(scanner.choose_official_site("https://news.example/story", page, "Soter crypto insurer raises funding", "CoinDesk"), "https://soter.example/")

    def test_product_hunt_website_cta_is_recognized(self):
        source_html = b'<html><body><a href="https://launch.example/">Visit website</a></body></html>'
        page = scanner.parse_page("https://producthunt.com/posts/app", source_html)
        self.assertEqual(scanner.choose_official_site("https://producthunt.com/posts/app", page, "App - Web3 wallet launch", "Product Hunt"), "https://launch.example/")

    def test_public_contacts_are_extracted_with_official_page_evidence(self):
        html = b'<html><head><meta property="og:title" content="Soter"></head><body><p>John Doe, Founder</p><a href="mailto:bd@soter.example">Email BD</a><a href="https://t.me/soter">Telegram</a><a href="https://x.com/soter">X</a></body></html>'
        page = scanner.parse_page("https://soter.example/team", html)
        contacts = scanner.extract_contacts("https://soter.example/team", page)
        kinds = {item["type"] for item in contacts}
        self.assertTrue({"person","email","telegram","x"}.issubset(kinds))
        self.assertTrue(all(item["verification"] == "found_on_official_site" for item in contacts))

    def test_end_to_end_enrichment_links_official_site_and_public_contacts(self):
        source_html = b'<html><body><a href="https://soter.example/">Soter</a></body></html>'
        official_html = b'<html><head><meta property="og:title" content="Soter"><meta property="og:site_name" content="Soter"></head><body><p>Jane Doe, Founder</p><a href="mailto:bd@soter.example">BD email</a><a href="https://t.me/soter">Telegram</a><a href="https://x.com/soter">X</a></body></html>'
        def fake_fetch(url, limit=scanner.MAX_PAGE_BYTES):
            if url == "https://news.example/story":
                return url, "text/html", source_html
            if url == "https://soter.example/":
                return url, "text/html", official_html
            raise OSError("page not found")
        candidate = {
            "title":"Standard Chartered and SBI back crypto insurer Soter as funding reaches $23.5 million",
            "summary":"A Web3 insurance company raised funding.",
            "source_name":"CoinDesk",
            "evidence_url":"https://news.example/story",
            "buyer_intent_status":"unverified",
        }
        with patch.object(scanner, "safe_fetch", side_effect=fake_fetch):
            result = scanner.enrich_candidate(candidate)
        self.assertEqual(result["project_website"], "https://soter.example/")
        self.assertEqual(result["resolved_evidence_url"], "https://news.example/story")
        self.assertEqual(result["project_name"], "Soter")
        self.assertEqual(result["enrichment_status"], "completed")
        self.assertEqual({c["type"] for c in result["public_contacts"]}, {"person","email","telegram","x"})
        self.assertEqual(result["buyer_intent_status"], "no_explicit_need")

    def test_private_and_local_urls_are_blocked(self):
        with self.assertRaises(ValueError):
            scanner.validate_public_url("http://127.0.0.1/admin")
        with self.assertRaises(ValueError):
            scanner.validate_public_url("file:///etc/passwd")

    def test_irrelevant_vendor_incident_and_generic_directory_posts_are_filtered(self):
        self.assertIsNone(scanner.classify({"title":"Bitcoin price today","summary":"Market is moving."}, "news_signal"))
        self.assertIsNone(scanner.classify({"title":"Web3 marketing packages available","summary":"We offer services for projects."}, "news_signal"))
        self.assertIsNone(scanner.classify({"title":"Gnosis Pay breach exposes crypto wallets","summary":"A security incident."}, "news_signal"))
        self.assertIsNone(scanner.classify({"title":"CRYMBO Funding Rounds, Token Sale Review & Tokenomics Analysis - CryptoRank","summary":"CryptoRank project profile."}, "funding_signal"))

if __name__ == "__main__":
    unittest.main()
