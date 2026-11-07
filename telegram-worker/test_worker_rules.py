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
            "re": re,
            "COMPILED": cls.patterns,
            "BUYING_CONTEXT": re.compile(
                r"\b(struggling to (get|attract|reach|grow|increase)|having trouble (getting|attracting|reaching|growing)|not getting (enough|many) (users|registrations|signups|members|engagement|traction)|could use more|how can we (get|attract|reach|grow|increase)|what.s the best way to (get|attract|reach|grow|increase)|looking for|looking to work with|looking to grow|looking to increase|looking to boost|in search of|trying to find|trying to grow|trying to increase|want to grow|want to increase|want to boost|need|needs|need more|seeking|hiring|searching for|want to hire|want someone to|need someone to|need a team|need a hand|any recommendation|recommend a|recommendations for|can anyone recommend|anyone know|does anyone know|who can help|can anyone help|anyone able to|someone who can|anyone experienced in|could use|need help with|help us|partner with|any agency|suggest a)\b",
                re.I,
            ),
            "CRYPTO_CONTEXT": re.compile(
                r"\b(web3|crypto|blockchain|defi|cefi|token|wallet|exchange|launchpad|staking|mining|rwa|gamefi|metaverse|ai agent|trading|forex|telegram|airdrop|dapp|testnet)\b",
                re.I,
            ),
            "NON_BUYER_CONTEXT": next(
                eval(compile(ast.Expression(body=node.value), str(WORKER), "eval"), {"re": re})
                for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "NON_BUYER_CONTEXT" for target in node.targets)
            ),
        }
        exec(compile(ast.Module(body=[classify_node], type_ignores=[]), str(WORKER), "exec"), namespace)
        cls.classify = staticmethod(namespace["classify"])
        priority_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "priority"
        )
        priority_namespace = {"re": re}
        exec(compile(ast.Module(body=[priority_node], type_ignores=[]), str(WORKER), "exec"), priority_namespace)
        cls.priority = staticmethod(priority_namespace["priority"])
        outreach_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "make_outreach"
        )
        outreach_namespace = {}
        exec(compile(ast.Module(body=[outreach_node], type_ignores=[]), str(WORKER), "exec"), outreach_namespace)
        cls.make_outreach = staticmethod(outreach_namespace["make_outreach"])
        contacts_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "extract_public_contacts"
        )
        contacts_namespace = {"re": re}
        exec(compile(ast.Module(body=[contacts_node], type_ignores=[]), str(WORKER), "exec"), contacts_namespace)
        cls.extract_public_contacts = staticmethod(contacts_namespace["extract_public_contacts"])
        sender_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "is_human_sender"
        )
        sender_namespace = {}
        exec(compile(ast.Module(body=[sender_node], type_ignores=[]), str(WORKER), "exec"), sender_namespace)
        cls.is_human_sender = staticmethod(sender_namespace["is_human_sender"])
        url_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "make_message_url"
        )
        url_namespace = {}
        exec(compile(ast.Module(body=[url_node], type_ignores=[]), str(WORKER), "exec"), url_namespace)
        cls.make_message_url = staticmethod(url_namespace["make_message_url"])
        helper_nodes = {
            node.name: node for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        pagination_namespace = {"MAX_MESSAGES_PER_GROUP": 200}
        exec(compile(ast.Module(body=[helper_nodes["message_scan_kwargs"]], type_ignores=[]), str(WORKER), "exec"), pagination_namespace)
        cls.message_scan_kwargs = staticmethod(pagination_namespace["message_scan_kwargs"])
        headers_namespace = {}
        exec(compile(ast.Module(body=[helper_nodes["supabase_headers"]], type_ignores=[]), str(WORKER), "exec"), headers_namespace)
        cls.supabase_headers = staticmethod(headers_namespace["supabase_headers"])
        dedupe_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "dedupe"
        )
        dedupe_namespace = {"hashlib": __import__("hashlib"), "re": re}
        exec(compile(ast.Module(body=[dedupe_node], type_ignores=[]), str(WORKER), "exec"), dedupe_namespace)
        cls.dedupe = staticmethod(dedupe_namespace["dedupe"])

    def test_same_author_cross_post_is_deduplicated(self):
        first = self.dedupe("group-a", 100, 42, "Need KOLs for our crypto launch!")
        second = self.dedupe("group-b", 900, 42, "NEED KOLS FOR OUR CRYPTO LAUNCH")
        self.assertEqual(first, second)

    def test_different_authors_are_not_merged(self):
        first = self.dedupe("group-a", 100, 42, "Need KOLs for our crypto launch")
        second = self.dedupe("group-a", 101, 43, "Need KOLs for our crypto launch")
        self.assertNotEqual(first, second)

    def test_distinct_requests_from_same_author_are_kept(self):
        first = self.dedupe("group-a", 100, 42, "Need KOLs for our crypto launch")
        second = self.dedupe("group-a", 101, 42, "Need website design for our crypto launch")
        self.assertNotEqual(first, second)

    def test_dedupe_falls_back_to_message_identity_without_author(self):
        self.assertEqual(self.dedupe("group-a", 100), self.dedupe("group-a", 100))

    def test_message_batches_are_oldest_first(self):
        options = self.message_scan_kwargs(120, "cutoff")
        self.assertTrue(options["reverse"])
        self.assertEqual(options["min_id"], 120)
        self.assertEqual(options["limit"], 200)

    def test_first_message_batch_is_limited_to_recent_history(self):
        options = self.message_scan_kwargs(0, "cutoff")
        self.assertEqual(options["offset_date"], "cutoff")

    def test_incremental_batch_keeps_backlog_even_after_lookback(self):
        options = self.message_scan_kwargs(120, "cutoff")
        self.assertNotIn("offset_date", options)

    def test_supabase_secret_is_not_sent_as_bearer_jwt(self):
        headers = self.supabase_headers("sb_secret_test")
        self.assertEqual(headers["apikey"], "sb_secret_test")
        self.assertNotIn("Authorization", headers)

    def assert_signal(self, category, message):
        self.assertTrue(
            any(pattern.search(message) for pattern in self.patterns[category]),
            msg=f"No pattern in {category!r} matched: {message!r}",
        )

    def test_public_group_message_link(self):
        entity = type("Entity", (), {"username": "publicgroup", "megagroup": True, "id": 123})()
        self.assertEqual(self.make_message_url(entity, 45), "https://t.me/publicgroup/45")

    def test_private_supergroup_message_link(self):
        entity = type("Entity", (), {"username": None, "megagroup": True, "id": 123})()
        self.assertEqual(self.make_message_url(entity, 45), "https://t.me/c/123/45")

    def test_private_basic_group_has_no_fabricated_link(self):
        entity = type("Entity", (), {"username": None, "megagroup": False, "id": 123})()
        self.assertIsNone(self.make_message_url(entity, 45))

    def test_bot_sender_is_excluded(self):
        self.assertFalse(self.is_human_sender(type("Sender", (), {"bot": True})()))

    def test_human_sender_is_kept(self):
        self.assertTrue(self.is_human_sender(type("Sender", (), {"bot": False})()))

    def test_public_contacts_are_extracted_without_guessing(self):
        found = self.extract_public_contacts(
            "Contact us at team@example.org, X: https://x.com/aenzo_team, "
            "WhatsApp: https://wa.me/966500000000, site https://aenzo.example",
            "founder_aenzo",
        )
        kinds = {item["type"] for item in found}
        self.assertEqual(kinds, {"telegram", "email", "x", "whatsapp", "website"})
        self.assertIn("https://t.me/founder_aenzo", [item.get("url") for item in found])
        self.assertIn("team@example.org", [item["value"] for item in found])

    def test_private_or_unmentioned_contact_is_not_invented(self):
        self.assertEqual(self.extract_public_contacts("We are launching a Web3 project."), [])

    def test_unknown_sender_is_excluded(self):
        self.assertFalse(self.is_human_sender(None))

    def test_job_seeker_is_not_a_client_lead(self):
        self.assertEqual(self.classify("Looking for a job in a Web3 project"), [])

    def test_free_airdrop_hunter_is_not_a_client_lead(self):
        self.assertEqual(self.classify("Anyone know how to claim a free airdrop?"), [])

    def test_price_prediction_request_is_not_a_client_lead(self):
        self.assertEqual(self.classify("Looking for token price prediction"), [])

    def test_wallet_support_issue_is_not_a_client_lead(self):
        self.assertEqual(self.classify("My wallet is not working, need help"), [])

    def test_real_service_request_still_matches(self):
        self.assertIn("KOL & Influencer Marketing", self.classify("Looking for KOLs for our crypto launch"))

    def test_first_person_buyer_request_is_not_excluded(self):
        self.assertIn("KOL & Influencer Marketing", self.classify("We are looking for KOLs for our crypto launch"))

    def test_outreach_is_specific_to_detected_service(self):
        english, bengali = self.make_outreach(["Website Design & Development"])
        self.assertIn("website design and development", english)
        self.assertIn("ওয়েবসাইট ডিজাইন ও ডেভেলপমেন্ট", bengali)

    def test_outreach_does_not_invent_project_identity(self):
        english, bengali = self.make_outreach(["KOL & Influencer Marketing"])
        self.assertNotIn("Potential project", english)
        self.assertNotIn("project —", bengali)

    def test_outreach_handles_empty_service_list(self):
        english, bengali = self.make_outreach([])
        self.assertIn("Web3 marketing", english)
        self.assertTrue(bengali)

    def test_priority_rewards_explicit_budget_and_urgency(self):
        low = self.priority("Looking for KOLs for our crypto project", ["KOL & Influencer Marketing"])
        high = self.priority(
            "Need KOLs urgently, budget approved, paid campaign, DM me",
            ["KOL & Influencer Marketing"],
        )
        self.assertGreater(high, low)

    def test_priority_is_capped(self):
        score = self.priority(
            "Need urgent paid budget ASAP DM me send proposal",
            ["A", "B", "C", "D", "E", "F"],
        )
        self.assertLessEqual(score, 95)

    def test_priority_does_not_treat_multiple_categories_as_proof(self):
        one = self.priority("Need marketing", ["A"])
        many = self.priority("Need marketing", ["A", "B", "C", "D"])
        self.assertLessEqual(many - one, 10)


    def test_agency_self_promotion_is_not_a_client_lead(self):
        self.assertEqual(self.classify("We are a Web3 marketing agency offering KOL services"), [])

    def test_service_provider_description_is_not_a_client_lead(self):
        self.assertEqual(self.classify("Our crypto agency provides community growth services"), [])

    def test_first_person_agency_advertisement_is_not_a_client_lead(self):
        self.assertEqual(self.classify("We provide KOL marketing and Telegram promotion for Web3 projects"), [])

    def test_agency_offer_post_is_not_a_client_lead(self):
        self.assertEqual(self.classify("Our company offers crypto PR and influencer campaigns"), [])

    def test_classifier_accepts_real_buying_intent(self):
        self.assertIn("Giveaways & Airdrops", self.classify("Need a giveaway campaign for our token launch"))

    def test_classifier_rejects_general_project_description(self):
        self.assertEqual(self.classify("We are building a Web3 wallet for global users"), [])

    def test_classifier_accepts_generic_crypto_agency_request(self):
        self.assertIn("Project Promotion", self.classify("Looking for a marketing agency for our crypto wallet"))

    def test_classifier_accepts_searching_for_and_want_to_hire_intent(self):
        self.assertIn("KOL & Influencer Marketing", self.classify("Searching for KOLs for our Web3 launch"))
        self.assertIn("KOL & Influencer Marketing", self.classify("We want to hire KOLs for our crypto launch"))
        self.assertIn("KOL & Influencer Marketing", self.classify("Need help with our KOL campaign for the token launch"))

    def test_classifier_accepts_partner_with_intent(self):
        self.assertIn("Project Promotion", self.classify("We want to partner with a Web3 marketing agency"))

    def test_classifier_understands_natural_group_writing(self):
        self.assertIn("KOL & Influencer Marketing", self.classify("Anyone know a good KOL team for our token launch?"))
        self.assertIn("Community Promotion", self.classify("Can someone help us grow our Telegram community?"))
        self.assertIn("Website Design & Development", self.classify("We need someone to build our website for the crypto project"))
        self.assertIn("Project Promotion", self.classify("Does anyone know a marketing agency for our Web3 launch?"))

    def test_technical_token_launch_request_is_not_a_marketing_lead(self):
        self.assertEqual(
            self.classify(
                "I’m looking for reliable specialists to help with a Token-2022 transfer hook launch and launchpad recommendations."
            ),
            [],
        )

    def test_usdt_arbitrage_and_payment_ads_are_not_client_leads(self):
        self.assertEqual(
            self.classify("We buy USDT and seek long-term arbitrage partners."),
            [],
        )
        self.assertEqual(
            self.classify("Need customers for USDT exchange and cash deposits."),
            [],
        )

    def test_explicit_aenzo_service_request_is_kept(self):
        self.assertIn(
            "KOL & Influencer Marketing",
            self.classify("Our Web3 project is looking for KOLs for a paid launch campaign. DM me for the budget."),
        )

    def test_growth_problem_requires_marketing_context(self):
        self.assertIn(
            "Project Promotion",
            self.classify("Our Web3 project is struggling to attract users before launch."),
        )
        self.assertEqual(
            self.classify("Anyone know specialists for a Solana token transfer hook?"),
            [],
        )

    def test_classifier_does_not_promote_vague_support_request(self):
        self.assertEqual(self.classify("Anyone know how to fix my crypto wallet?"), [])

    def test_service_intent_examples_are_not_just_exact_keyword_phrases(self):
        self.assertIn("Community Promotion", self.classify("Our Telegram group is quiet and we want to attract more real users. Can anyone help?"))
        self.assertIn("Project Promotion", self.classify("We are preparing a Web3 launch and could use a marketing partner."))
        self.assertIn("Project Promotion", self.classify("We want to grow our Web3 user base before launch. Anyone able to help?"))
        self.assertIn("Project Promotion", self.classify("Trying to increase visibility for our crypto project before launch."))
        self.assertIn("Project Promotion", self.classify("We need more traction for our Web3 launch. Can anyone help?"))
        self.assertIn("Project Promotion", self.classify("Looking for someone who can help us grow our Web3 project audience."))

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
        self.assert_signal("AI / Automation Promotion", "Looking for promotion for our automation tool")

    def test_wallet_user_acquisition(self):
        self.assert_signal("Exchange / Wallet Promotion", "Need wallet users and community")

    def test_metaverse_request(self):
        self.assert_signal("GameFi / Casino Promotion", "Looking for metaverse marketing")

    def test_mining_request(self):
        self.assert_signal("Mining / Staking Promotion", "Looking for mining marketing")


    def test_classifier_recognizes_indirect_growth_pain(self):
        self.assertIn("Project Promotion", self.classify(
            "Our Web3 project is struggling to attract users before launch."
        ))
        self.assertIn("Project Promotion", self.classify(
            "We are not getting enough users for our crypto wallet."
        ))
        self.assertIn("Project Promotion", self.classify(
            "What's the best way to increase visibility for our blockchain launch?"
        ))

    def test_lead_seller_ad_is_not_a_client_lead(self):
        self.assertEqual(
            self.classify(
                "Looking for High-Converting, Niche-Targeted Leads? "
                "AVAILABLE LEAD CATEGORIES: Crypto Leads, Binance Leads, Forex Leads. "
                "Order Today & Get Premium Leads."
            ),
            [],
        )

    def test_pinksale_tokenomics_support_is_not_a_marketing_client_lead(self):
        self.assertEqual(
            self.classify(
                "Please see this to learn about the available tokens on PinkSale. "
                "The marketing tax goes to the developer. For further assistance, "
                "seek assistance with our recommended developers."
            ),
            [],
        )

    def test_message_body_telegram_handles_are_extracted(self):
        found = self.extract_public_contacts("DM @NomissianHUB for details")
        self.assertIn(
            ("@NomissianHUB", "https://t.me/NomissianHUB"),
            [(item["value"], item.get("url")) for item in found],
        )

    def test_long_identical_advertisements_dedupe_across_authors(self):
        first = self.dedupe("group-a", 1, 111, "A" * 120)
        second = self.dedupe("group-b", 2, 222, "A" * 120)
        self.assertEqual(first, second)

    def test_usdt_fund_and_payment_ads_are_rejected(self):
        spam = [
            "We buy USDT across the entire network. Profit through USDT arbitrage.",
            "Needs a large number of Indian customers. Large daily demand for USDT. Hacker Fund, Cash Deposits, Equity Funds, UPI/IMPS.",
            "Cash App Transfer, PayPal Transfer, cloned cards and bank drops available.",
        ]
        for message in spam:
            with self.subTest(message=message):
                self.assertEqual(self.classify(message), [])

    def test_pinksale_promotion_and_token_support_posts_are_rejected(self):
        posts = [
            "No mate you need a PinkSale presale to be able to promote here.",
            "Please see this to learn about available tokens on PinkSale. The marketing tax goes to the developer. Seek assistance with recommended developers.",
            "Welcome to Solama as they partner with PinkSale for their Fairlaunch. Recognized with KYC, Audit and Doxx badge.",
        ]
        for message in posts:
            with self.subTest(message=message):
                self.assertEqual(self.classify(message), [])

    def test_web3_marketing_service_sellers_are_not_client_leads(self):
        provider_posts = [
            "We offer KOL and influencer marketing services for Web3 projects. DM us for rates.",
            "Our agency provides PR, AMA hosting, Telegram community management and paid promotions.",
            "We are a crypto growth agency. Our packages include shilling, influencer campaigns and media coverage.",
            "Promote your token with our large Telegram community and influencer network. Contact us for pricing.",
            "Available for paid promotions, AMA hosting and community growth campaigns.",
            "KOL services available. Message me to get packages and collaboration details.",
            "We help Web3 projects grow. We provide marketing, PR and community services.",
        ]
        for message in provider_posts:
            with self.subTest(message=message):
                self.assertEqual(self.classify(message), [])

    def test_client_buying_request_is_not_blocked_as_a_provider(self):
        self.assertIn(
            "KOL & Influencer Marketing",
            self.classify("Our crypto project is looking to hire an external KOL agency for our token launch."),
        )
        self.assertIn(
            "AMA Hosting & Engagement",
            self.classify("We need AMA hosting for our Web3 project and help managing our Telegram community."),
        )

    def test_real_explicit_marketing_request_survives_new_spam_filters(self):
        self.assertIn(
            "KOL & Influencer Marketing",
            self.classify("Our Web3 project is looking for KOLs for a paid launch campaign. Please DM with your rates."),
        )
        self.assertIn(
            "Exchange / Wallet Promotion",
            self.classify("We are looking for a marketing agency to promote our crypto wallet before launch."),
        )

    def test_meta_tiktok_account_rental_ad_is_not_a_client_lead(self):
        self.assertEqual(
            self.classify(
                "Still looking for a reliable Meta or TikTok advertising account for your next campaign? "
                "I have rental + purchase options available. For legitimate businesses, agencies & media buyers. "
                "DM me your platform + niche and let's check availability."
            ),
            [],
        )

    def test_vendor_inventory_and_rental_posts_are_rejected(self):
        posts = [
            "Meta Ads accounts available for rent. DM me for availability.",
            "I have TikTok advertising account rental and purchase options available.",
            "Facebook ad accounts for sale. Message me your niche.",
        ]
        for message in posts:
            with self.subTest(message=message):
                self.assertEqual(self.classify(message), [])

    def test_real_project_marketing_buyer_request_still_passes(self):
        self.assertIn(
            "Project Promotion",
            self.classify("Our Web3 project is looking for a marketing agency for our upcoming launch."),
        )

    def test_classifier_does_not_promote_unrelated_indirect_complaints(self):
        self.assertEqual(self.classify(
            "Our local cafe is struggling to attract customers."
        ), [])
        self.assertEqual(self.classify(
            "I'm not getting enough members for my gaming chat."
        ), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
