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
        tree = ast.parse(WORKER.read_text(encoding="utf-8"))
        classify_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "classify"
        )
        namespace = {
            "COMPILED": cls.patterns,
            "BUYING_CONTEXT": re.compile(
                r"\b(looking for|need|seeking|hiring|searching for|want to hire|any recommendation|recommend a|partner with|agency|service provider)\b",
                re.I,
            ),
            "CRYPTO_CONTEXT": re.compile(
                r"\b(web3|crypto|blockchain|defi|cefi|token|wallet|exchange|launchpad|staking|mining|rwa|gamefi|metaverse|ai agent|trading|forex|telegram|airdrop|dapp|testnet)\b",
                re.I,
            ),
        }
        exec(compile(ast.Module(body=[classify_node], type_ignores=[]), str(WORKER), "exec"), namespace)
        cls.classify = staticmethod(namespace["classify"])
        sender_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "is_human_sender"
        )
        sender_namespace = {}
        exec(compile(ast.Module(body=[sender_node], type_ignores=[]), str(WORKER), "exec"), sender_namespace)
        cls.is_human_sender = staticmethod(sender_namespace["is_human_sender"])

    def assert_signal(self, category, message):
        self.assertTrue(
            any(pattern.search(message) for pattern in self.patterns[category]),
            msg=f"No pattern in {category!r} matched: {message!r}",
        )

    def test_bot_sender_is_excluded(self):
        self.assertFalse(self.is_human_sender(type("Sender", (), {"bot": True})()))

    def test_human_sender_is_kept(self):
        self.assertTrue(self.is_human_sender(type("Sender", (), {"bot": False})()))

    def test_unknown_sender_is_kept_for_manual_review(self):
        self.assertTrue(self.is_human_sender(None))

    def test_classifier_accepts_real_buying_intent(self):
        self.assertIn("Giveaways & Airdrops", self.classify("Need a giveaway campaign for our token launch"))

    def test_classifier_rejects_general_project_description(self):
        self.assertEqual(self.classify("We are building a Web3 wallet for global users"), [])

    def test_classifier_accepts_generic_crypto_agency_request(self):
        self.assertIn("Project Promotion", self.classify("Looking for a marketing agency for our crypto wallet"))

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

    def test_ama_request(self):
        self.assert_signal("AMA Hosting & Engagement", "Need AMA hosting partner")

    def test_pr_request(self):
        self.assert_signal("PR & Media Visibility", "Looking for PR agency")

    def test_airdrop_request(self):
        self.assert_signal("Giveaways & Airdrops", "Need a giveaway campaign")

    def test_content_marketing_request(self):
        self.assert_signal("Content Distribution & Marketing", "Looking for content marketing")

    def test_social_media_request(self):
        self.assert_signal("Social Media Marketing", "Need social media management")

    def test_project_marketing_request(self):
        self.assert_signal("Project Promotion", "Looking for promotion agency")

    def test_video_request(self):
        self.assert_signal("Video & Creative Production", "Need promo video production")

    def test_fundraising_request(self):
        self.assert_signal("Fundraising / Launch Promotion", "Need launch promotion")

    def test_automation_request(self):
        self.assert_signal("AI / Automation Promotion", "Promote our automation tool")

    def test_wallet_user_acquisition(self):
        self.assert_signal("Exchange / Wallet Promotion", "Need wallet users and community")

    def test_metaverse_request(self):
        self.assert_signal("GameFi / Casino Promotion", "Looking for metaverse marketing")

    def test_mining_request(self):
        self.assert_signal("Mining / Staking Promotion", "Looking for mining marketing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
