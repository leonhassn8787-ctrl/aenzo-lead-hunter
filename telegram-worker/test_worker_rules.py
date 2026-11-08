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
        namespace["SELLER_AD_CONTEXT"] = next(
            eval(compile(ast.Expression(body=node.value), str(WORKER), "eval"), {"re": re})
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(target.id == "SELLER_AD_CONTEXT" for target in node.targets if isinstance(target, ast.Name))
        )
        namespace["SELLER_POST_CONTEXT"] = next(
            eval(compile(ast.Expression(body=node.value), str(WORKER), "eval"), {"re": re})
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(target.id == "SELLER_POST_CONTEXT" for target in node.targets if isinstance(target, ast.Name))
        )
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
        sender_namespace = {"User": type("User", (), {})}
        exec(compile(ast.Module(body=[sender_node], type_ignores=[]), str(WORKER), "exec"), sender_namespace)
        cls.is_human_sender = staticmethod(sender_namespace["is_human_sender"])
        cls.telegram_user_type = sender_namespace["User"]
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

    def test_global_search_scans_groups_without_joining(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn("SearchGlobalRequest", source)
        self.assertIn("groups_only=True", source)
        self.assertIn("GLOBAL_GROUP_SEARCH_QUERIES", source)
        self.assertIn('state.setdefault("global_search", {})', source)

    def test_same_author_cross_post_is_deduplicated(self):
        first = self.dedupe("group-a", 100, 42, "Need KOLs for our crypto launch!")
        second = self.dedupe("group-b", 900, 42, "NEED KOLS FOR OUR CRYPTO LAUNCH")
        self.assertEqual(first, second)

    def test_different_authors_are_not_merged(self):
        first = self.dedupe("group-a", 100, 42, "Need KOLs for our crypto launch")
        second = self.dedupe("group-a", 101, 43, "Need KOLs for our crypto launch")
        self.assertNotEqual(first, second)

    def test_same_author_is_not_sent_twice_for_a_different_request(self):
        first = self.dedupe("group-a", 100, 42, "Need KOLs for our crypto launch")
        second = self.dedupe("group-a", 101, 42, "Need website design for our crypto launch")
        self.assertEqual(first, second)

    def test_dedupe_falls_back_to_message_identity_without_author(self):
        self.assertEqual(self.dedupe("group-a", 100), self.dedupe("group-a", 100))
        self.assertNotEqual(self.dedupe("group-a", 100), self.dedupe("group-a", 101))
        self.assertNotEqual(self.dedupe("group-a", 100), self.dedupe("group-b", 100))

    def test_message_batches_are_oldest_first(self):
        options = self.message_scan_kwargs(120, "cutoff")
        self.assertTrue(options["reverse"])
        self.assertEqual(options["min_id"], 120)

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
        sender = self.telegram_user_type()
        sender.bot = True
        self.assertFalse(self.is_human_sender(sender))

    def test_human_sender_is_kept(self):
        sender = self.telegram_user_type()
        sender.bot = False
        self.assertTrue(self.is_human_sender(sender))

    def test_anonymous_group_or_channel_sender_is_excluded(self):
        anonymous = type("Chat", (), {"bot": False})()
        self.assertFalse(self.is_human_sender(anonymous))

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

    def test_generic_user_acquisition_without_digital_project_context_is_rejected(self):
        for message in [
            "Looking for users",
            "Need more audience",
            "Searching for signups",
            "We need more traction",
        ]:
            with self.subTest(message=message):
                self.assertEqual(self.classify(message), [])

    def test_indirect_growth_request_with_digital_project_context_is_accepted(self):
        self.assertIn("Project Promotion", self.classify("Looking for more users for our new SaaS app"))
        self.assertIn("Project Promotion", self.classify("We need more signups for our Web3 platform"))
        self.assertIn("Project Promotion", self.classify("Trying to increase visibility for our digital product"))

    def test_developer_recruitment_is_not_blocked_as_technical_only(self):
        self.assertIn("Recruitment", self.classify("We are looking for a developer for our Web3 wallet project"))
        self.assertIn("Recruitment", self.classify("Hiring a community manager and moderators for our crypto project"))
        self.assertEqual(self.classify("Looking for a Solidity smart contract auditor"), [])

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

    def test_ad_account_and_campaign_support_vendors_are_rejected(self):
        examples = [
            "Need help with ad accounts, campaign approvals, or performance? Google, Meta & TikTok Ads. Contact @Maxi_solution",
            "Looking for reliable advertising solutions for your campaigns? Meta Ads, Google Ads, landing pages and account support. DM to discuss availability.",
            "Premium Advertising Accounts. We only deal with verified accounts for rental and purchase across Google, Meta and TikTok.",
            "Looking to buy advertising accounts? Purchase options, rental solutions and account setup support for agencies and media buyers.",
            "Advertising account solutions available. Serious buyers only. Inbox me to discuss your requirements and pricing.",
        ]
        for message in examples:
            with self.subTest(message=message):
                self.assertEqual(self.classify(message), [])

    def test_lead_database_and_campaign_data_vendors_are_rejected(self):
        examples = [
            "Fresh Crypto, investors, business and depositor leads just landed. We give you access to our private database tool with custom filters.",
            "Looking for high-converting, niche-targeted leads? Available lead categories include crypto, forex and Binance. Order today.",
            "Targeted business data and campaign-ready leads available by country and industry. Contact us for pricing.",
        ]
        for message in examples:
            with self.subTest(message=message):
                self.assertEqual(self.classify(message), [])

    def test_real_web3_buyers_are_not_blocked_by_vendor_filter(self):
        self.assertIn(
            "KOL & Influencer Marketing",
            self.classify("We are looking for KOLs for our Web3 launch and have an approved campaign budget."),
        )
        self.assertIn(
            "Project Promotion",
            self.classify("Our crypto wallet needs a marketing agency for its upcoming launch."),
        )

    def test_genuine_buyer_budget_language_is_not_mistaken_for_a_vendor(self):
        buyer_messages = [
            "Our Web3 project is looking for KOLs for launch. We have an approved budget.",
            "We need an influencer marketing agency for our wallet. We have budget for a paid campaign.",
            "Looking for a PR partner for our token launch; we have funds approved and are ready to hire.",
        ]
        for message in buyer_messages:
            with self.subTest(message=message):
                self.assertTrue(self.classify(message))

    def test_kol_network_and_project_promotion_vendors_are_rejected(self):
        examples = [
            "Need KOLs? We have a large influencer network and can promote your token.",
            "We can promote your project through our Telegram community. DM for paid promotion.",
            "Looking for new projects to promote with our KOL network.",
            "Need KOL marketing? I can provide influencer campaigns and packages.",
        ]
        for message in examples:
            with self.subTest(message=message):
                self.assertEqual(self.classify(message), [])

    def test_busy_public_search_windows_are_recursively_split(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn("await fetch_window(window_min, midpoint, depth + 1)", source)
        self.assertIn("await fetch_window(midpoint, window_max, depth + 1)", source)
        self.assertIn("window_max - window_min <= 1", source)

    def test_public_search_deduplicates_messages_and_counts_vendor_ads(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn("run_seen_public_messages = set()", source)
        self.assertIn("if public_message_key in run_seen_public_messages", source)
        self.assertIn("seller_posts += 1", source)

    def test_incomplete_public_search_still_processes_partial_messages_without_advancing_cursor(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("if not complete:", source.index("async def run"))
        end = source.index("query_failed = not complete", start)
        incomplete_branch = source[start:end]
        self.assertIn("processing available messages", incomplete_branch)
        self.assertNotIn("continue", incomplete_branch)
        self.assertIn("if query_failed:", source[end:])

    def test_global_search_cursor_overlaps_boundary_to_avoid_missed_seconds(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn("previous_scan - 2 if previous_scan", source)

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

    def test_similar_or_identical_text_from_different_authors_stays_separate(self):
        first = self.dedupe("group-a", 1, 111, "A" * 120)
        second = self.dedupe("group-b", 2, 222, "A" * 120)
        self.assertNotEqual(first, second)

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

    def test_realistic_service_seller_ads_are_rejected(self):
        seller_posts = [
            "Professional communication and telecom services. Looking for reliable solutions? Our services include Bulk SMS, VoIP and SIP trunking.",
            "Crypto Advertising & Traffic Optimization Solutions. Looking to improve your campaigns? I specialize in traffic acquisition and conversion-focused campaigns.",
            "Looking for a few users? I have paid testing options available.",
            "Need advertising accounts or campaign support? We've got you covered. DM for pricing.",
            "DATA WORLD — FRESH DATA & LEADS AVAILABLE. Looking for the right audience? Get targeted business data and campaign-ready leads.",
            "Looking for reliable advertising solutions? Available for one-time orders and long-term business partnerships.",
        ]
        for post in seller_posts:
            with self.subTest(post=post):
                self.assertEqual(self.classify(post), [])

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

    def test_vendor_account_inventory_is_rejected(self):
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


    def test_advertising_infrastructure_and_account_vendors_are_rejected(self):
        posts = [
            "HAVING TROUBLE RUNNING YOUR CAMPAIGNS? From account restrictions and rejected ads "
            "to tracking, conversion setup, landing pages, and campaign configuration — "
            "we help advertisers get their advertising infrastructure properly set up and ready to launch. "
            "AVAILABLE SUPPORT Ad account setup & configuration; Campaign creation & optimization; "
            "Tracking & conversion setup; Landing-page configuration; Technical advertising support. "
            "For serious advertising projects: @adtech_cloaker",
            "NEED WHATSAPP + ADS SOLUTIONS THAT CAN SCALE WITH YOU? "
            "WhatsApp API — 10K • 100K • Unlimited; WhatsApp Messaging & Marketing Tools; "
            "Meta & Google Ads Solutions; BM5 • BM10 • BM25 • BM50 • BM100 • BM250 • BM500 • BM1K; "
            "TikTok Ads Accounts; Blue Tick Solutions; Fresh Facebook Accounts & Pages. "
            "From 5 to 1,000 ad accounts. Fast Setup • Support • Scalable Solutions. "
            "Ready to scale? @MetaBMExpert",
        ]
        for post in posts:
            with self.subTest(post=post):
                self.assertEqual(self.classify(post), [])

    def test_buyer_request_for_a_real_marketing_campaign_still_passes_vendor_filter(self):
        self.assertIn(
            "Project Promotion",
            self.classify("Our crypto project needs a paid marketing campaign before launch. "
                           "We are looking for an agency to manage it."),
        )

class GroupScanningOptimizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(WORKER.read_text(encoding="utf-8"))
        wanted = {
            "group_priority", "should_pause_group", "message_scan_kwargs",
            "reset_group_quality_metrics",
        }
        nodes = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in wanted
        ]
        namespace = {"CLASSIFIER_RULES_VERSION": 3}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(WORKER), "exec"), namespace)
        cls.group_priority = staticmethod(namespace["group_priority"])
        cls.should_pause_group = staticmethod(namespace["should_pause_group"])
        cls.message_scan_kwargs = staticmethod(namespace["message_scan_kwargs"])
        cls.reset_group_quality_metrics = staticmethod(namespace["reset_group_quality_metrics"])

    def test_only_unseen_messages_are_requested_after_initial_scan(self):
        from datetime import datetime, timezone
        cutoff = datetime.now(timezone.utc)
        kwargs = self.message_scan_kwargs(1234, cutoff)
        self.assertEqual(kwargs["min_id"], 1234)
        self.assertTrue(kwargs["reverse"])
        self.assertNotIn("offset_date", kwargs)

    def test_initial_scan_is_bounded_to_recent_history(self):
        from datetime import datetime, timezone
        cutoff = datetime.now(timezone.utc)
        kwargs = self.message_scan_kwargs(0, cutoff)
        self.assertEqual(kwargs["offset_date"], cutoff)
        self.assertNotIn("limit", kwargs)

    def test_groups_with_real_leads_receive_higher_priority(self):
        good = {"qualified_leads": 2, "buyer_signals": 5, "seller_ads": 0}
        noisy = {"qualified_leads": 0, "buyer_signals": 0, "seller_ads": 20}
        self.assertGreater(self.group_priority(good), self.group_priority(noisy))

    def test_only_vendor_heavy_groups_without_leads_are_snoozed(self):
        self.assertTrue(self.should_pause_group({
            "messages_seen": 200, "seller_ads": 80, "qualified_leads": 0
        }))
        self.assertFalse(self.should_pause_group({
            "messages_seen": 200, "seller_ads": 80, "qualified_leads": 1
        }))
        self.assertFalse(self.should_pause_group({
            "messages_seen": 199, "seller_ads": 100, "qualified_leads": 0
        }))

    def test_classifier_upgrade_resets_stale_group_quality_but_keeps_cursor(self):
        state = {
            "version": 2,
            "groups": {
                "group-1": {
                    "last_seen_id": 9876,
                    "messages_seen": 500,
                    "seller_ads": 180,
                    "buyer_signals": 15,
                    "qualified_leads": 7,
                    "paused_until": "2026-11-15T00:00:00+00:00",
                }
            },
        }
        self.assertTrue(self.reset_group_quality_metrics(state))
        meta = state["groups"]["group-1"]
        self.assertEqual(meta["last_seen_id"], 9876)
        self.assertEqual(meta["messages_seen"], 0)
        self.assertEqual(meta["seller_ads"], 0)
        self.assertEqual(meta["buyer_signals"], 0)
        self.assertEqual(meta["qualified_leads"], 0)
        self.assertIsNone(meta["paused_until"])
        self.assertEqual(state["classifier_rules_version"], 3)
        self.assertFalse(self.reset_group_quality_metrics(state))

    def test_rejected_leads_are_excluded_from_telegram_notification_queue(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("async def notify_pending_leads")
        end = source.index("async def send_scan_report", start)
        notification_code = source[start:end]
        self.assertIn("'status': 'eq.new'", notification_code)
        self.assertIn("'telegram_notified_at': 'is.null'", notification_code)
        self.assertIn("'owner_id': 'eq.' + SUPABASE_OWNER_ID", notification_code)
        self.assertIn("'limit': '25'", notification_code)

    def test_worker_numeric_environment_settings_are_bounded(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn('bounded_int_env("POLL_SECONDS", 600, 60, 86400)', source)
        self.assertIn('bounded_int_env("LOOKBACK_DAYS", 30, 1, 3650)', source)
        self.assertIn('bounded_int_env("GLOBAL_SEARCH_MAX_PAGES", 3, 1, 20)', source)
        self.assertIn('bounded_int_env("SCAN_BUDGET_SECONDS", 1320, 60, 1500)', source)

    def test_scan_report_separates_joined_groups_from_public_search_signals(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn("Joined groups available:", source)
        self.assertIn("Joined groups checked:", source)
        self.assertIn("Public groups with qualified buyer signals:", source)
        self.assertNotIn('f"Groups scanned:', source)



class JoinedGroupCheckpointTests(unittest.TestCase):
    def test_checkpoint_counts_all_messages_and_saves_before_current_message(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("async for msg in client.iter_messages(entity")
        end = source.index("if not group_write_failed:", start)
        loop_start = source[start:end]
        checkpoint = loop_start.index('if messages_since_checkpoint >= 25 and not group_write_failed:')
        save_cursor = loop_start.index('meta["last_seen_id"] = max(last_seen, newest_seen)')
        increment = loop_start.index("messages_since_checkpoint += 1")
        update_current = loop_start.index("newest_seen = max(newest_seen, int(msg.id))")
        self.assertLess(checkpoint, save_cursor)
        self.assertLess(save_cursor, update_current)
        self.assertLess(update_current, increment)
        self.assertIn("if getattr(msg, \"out\", False):", loop_start)


class GlobalSearchPaginationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(WORKER.read_text(encoding="utf-8"))
        node = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "fetch_global_group_messages"
        )

        class Request:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        class EmptyPeer:
            pass

        class EmptyFilter:
            pass

        class QuietLog:
            def info(self, *args, **kwargs):
                pass

            def warning(self, *args, **kwargs):
                pass

            def exception(self, *args, **kwargs):
                pass

        namespace = {
            "SearchGlobalRequest": Request,
            "InputPeerEmpty": EmptyPeer,
            "InputMessagesFilterEmpty": EmptyFilter,
            "GLOBAL_SEARCH_MAX_PAGES": 3,
            "log": QuietLog(),
        }
        exec(
            compile(ast.Module(body=[node], type_ignores=[]), str(WORKER), "exec"),
            namespace,
        )
        cls.fetch = staticmethod(namespace["fetch_global_group_messages"])

    def test_saturated_public_search_recursively_splits_and_merges(self):
        import asyncio
        from datetime import datetime, timezone
        from types import SimpleNamespace

        class Message:
            def __init__(self, peer_id, message_id, timestamp):
                self.peer_id = peer_id
                self.id = message_id
                self.date = datetime.fromtimestamp(timestamp, timezone.utc)

        class Client:
            def __init__(self):
                self.calls = []

            async def __call__(self, request):
                self.calls.append((request.min_date, request.max_date, request.offset_rate))
                if request.max_date - request.min_date > 10:
                    page = int(request.offset_rate)
                    messages = [
                        Message("wide-window", page * 100 + i + 1, request.min_date + 1)
                        for i in range(100)
                    ]
                    return SimpleNamespace(messages=messages, next_rate=page + 1)
                message = Message(
                    f"peer-{request.min_date}",
                    request.min_date + 10000,
                    request.min_date,
                )
                return SimpleNamespace(messages=[message], next_rate=None)

            async def get_input_entity(self, peer_id):
                return peer_id

        client = Client()
        messages, complete = asyncio.run(
            self.fetch(client, "looking for KOL", 0, 100)
        )
        identities = {
            (repr(message.peer_id), message.id)
            for message in messages
        }
        self.assertTrue(complete)
        self.assertGreater(len(client.calls), 3)
        self.assertGreater(len(messages), 1)
        self.assertEqual(len(messages), len(identities))

    def test_one_second_overflow_is_reported_incomplete_without_infinite_recursion(self):
        import asyncio
        from datetime import datetime, timezone
        from types import SimpleNamespace

        class Message:
            def __init__(self, message_id):
                self.peer_id = "same-peer"
                self.id = message_id
                self.date = datetime.fromtimestamp(1, timezone.utc)

        class Client:
            def __init__(self):
                self.calls = 0

            async def __call__(self, request):
                self.calls += 1
                page = int(request.offset_rate)
                return SimpleNamespace(
                    messages=[Message(page * 100 + i) for i in range(100)],
                    next_rate=page + 1,
                )

            async def get_input_entity(self, peer_id):
                return peer_id

        client = Client()
        messages, complete = asyncio.run(
            self.fetch(client, "looking for KOL", 1, 2)
        )
        self.assertFalse(complete)
        self.assertEqual(client.calls, 3)
        self.assertEqual(len(messages), 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)
