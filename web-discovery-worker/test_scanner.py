import os
import unittest
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

    def test_irrelevant_vendor_incident_and_generic_directory_posts_are_filtered(self):
        self.assertIsNone(scanner.classify({"title":"Bitcoin price today","summary":"Market is moving."}, "news_signal"))
        self.assertIsNone(scanner.classify({"title":"Web3 marketing packages available","summary":"We offer services for projects."}, "news_signal"))
        self.assertIsNone(scanner.classify({"title":"Gnosis Pay breach exposes crypto wallets","summary":"A security incident."}, "news_signal"))
        self.assertIsNone(scanner.classify({"title":"CRYMBO Funding Rounds, Token Sale Review & Tokenomics Analysis - CryptoRank","summary":"CryptoRank project profile."}, "funding_signal"))

if __name__ == "__main__":
    unittest.main()
