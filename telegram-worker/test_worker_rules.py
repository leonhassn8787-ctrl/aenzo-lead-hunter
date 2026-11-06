import ast
import re
import unittest
from pathlib import Path

WORKER = Path(__file__).with_name("worker.py")


def load_signals():
    tree = ast.parse(WORKER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SIGNALS":
                    return ast.literal_eval(node.value)
    raise AssertionError("SIGNALS dictionary was not found")


class LeadSignalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns = {
            name: [re.compile(pattern, re.I) for pattern in patterns]
            for name, patterns in load_signals().items()
        }

    def assert_signal(self, category, message):
        self.assertTrue(
            any(pattern.search(message) for pattern in self.patterns[category]),
            msg=f"No pattern in {category!r} matched: {message!r}",
        )

    def test_kol_request(self):
        self.assert_signal("KOL & Influencer Marketing", "We are looking for KOLs for our Web3 launch")

    def test_community_request(self):
        self.assert_signal("Community Promotion", "Need Telegram community growth promotion")

    def test_ai_automation_request(self):
        self.assert_signal("AI / Automation Promotion", "Need AI agent promotion and users")

    def test_exchange_wallet_request(self):
        self.assert_signal("Exchange / Wallet Promotion", "Looking for wallet marketing and growth")

    def test_rwa_trading_request(self):
        self.assert_signal("RWA / Trading Promotion", "Looking for RWA marketing and promotion")

    def test_gamefi_casino_request(self):
        self.assert_signal("GameFi / Casino Promotion", "Need GameFi community promotion")

    def test_mining_staking_request(self):
        self.assert_signal("Mining / Staking Promotion", "Looking for staking marketing")

    def test_website_request(self):
        self.assert_signal("Website Design & Development", "We need website design and development")

    def test_recruitment_request(self):
        self.assert_signal("Recruitment", "Hiring community manager for our crypto project")

    def test_verdict_testing_request(self):
        self.assert_signal("Project Review / VERDICT", "Looking for beta testers for our app")


if __name__ == "__main__":
    unittest.main(verbosity=2)
