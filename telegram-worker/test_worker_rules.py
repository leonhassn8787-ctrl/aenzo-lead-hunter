# Regression tests for joined-group scan resume and lead-quality gates.
import ast
import asyncio
import hashlib
import logging
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
            "CRYPTO_CONTEXT": next(
                eval(compile(ast.Expression(body=node.value), str(WORKER), "eval"), {"re": re})
                for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "CRYPTO_CONTEXT" for target in node.targets)
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
        for name in (
            "SELLER_PITCH_CONTEXT", "RECRUITMENT_BUYER_CONTEXT", "KOL_PROJECT_CONTEXT",
            "INDIVIDUAL_CREATIVE_ROLE_CONTEXT", "CAPITAL_RAISE_CONTEXT",
            "DIRECT_SERVICE_BUY_REQUEST_CONTEXT",
        ):
            namespace[name] = next(
                eval(compile(ast.Expression(body=node.value), str(WORKER), "eval"), {"re": re})
                for node in tree.body
                if isinstance(node, ast.Assign)
                and any(target.id == name for target in node.targets if isinstance(target, ast.Name))
            )
        verify_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "verify_buyer_evidence"
        )
        exec(compile(ast.Module(body=[verify_node], type_ignores=[]), str(WORKER), "exec"), namespace)
        cls.verify_buyer_evidence = staticmethod(namespace["verify_buyer_evidence"])
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
        pagination_namespace = {}
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

    def test_post_scan_audit_runs_before_new_lead_notifications(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn("async def audit_current_scan_leads(client_http, scan_run_id)", source)
        self.assertIn("post_scan_audit: buyer_intent_uncertain_manual_review_required", source)
        self.assertIn("ambiguous or incomplete evidence", source)
        self.assertIn("def verify_buyer_evidence(text):", source)
        self.assertIn("post_scan_audit: buyer_intent_verified", source)
        self.assertIn("post_scan_audit: service_label_repaired", source)
        self.assertNotIn("verify_buyer_evidence(evidence) or bool(classify(evidence))", source)
        self.assertIn("missing_post_scan_buyer_audit", source)
        self.assertIn("source_evidence_does_not_prove_buyer_intent", source)
        self.assertIn("post_scan_verified", source)
        audit_start = source.index("async def audit_current_scan_leads")
        audit_end = source.index("\n\ndef format_telegram_lead", audit_start)
        audit_code = source[audit_start:audit_end]
        self.assertNotIn('"telegram_notified_at": "is.null"', audit_code)
        self.assertIn('"source_scan_run_id": "eq." + str(scan_run_id)', audit_code)
        self.assertIn('"order": "created_at.asc,id.asc"', audit_code)
        self.assertNotIn("for human review to protect buyers", source)
        self.assertNotIn("await notify_saved_lead(", source)
        self.assertIn("await notify_pending_leads(http)", source)
        self.assertIn("audit_result = await audit_current_scan_leads(http, scan_run_id)", source)
        self.assertLess(source.index("audit_result = await audit_current_scan_leads"), source.index("await notify_pending_leads(http)", source.index("audit_result = await audit_current_scan_leads")))
        self.assertIn("pending-lead notifications withheld for safety", source)
        self.assertIn('"offset": str(offset)', audit_code)
        self.assertIn("pending.extend(page)", audit_code)
        self.assertLess(audit_code.index("pending.extend(page)"), audit_code.index("for lead in pending"))
    def test_evidence_verifier_keeps_proven_project_buyers(self):
        posts = [
            "Our blockchain project is looking for a marketing agency for launch promotion.",
            "We need paid KOL marketing for our crypto wallet project.",
            "We are seeking beta testers for our Web3 wallet and product feedback.",
            "Our Web3 startup is looking for a growth agency to increase users.",
            "We need community engagement and Telegram member acquisition for our DeFi project.",
            "Our crypto exchange is hiring brand ambassadors for a paid campaign.",
            "We need content creators and sponsored posts for our blockchain game.",
            "We are looking for an AMA host for our token project.",
            "Our new crypto game needs KOLs for promotion.",
            "We are looking for moderators for our DeFi app.",
        ]
        for post in posts:
            with self.subTest(post=post):
                self.assertTrue(self.verify_buyer_evidence(post))

    def test_evidence_verifier_rejects_unproven_or_seller_posts(self):
        posts = [
            "I offer crypto marketing services and promotion packages.",
            "Anyone want to exchange free cross-promotion with our project?",
            "We need a Solidity auditor for our blockchain project.",
            "Looking for users.",
        ]
        for post in posts:
            with self.subTest(post=post):
                self.assertFalse(self.verify_buyer_evidence(post))

    def test_workoff_early_access_feedback_post_is_not_a_marketing_service_buyer(self):
        message = (
            "I’m working on WorkOff, an AI-native workplace where humans and AI agents can work together. "
            "The product covers sales, marketing, engineering, QA, DevOps and operations. "
            "We’re currently opening Early Access and looking for feedback from founders, builders, "
            "and teams already experimenting with AI."
        )
        self.assertFalse(self.verify_buyer_evidence(message))

    def test_content_specialist_and_video_editor_job_post_is_not_a_client_lead(self):
        message = "Looking for a content specialist?, video editor for marketing? DM me please. Thank you."
        self.assertEqual(self.classify(message), [])
        self.assertFalse(self.verify_buyer_evidence(message))

    def test_fundraising_and_liquidity_request_is_not_a_marketing_service_buyer(self):
        message = (
            "We are developing a GameFi project and are looking for additional fund "
            "investment for liquidity and marketing, or we can sell the project and listing contract."
        )
        self.assertEqual(self.classify(message), [])
        self.assertFalse(self.verify_buyer_evidence(message))

    def test_generic_partnership_discussion_is_not_a_service_buyer(self):
        message = (
            "I always worry about onboarding users. This is when we need a big partnership "
            "to bring volume. The network rewards people for powering infrastructure; "
            "I also lean on advertising partners as a general growth idea."
        )
        self.assertFalse(self.verify_buyer_evidence(message))

    def test_clear_project_side_promotion_requests_still_pass(self):
        posts = [
            "Looking for a promoter who can get users for our AI agent launchpad platform.",
            "Our crypto project is looking for paid project promotion.",
            "We need content creators and sponsored posts for our blockchain game.",
            "Our DeFi app is looking for moderators for our community.",
        ]
        for post in posts:
            with self.subTest(post=post):
                self.assertTrue(self.verify_buyer_evidence(post))

    def test_direct_gamefi_marketing_agency_request_is_preserved(self):
        message = "Our GameFi project is looking for a marketing agency for its launch campaign."
        self.assertIn("Project Promotion", self.classify(message))
        self.assertTrue(self.verify_buyer_evidence(message))

    def test_new_web3_marketing_partner_request_is_detected(self):
        # A general marketing-partner request is classified under the broad
        # Content Distribution & Marketing service signal.
        self.assertIn(
            "Content Distribution & Marketing",
            self.classify("We are seeking a Web3 marketing partner for our blockchain launch"),
        )

    def test_user_acquisition_agency_request_is_detected(self):
        self.assertIn(
            "Project Promotion",
            self.classify("Need a user acquisition agency for our crypto wallet launch"),
        )

    def test_reciprocal_cross_promotion_and_exposure_swaps_are_not_buyers(self):
        posts = [
            "Looking for cross-promotion partners to exchange exposure between our crypto communities.",
            "We are seeking co-marketing partnerships where we promote each other for free.",
            "Open to mutual promotion and barter campaigns with other Web3 projects.",
        ]
        for post in posts:
            with self.subTest(post=post):
                self.assertEqual(self.classify(post), [])

    def test_real_world_vendor_and_noise_posts_from_latest_scan_are_rejected(self):
        posts = [
            "Hey everyone! I'm @San_mddf, BD at MyDollarFun. Looking for real users and genuine engagement on X (Twitter)? DM me! I'll offer you special discounts. You can also run your campaigns directly on our website. Also you can test any think in $1. For more details, feel free to DM me. Let's grow together!",
            "We provide quality iGaming, casino & sportsbook traffic across 32+ GEOs through Google PPC, Meta Ads, TG Ads & Influencers. Our focus is quality registrations and FTDs. Looking for quality traffic or interested in a partnership? DM @SalesDiplomat0.",
            "GET REAL USERS FOR YOUR MINI-APP OR CHANNEL. We deliver high-velocity traffic. 80k+ daily active users, 650k+ monthly reach. Services offered, price list, book your slot today.",
            "Will anyone ever need a moderator here?",
            "I'm a full-stack developer with 5+ years of experience building websites, applications, and digital products. I'm currently open to new projects and collaborations. If you need a developer, contact me.",
            "Im looking for traders in Kols",
        ]
        for post in posts:
            with self.subTest(post=post):
                self.assertEqual(self.classify(post), [])

    def test_buyer_requests_for_exchange_and_token_campaigns_are_preserved(self):
        self.assertIn("KOL & Influencer Marketing", self.classify("Looking for CEX KOLs, if you can bring traders DM me."))
        self.assertIn("KOL & Influencer Marketing", self.classify("Need KOLs that can generate volume for our exchange. DM me if you have a team."))
        self.assertIn("KOL & Influencer Marketing", self.classify("Looking for KOLs which help in token sale and increasing volume!"))

    def test_mydollarfun_style_user_engagement_promotion_is_rejected(self):
        message = (
            "Looking for real users and genuine engagement on X (Twitter)? "
            "DM me! I will offer you special discounts. You can also run your "
            "campaigns directly on our website. You can test anything for $1. "
            "For more details, feel free to DM me. Let us grow together!"
        )
        self.assertEqual(self.classify(message), [])

    def test_ad_account_provider_pitch_is_rejected_even_with_looking_for_cta(self):
        message = (
            "Hi, Sigma! Here is Malt Interactive which specializes in proving "
            "meta/Tiktok/Google ad accounts. We have credit lines enterprise-level "
            "and We provide a wide range of advertising accounts and related services. "
            "Suitable for all products. If you're looking for a reliable advertising "
            "account provider, feel free to contact me."
        )
        self.assertEqual(self.classify(message), [])

    def test_ad_account_supplier_variants_are_rejected(self):
        self.assertEqual(
            self.classify("We provide Meta and TikTok advertising accounts. DM us if you need a provider."),
            [],
        )
        self.assertEqual(
            self.classify("I specialize in supplying Google ad accounts and credit lines. Contact me."),
            [],
        )

    def test_expanded_buyer_detection_does_not_admit_vendor_promotion_ads(self):
        self.assertEqual(
            self.classify("We provide KOL marketing and paid promotion for crypto projects. DM us for rates."),
            [],
        )

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

    def test_worker_has_no_message_count_cap(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertNotIn("MAX_MESSAGES_PER_RUN", source)
        self.assertNotIn("message_limit_reached", source)
        self.assertIn('"message_count_limit": "unlimited"', source)
        self.assertIn("if dt >= window_end:", source)

    def test_message_scan_is_date_windowed_and_old_backlog_is_not_requested(self):
        from datetime import datetime, timezone
        start = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
        options = self.message_scan_kwargs(start)
        self.assertTrue(options["reverse"])
        self.assertEqual(options["offset_date"], start)
        self.assertNotIn("min_id", options)
        self.assertNotIn("limit", options)

    def test_supabase_secret_is_not_sent_as_bearer_jwt(self):
        headers = self.supabase_headers("sb_secret_test")
        self.assertEqual(headers["apikey"], "sb_secret_test")
        self.assertNotIn("Authorization", headers)

    def test_notification_alerts_fetch_all_pages_before_sending(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("async def notify_pending_leads(http):")
        end = source.index("async def send_scan_report", start)
        notify = source[start:end]
        self.assertIn('"offset": str(offset)', notify)
        self.assertIn("pending.extend(page)", notify)
        self.assertLess(notify.index("pending.extend(page)"), notify.index("for lead in pending"))

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

    def test_advice_to_another_member_is_not_a_client_lead(self):
        self.assertEqual(self.classify("You need marketing in spanish"), [])

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

    def test_classifier_keeps_broader_verified_buyer_wording(self):
        examples = [
            "Our new crypto game needs KOLs for promotion",
            "We are looking for moderators for our DeFi app",
            "Our Web3 startup is looking for a growth agency to increase users",
            "We need community engagement and Telegram member acquisition for our DeFi project",
            "Our crypto exchange is hiring brand ambassadors for a paid campaign",
        ]
        for message in examples:
            with self.subTest(message=message):
                self.assertTrue(self.classify(message))

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

    def test_classifier_accepts_explicit_marketing_agency_partner_request(self):
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

    def test_generic_beta_tester_posts_without_crypto_project_context_are_not_leads(self):
        self.assertEqual(self.classify("Looking for beta testers for our app"), [])
        self.assertEqual(self.classify("We are opening early access and need app testers"), [])
        self.assertEqual(self.classify("Looking for product feedback from early users"), [])

    def test_web3_project_looking_for_early_users_is_a_potential_lead(self):
        self.assertIn(
            "Project Review / VERDICT",
            self.classify(
                "We are building a Solana AI trading agent and looking for early users "
                "to try our MVP and share honest feedback."
            ),
        )

    def test_generic_cross_marketing_and_ama_partnership_invitation_is_rejected(self):
        self.assertEqual(
            self.classify(
                "We have two Web3 projects open for PR collaborations, X partnerships, "
                "joint campaigns, AMAs, and cross-marketing opportunities."
            ),
            [],
        )

    def test_telegram_promoter_offer_is_not_a_client_lead(self):
        self.assertEqual(
            self.classify(
                "Hiring Telegram promoters for daily paid promotions. "
                "Do you own a group with active members?"
            ),
            [],
        )

    def test_daily_paid_promotions_available_hiring_post_is_not_a_client_lead(self):
        self.assertEqual(
            self.classify(
                "HIRING TELEGRAM PROMOTERS! Daily Paid Promotions Available! "
                "Do you own a Telegram group or channel with active members? "
                "We are looking for promoters for paid promotions."
            ),
            [],
        )

    def test_kryptokite_free_article_and_cross_promotion_offer_is_rejected(self):
        self.assertEqual(
            self.classify(
                "We're building KryptoKite and looking to connect with promising crypto projects. "
                "We'll publish a dedicated project article and do social media cross-promotion. "
                "We're offering this collaboration free of charge."
            ),
            [],
        )

    def test_event_guest_speaker_signup_is_not_a_client_lead(self):
        self.assertEqual(
            self.classify(
                "Friday Spaces AMA - Guest Signup Open. "
                "We are looking for founders, KOLs, and project representatives "
                "to join us as guest speakers. DM me if interested."
            ),
            [],
        )

    def test_nikola_naro_style_web3_collaboration_post_is_rejected(self):
        self.assertEqual(
            self.classify(
                "We have two Web3 projects open to PR collaborations, X partnerships, "
                "joint campaigns, AMAs, and cross-marketing opportunities. "
                "We are open to mutually beneficial partnerships with crypto communities."
            ),
            [],
        )

    def test_cex_kol_and_trader_acquisition_request_is_a_potential_lead(self):
        self.assertIn(
            "KOL & Influencer Marketing",
            self.classify(
                "Looking for CEX KOLs, if you can bring traders DM me."
            ),
        )

    def test_bd_partner_recruitment_to_onboard_kols_is_not_a_client_lead(self):
        self.assertEqual(
            self.classify(
                "Looking for BD partners who can onboard high-volume KOLs to a new exchange."
            ),
            [],
        )

    def test_project_hiring_growth_marketers_and_kols_is_a_potential_lead(self):
        self.assertIn(
            "KOL & Influencer Marketing",
            self.classify(
                "Qurve is hiring growth marketers and KOLs to bring AI agent creators "
                "and active builders to its ecosystem."
            ),
        )

    def test_general_web3_partnership_invitation_is_rejected(self):
        self.assertEqual(
            self.classify(
                "We are open to mutually beneficial collaborations with Web3 projects, "
                "communities, and media partners."
            ),
            [],
        )

    def test_generic_promoter_request_for_ai_launchpad_users_is_a_prospect(self):
        self.assertIn(
            "Community Promotion",
            self.classify(
                "Looking for a promoter who can help get users for our AI agent launchpad platform."
            ),
        )

    def test_project_owner_can_say_we_offer_a_product_and_still_be_a_buyer(self):
        self.assertIn(
            "Community Promotion",
            self.classify(
                "We offer an AI agent launchpad platform and are looking for promoters to bring users."
            ),
        )

    def test_ai_influencer_content_creator_is_rejected_as_a_service_seller(self):
        self.assertEqual(
            self.classify(
                "I create aesthetic beauty, skincare and product promotional content using AI influencer models. "
                "I'm open to brand collaborations, UGC content creation, product promotions, paid partnerships, "
                "and AI influencer marketing."
            ),
            [],
        )

    def test_free_pr_and_cross_promotion_offer_is_rejected_as_a_vendor(self):
        self.assertEqual(
            self.classify(
                "We're offering this collaboration free of charge: project features and social media cross-promotion."
            ),
            [],
        )

    def test_no_upfront_fee_launchpad_offer_is_rejected_as_a_vendor(self):
        self.assertEqual(
            self.classify(
                "DM me, we have a good launchpad who not tack upfront fee."
            ),
            [],
        )

    def test_beggar_agency_sales_pitch_is_rejected_as_a_vendor(self):
        self.assertEqual(
            self.classify(
                "Gonçalo here, Head of sales at Beggar Agency. "
                "We work with the best streamers & influencers mainly from Portugal. "
                "If you are looking for consistent FTDs and high-quality traffic from the best, let’s connect."
            ),
            [],
        )

    def test_influencer_network_traffic_offer_is_rejected_as_a_vendor(self):
        self.assertEqual(
            self.classify(
                "We work with top streamers and influencers and can deliver qualified leads and FTDs. DM us."
            ),
            [],
        )

    def test_real_project_request_for_influencers_is_still_accepted(self):
        self.assertIn(
            "KOL & Influencer Marketing",
            self.classify("Our Web3 project is looking for influencers for our paid launch campaign.")
        )

    def test_affiliate_partner_recruitment_pitch_is_not_a_client_lead(self):
        self.assertEqual(
            self.classify(
                "SEEFX GLOBAL PARTNER RECRUITMENT. We are now welcoming global partners. "
                "Regional & Country Representatives, Marketing Professionals, Community Builders. "
                "Referral rewards and team commissions. Minimum first deposit: $500."
            ),
            [],
        )

    def test_paid_promotion_reseller_recruitment_is_not_a_client_lead(self):
        self.assertEqual(
            self.classify(
                "HIRING TELEGRAM PROMOTERS! Daily Paid Promotions Available! "
                "Do you own a Telegram group or channel with active members? "
                "We are looking for promoters for paid promotions."
            ),
            [],
        )

    def test_joined_group_scan_has_no_count_caps_and_resumes_per_message(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertNotIn("MAX_JOINED_GROUPS_PER_RUN", source)
        self.assertNotIn("MAX_MESSAGES_PER_RUN", source)
        self.assertNotIn("MAX_JOINED_MESSAGES_PER_RUN", source)
        self.assertNotIn("MAX_MESSAGES_PER_GROUP_PER_RUN", source)
        self.assertNotIn("SCAN_BUDGET_SECONDS", source)
        self.assertIn('bounded_int_env("POLL_SECONDS", 7200, 60, 86400)', source)
        self.assertIn("async for dialog in client.iter_dialogs()", source)
        self.assertIn('"window_progress"', source)
        self.assertIn('"last_message_id"', source)
        self.assertIn('kwargs["min_id"]', source)
        self.assertIn('state["next_window_start"]', source)
        self.assertIn("Only completed windows are skipped", source)
        self.assertIn("message_count_limit", source)
        run_code = source[source.index("async def run("):]
        self.assertNotIn("SearchGlobalRequest", run_code)
        self.assertNotIn("fetch_global_group_messages", run_code)
        self.assertNotIn("should_pause_group(meta)", run_code)

    def test_verdict_testing_service_buyer_request(self):
        self.assert_signal(
            "Project Review / VERDICT",
            "We need a beta testing team to test our Web3 app and provide structured feedback.",
        )

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

    def test_vendor_database_and_ad_account_inventory_posts_are_rejected(self):
        posts = [
            "Fresh Crypto, investors,business, depositors, recovery, bank Leads etc..Just Landed. We give you access to our private database tool.",
            "TABOOLA AD ACCOUNTS AVAILABLE! Regular Accounts, Agency Accounts, Network Accounts. DM for availability, pricing, and details.",
            "Premium Advertising Accounts. Looking for stable accounts? We have rental and purchase options available.",
            "Need a Team? We help set up multi-user call centre ops worldwide.",
        ]
        for post in posts:
            with self.subTest(post=post):
                self.assertEqual(self.classify(post), [])

    def test_explicit_project_campaign_request_remains_qualified(self):
        self.assertIn(
            "KOL & Influencer Marketing",
            self.classify("We are a Web3 project looking for KOLs for a paid token launch campaign. Please share your rates."),
        )

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

    def test_marketing_agency_self_promotion_ad_is_rejected(self):
        post = (
            "CRYPTO & FOREX BUSINESSES — LET'S SCALE! "
            "Looking for targeted traffic and potential customers for your platform? "
            "Digital marketing solutions tailored to your campaign goals. "
            "Reach the right audience with a smarter marketing strategy. MESSAGE ME TODAY!"
        )
        self.assertEqual(self.classify(post), [])

    def test_premium_advertising_network_vendor_post_is_rejected(self):
        post = (
            "PREMIUM ADVERTISING NETWORK SOLUTIONS "
            "Looking for traffic and advertising opportunities? "
            "MediaGo Quantcast Moloco Programmatic Advertising "
            "Traffic & Lead Generation. "
            "Business owners, media buyers and agencies are welcome! "
            "Send me a private message for details."
        )
        self.assertEqual(self.classify(post), [])

    def test_real_crypto_project_request_for_paid_marketing_still_passes(self):
        self.assertIn(
            "Project Promotion",
            self.classify(
                "Our crypto project is looking for a paid advertising campaign "
                "and a marketing agency to bring targeted traffic."
            ),
        )

    def test_real_crypto_project_request_for_targeted_traffic_still_passes(self):
        self.assertIn(
            "Project Promotion",
            self.classify(
                "Our crypto platform is looking for an agency to bring targeted traffic "
                "and potential customers through a paid marketing campaign."
            ),
        )


    def test_job_seekers_and_people_asking_for_nontechnical_roles_are_rejected(self):
        posts = [
            "Hey y'all! Official off my last role. I'm open to the next opportunity now. "
            "I was lead product manager for a 300m+ users gaming platform. Preferably remote.",
            "Is there anyone hiring team member for Marketing, Partnership, BD Manager, "
            "Operations, or any other non-technical position?",
            "I'm looking for a new role as a Marketing Manager in Web3.",
            "Available for new opportunities in business development or operations.",
        ]
        for post in posts:
            with self.subTest(post=post):
                self.assertEqual(self.classify(post), [])

    def test_free_marketing_tool_offer_is_rejected(self):
        self.assertEqual(
            self.classify(
                "Anyone looking for a free Marketing + Automation + Lead Generation tool "
                "for their business? If yes, DM me and I'll share the details."
            ),
            [],
        )

    def test_contact_data_service_vendor_is_rejected(self):
        self.assertEqual(
            self.classify(
                "Premium Global Contact Data Services. Our Telegram channel provides "
                "access to international contact datasets."
            ),
            [],
        )

    def test_growth_network_soliciting_projects_is_rejected(self):
        self.assertEqual(
            self.classify(
                "TrafficPlaza Growth Network is open for new projects. "
                "We're currently taking on new Web3 projects looking to grow through "
                "user acquisition, targeted traffic and CPA campaigns."
            ),
            [],
        )

    def test_investor_project_funding_request_is_not_a_marketing_lead(self):
        self.assertEqual(
            self.classify(
                "Private investors looking for projects to fund. "
                "DM if you have investment opportunities."
            ),
            [],
        )

    def test_actual_project_marketing_buyer_is_not_blocked_by_job_filter(self):
        self.assertIn(
            "KOL & Influencer Marketing",
            self.classify(
                "Our Web3 project is looking to hire KOLs for a paid marketing campaign. "
                "Please share your rates."
            ),
        )

    def test_recent_service_seller_false_positives_are_rejected(self):
        provider_posts = [
            "We provide targeted traffic, giveaways, targeting and API services. DM for rates and booking.",
            "We offer iGaming traffic, Google Ads, Meta Ads, Telegram Ads and influencer services. Contact us for pricing.",
            "We deliver KOL and influencer marketing services for Web3 projects. DM us for rates.",
        ]
        for message in provider_posts:
            with self.subTest(message=message):
                self.assertEqual(self.classify(message), [])

    def test_freelancer_open_to_new_projects_is_not_a_buyer(self):
        self.assertEqual(
            self.classify("I am a full-stack developer, open to new projects and collaborations."),
            [],
        )

    def test_ambiguous_moderator_question_is_not_a_recruitment_lead(self):
        self.assertEqual(
            self.classify("Will anyone ever need a moderator here?"),
            [],
        )

    def test_employer_side_recruitment_request_is_preserved(self):
        self.assertIn(
            "Recruitment",
            self.classify("Hiring a community manager and moderators for our crypto project."),
        )
        self.assertIn(
            "Recruitment",
            self.classify("We are looking for a developer for our Web3 wallet project."),
        )

    def test_ambiguous_kol_demand_is_not_promoted_to_buyer(self):
        for message in [
            "Anyone looking for KOLs?",
            "Need KOLs.",
            "Will anyone need influencers?",
        ]:
            with self.subTest(message=message):
                self.assertEqual(self.classify(message), [])

    def test_project_specific_kol_buying_intent_is_preserved(self):
        self.assertIn(
            "KOL & Influencer Marketing",
            self.classify("Looking for KOLs for our crypto launch."),
        )
        self.assertIn(
            "KOL & Influencer Marketing",
            self.classify("We need a paid influencer campaign for our Web3 project."),
        )




    def test_latest_igaming_traffic_provider_pitch_is_rejected(self):
        message = (
            "We provide quality iGaming, casino & sportsbook traffic across 32+ GEOs "
            "through Google PPC, Meta Ads (Facebook & Instagram), TG Ads & Influencers. "
            "Our focus is on quality registrations and First-Time Depositors (FTDs) "
            "to help brands grow. Looking for quality traffic or interested in a "
            "partnership? Let's connect! DM @SalesDiplomat0"
        )
        self.assertEqual(self.classify(message), [])

    def test_traffic_and_ftd_vendor_variants_are_rejected(self):
        for message in (
            "We provide targeted traffic and qualified registrations for casino brands. DM us.",
            "We deliver sportsbook FTDs across multiple GEOs through paid ads and influencers.",
            "Our agency offers iGaming traffic packages. Contact us for pricing.",
            "GET REAL USERS FOR YOUR MINI-APP OR CHANNEL. We deliver high-velocity traffic. "
            "Services Offered: giveaways, targeted growth and API integration. Price List: "
            "Standard Traffic $0.02+. Book your slot today.",
        ):
            with self.subTest(message=message):
                self.assertEqual(self.classify(message), [])

    def test_vendor_pitch_filters_use_real_word_boundaries(self):
        source = WORKER.read_text(encoding="utf-8")
        for name in (
            "SELLER_PITCH_CONTEXT", "RECRUITMENT_BUYER_CONTEXT", "KOL_PROJECT_CONTEXT",
            "INDIVIDUAL_CREATIVE_ROLE_CONTEXT", "CAPITAL_RAISE_CONTEXT",
            "DIRECT_SERVICE_BUY_REQUEST_CONTEXT",
        ):
            with self.subTest(name=name):
                start = source.index(name + " = re.compile(")
                end = source.index("\n)", start)
                block = source[start:end]
                self.assertIn(r"\b", block)
                self.assertNotIn(r"\\b", block)

    def test_job_seeker_moderator_post_is_rejected(self):
        self.assertEqual(
            self.classify("Will anyone ever need a moderator here? Since when did this job become so low-demand"),
            [],
        )



class TelegramNotificationGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(WORKER.read_text(encoding="utf-8"))
        node = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef)
            and item.name == "telegram_notification_block_reason"
        )
        namespace = {"re": re, "classify": lambda evidence: ["Project Promotion"] if "our crypto project needs a paid marketing campaign" in evidence.lower() else []}
        needed_constants = {
            "BUYING_CONTEXT", "CRYPTO_CONTEXT", "NON_BUYER_CONTEXT",
            "SELLER_AD_CONTEXT", "SELLER_POST_CONTEXT", "SELLER_PITCH_CONTEXT",
            "INDIVIDUAL_CREATIVE_ROLE_CONTEXT", "CAPITAL_RAISE_CONTEXT",
            "DIRECT_SERVICE_BUY_REQUEST_CONTEXT",
        }
        for assignment in tree.body:
            if isinstance(assignment, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in needed_constants
                for target in assignment.targets
            ):
                names = {
                    target.id for target in assignment.targets
                    if isinstance(target, ast.Name)
                }
                if names & needed_constants:
                    exec(compile(ast.Module(body=[assignment], type_ignores=[]), str(WORKER), "exec"), namespace)
        verify_node = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == "verify_buyer_evidence"
        )
        exec(compile(ast.Module(body=[verify_node], type_ignores=[]), str(WORKER), "exec"), namespace)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(WORKER), "exec"), namespace)
        cls.check = staticmethod(namespace["telegram_notification_block_reason"])

    def test_strong_evidenced_buyer_can_be_notified(self):
        lead = {
            "evidence_summary": "Our crypto project needs a paid marketing campaign before launch. We need an agency.",
            "service_need": "Project Promotion",
            "priority_score": 75,
            "notes": "post_scan_audit: buyer_intent_verified",
        }
        self.assertIsNone(self.check(lead))

    def test_missing_post_scan_audit_marker_is_blocked(self):
        lead = {
            "evidence_summary": "Our crypto project needs a paid marketing campaign before launch. We need an agency.",
            "service_need": "Project Promotion",
        }
        self.assertEqual(self.check(lead), "missing_post_scan_buyer_audit")

    def test_missing_evidence_is_blocked(self):
        self.assertEqual(
            self.check({"evidence_summary": "", "service_need": "Project Promotion", "priority_score": 90}),
            "missing_or_too_short_evidence",
        )

    def test_low_priority_does_not_block_evidence_proven_buyer(self):
        self.assertIsNone(
            self.check({"evidence_summary": "Our crypto project needs a paid marketing campaign before launch.", "service_need": "Project Promotion", "priority_score": 1, "notes": "post_scan_audit: buyer_intent_verified"}),
        )

    def test_direct_buyer_at_minimum_qualified_score_can_be_notified(self):
        lead = {
            "evidence_summary": "Our crypto project needs a paid marketing campaign before launch. We need an agency.",
            "service_need": "Project Promotion",
            "priority_score": 55,
            "notes": "post_scan_audit: buyer_intent_verified",
        }
        self.assertIsNone(self.check(lead))

    def test_new_lead_notifications_run_only_after_post_scan_audit(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertNotIn("async def notify_saved_lead(http, dedupe_key):", source)
        self.assertNotIn('await notify_saved_lead(http, payload["dedupe_key"])', source)
        audit = source.index("audit_result = await audit_current_scan_leads(http, scan_run_id)")
        notify = source.index("await notify_pending_leads(http)", audit)
        self.assertLess(audit, notify)

    def test_non_buyer_evidence_is_blocked(self):
        self.assertEqual(
            self.check({"evidence_summary": "We offer marketing services to crypto projects and need clients.", "service_need": "Project Promotion", "priority_score": 90}),
            "seller_or_vendor_post",
        )

    def test_missing_service_category_is_blocked(self):
        self.assertEqual(
            self.check({"evidence_summary": "Our crypto project needs a paid marketing campaign before launch.", "service_need": "", "priority_score": 90}),
            "missing_service_need",
        )


class GroupScanningOptimizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(WORKER.read_text(encoding="utf-8"))
        wanted = {
            "group_priority", "rotate_group_ids", "should_pause_group", "message_scan_kwargs",
            "two_hour_window", "reset_group_quality_metrics",
        }
        nodes = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in wanted
        ]
        from datetime import datetime, timedelta, timezone
        namespace = {"CLASSIFIER_RULES_VERSION": 3, "datetime": datetime, "timedelta": timedelta, "timezone": timezone}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(WORKER), "exec"), namespace)
        cls.group_priority = staticmethod(namespace["group_priority"])
        cls.rotate_group_ids = staticmethod(namespace["rotate_group_ids"])
        cls.should_pause_group = staticmethod(namespace["should_pause_group"])
        cls.message_scan_kwargs = staticmethod(namespace["message_scan_kwargs"])
        cls.two_hour_window = staticmethod(namespace["two_hour_window"])
        cls.reset_group_quality_metrics = staticmethod(namespace["reset_group_quality_metrics"])


    def test_failed_message_and_window_resume_from_last_checkpoint(self):
        source = WORKER.read_text(encoding="utf-8")
        run_code = source[source.index("async def run("):]
        self.assertIn('kwargs["min_id"]', run_code)
        self.assertIn('gp["last_message_id"] = int(msg.id)', run_code)
        self.assertIn("write_state(state)", run_code)
        self.assertIn("retry_after = retry_delay_seconds(exc)", run_code)
        self.assertIn("await asyncio.sleep(retry_after)", run_code)
        self.assertIn("next_window_start", run_code)
        self.assertIn('return any(row.get("status") == "completed" for row in response.json())', source)
        self.assertIn('json={"status": "running", "finished_at": None}', source)

    def test_two_hour_windows_advance_without_replaying_expired_periods(self):
        from datetime import datetime, timedelta, timezone
        anchor = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
        self.assertIsNone(self.two_hour_window(anchor, anchor + timedelta(minutes=5)))
        first = self.two_hour_window(anchor, anchor + timedelta(hours=2, minutes=5))
        self.assertEqual(first, (anchor, anchor + timedelta(hours=2)))
        second = self.two_hour_window(anchor, anchor + timedelta(hours=4, minutes=5))
        self.assertEqual(second, (anchor + timedelta(hours=2), anchor + timedelta(hours=4)))

    def test_groups_with_real_leads_receive_higher_priority(self):
        good = {"qualified_leads": 2, "buyer_signals": 5, "seller_ads": 0}
        noisy = {"qualified_leads": 0, "buyer_signals": 0, "seller_ads": 20}
        self.assertGreater(self.group_priority(good), self.group_priority(noisy))

    def test_joined_group_scan_rotates_after_last_group(self):
        ids = ["a", "b", "c", "d"]
        self.assertEqual(self.rotate_group_ids(ids, "b"), ["c", "d", "a", "b"])
        self.assertEqual(self.rotate_group_ids(ids, "missing"), ids)
        self.assertEqual(self.rotate_group_ids([], "a"), [])

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
        self.assertIn('"status": "eq.new"', notification_code)
        self.assertIn('"telegram_notified_at": "is.null"', notification_code)
        self.assertIn('"owner_id": "eq." + SUPABASE_OWNER_ID', notification_code)
        self.assertIn('"limit": "100"', notification_code)
        self.assertIn('"offset": str(offset)', notification_code)
        self.assertIn('pending.extend(page)', notification_code)

    def test_worker_numeric_environment_settings_are_bounded(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn('bounded_int_env("POLL_SECONDS", 7200, 60, 86400)', source)
        self.assertIn('bounded_int_env("LOOKBACK_DAYS", 30, 1, 3650)', source)
        self.assertIn('os.getenv("INITIAL_SCAN_START_AT"', source)
        self.assertIn('state["initial_scan_since"]', source)
        self.assertIn('state["next_window_start"]', source)
        self.assertIn('kwargs["min_id"]', source)
        self.assertIn("dt >= window_end", source)
        self.assertNotIn("message_scan_kwargs(last_seen", source)

    def test_scan_report_is_joined_group_only(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn("Joined groups available:", source)
        self.assertIn("Joined groups selected this run:", source)
        self.assertIn("no message-count limit", source)
        self.assertIn("Joined groups checked:", source)
        self.assertIn("Joined-group messages processed:", source)
        self.assertNotIn("Public groups with qualified buyer signals:", source)
        self.assertNotIn("Non-joined public groups", source)

    def test_scan_report_exposes_post_scan_audit_result(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("async def send_scan_report")
        end = source.index("async def login", start)
        report = source[start:end]
        self.assertIn("Post-scan audit status:", report)
        self.assertIn("post_scan_audited", report)
        self.assertIn("post_scan_verified", report)
        self.assertIn("post_scan_rejected", report)



class LeadDisplayLabelTests(unittest.TestCase):
    def test_group_title_is_not_misrepresented_as_project_name(self):
        worker_source = open(__file__.replace("test_worker_rules.py", "worker.py"), encoding="utf-8").read()
        self.assertNotIn('f"Potential project (verify) — {group_name}"', worker_source)
        self.assertEqual(worker_source.count('"company_name": "Potential project (verify)"'), 1)



    def test_scan_run_telemetry_uses_only_existing_schema_columns(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("async def finish_scan_run(http, run_id, stats):")
        end = source.index("\nasync def ", start + 20)
        block = source[start:end]
        # scan_runs currently has only these writable reporting columns;
        # source-separated counters are packed into error_summary JSON.
        for column in ("finished_at", "status", "sources_checked", "leads_found", "leads_saved", "error_summary"):
            with self.subTest(column=column):
                self.assertIn('"' + column + '"', block)
        for unsupported in ("public_messages_processed", "joined_messages_processed", "duration_seconds"):
            with self.subTest(unsupported=unsupported):
                self.assertNotIn('"' + unsupported + '":', block.split('payload = {', 1)[1].split('}', 1)[0])

    def test_pending_notifications_are_not_limited_to_current_scan_time(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("async def notify_pending_leads(http):")
        end = source.index("\n\nasync def scan_window_already_recorded", start)
        block = source[start:end]
        self.assertNotIn('"created_at":', block)
        self.assertIn('"telegram_notified_at": "is.null"', block)
        self.assertIn('"order": "created_at.asc,id.asc"', block)

    def test_blocked_pending_leads_are_preserved_in_manual_review(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("async def notify_pending_leads")
        end = source.index("\n\nasync def scan_window_already_recorded", start)
        block = source[start:end]
        self.assertIn('"status": "review"', block)
        self.assertIn('"status": "eq.new"', block)
        self.assertIn('"telegram_gate: " + block_reason', block)

    def test_notification_gate_blocks_explicit_service_seller_posts(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("def telegram_notification_block_reason")
        end = source.index("\n\nasync def send_telegram_to_chat", start)
        block = source[start:end]
        self.assertIn("SELLER_AD_CONTEXT", block)
        self.assertIn("SELLER_POST_CONTEXT", block)
        self.assertIn("SELLER_PITCH_CONTEXT", block)
        self.assertIn('"seller_or_vendor_post"', block)
        self.assertIn("post_scan_audit: buyer_intent_verified", block)
        self.assertNotIn("or classify(evidence)", block)

    def test_telegram_scan_run_metrics_are_persisted_to_supabase(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn('"source_scan_run_id": scan_run_id', source)
        self.assertIn("async def start_scan_run(http, window_start, window_end):", source)
        self.assertIn("async def finish_scan_run(http, run_id, stats):", source)
        self.assertIn('"window_start": stats.get("window_start")', source)
        self.assertIn('"window_end": stats.get("window_end")', source)
        self.assertIn('"joined_messages_processed"', source)
        self.assertIn('"joined_leads_saved"', source)
        self.assertIn("await finish_scan_run(http, scan_run_id, stats)", source)

    def test_same_two_hour_window_is_not_scanned_twice(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn("async def scan_window_already_recorded(http, window_start):", source)
        self.assertIn('"window_start": "eq." + window_start.isoformat()', source)
        self.assertIn('"window_start": window_start.isoformat()', source)
        self.assertIn('return any(row.get("status") == "completed" for row in response.json())', source)
        self.assertIn("if await scan_window_already_recorded(http, window_start):", source)
        self.assertIn('"status": "running", "finished_at": None', source)


    def test_per_chat_lead_alert_delivery_is_persisted_without_raw_chat_ids(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("async def notify_pending_leads")
        end = source.index("async def scan_window_already_recorded", start)
        block = source[start:end]
        self.assertIn("telegram_deliveries", block)
        self.assertIn("recipient_key(chat_id)", block)
        self.assertIn("telegram_notified_at", block)
        self.assertNotIn("send_telegram_to_all", block)

    def test_scan_report_delivery_is_recorded_in_scan_run(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("async def send_scan_report")
        end = source.index("async def login", start)
        block = source[start:end]
        self.assertIn("report_deliveries", block)
        self.assertIn("report_delivered_at", block)
        self.assertIn("report_delivery_error", block)

    def test_scan_processing_errors_are_not_reported_as_clean_success(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("async def finish_scan_run")
        end = source.index("async def mark_scan_run_failed", start)
        block = source[start:end]
        self.assertIn('"scan_errors"', block)
        self.assertIn('"status": "failed" if', block)



    def test_scan_metrics_persistence_failure_fails_the_worker(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn('if not await finish_scan_run(http, scan_run_id, stats):', source)
        self.assertIn('mark_scan_run_failed(http, scan_run_id, exc)', source)

    def test_disabled_scan_report_is_recorded(self):
        source = WORKER.read_text(encoding="utf-8")
        start = source.index("async def send_scan_report")
        end = source.index("async def login", start)
        block = source[start:end]
        self.assertIn('report_delivery_error', block)
        self.assertIn('disabled: bot token or chat ID is not configured', block)


    def test_alert_delivery_counts_are_reported_and_persisted(self):
        source = WORKER.read_text(encoding="utf-8")
        finish_start = source.index("async def finish_scan_run")
        finish_end = source.index("\n\nasync def mark_scan_run_failed", finish_start)
        finish = source[finish_start:finish_end]
        report_start = source.index("async def send_scan_report")
        report_end = source.index("\n\nasync def login", report_start)
        report = source[report_start:report_end]
        for key in ("alerts_delivered", "alerts_failed", "leads_moved_to_review", "alert_load_error"):
            self.assertIn('"' + key + '"', finish)
            self.assertIn("stats.get('" + key + "'", report)

    def test_audit_is_bound_to_the_exact_scan_run(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn('"source_scan_run_id": scan_run_id', source)
        self.assertIn('"source_scan_run_id": "eq." + str(scan_run_id)', source)
        self.assertIn("audit_current_scan_leads(http, scan_run_id)", source)


    def test_configured_scan_anchor_overrides_stale_host_state(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertIn('initial_start = os.getenv("INITIAL_SCAN_START_AT", "").strip()', source)
        self.assertIn('if state.get("initial_scan_since") != configured_anchor:', source)
        render = (WORKER.parent.parent / "render.yaml").read_text(encoding="utf-8")
        self.assertIn('INITIAL_SCAN_START_AT', render)
        self.assertIn('2026-11-15T22:04:35+00:00', render)


class WorkerHttpBehaviorTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(WORKER.read_text(encoding="utf-8"))

    @classmethod
    def load_functions(cls, names, namespace):
        nodes = [
            node for node in cls.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in names
        ]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(WORKER), "exec"), namespace)
        return namespace

    class Response:
        def __init__(self, status_code, data=None, text=""):
            self.status_code = status_code
            self._data = data if data is not None else []
            self.text = text

        def json(self):
            return self._data

    class FakeHttp:
        def __init__(self, lead):
            self.lead = lead
            self.patches = []
            self.get_params = []

        async def get(self, url, headers=None, params=None, timeout=None):
            self.get_params.append(params or {})
            return WorkerHttpBehaviorTests.Response(200, [self.lead])

        async def patch(self, url, headers=None, params=None, json=None, timeout=None):
            payload = json or {}
            self.patches.append(payload)
            self.lead.update(payload)
            return WorkerHttpBehaviorTests.Response(204)

    async def test_partial_alert_delivery_retries_only_the_failed_chat(self):
        lead = {
            "id": "lead-1",
            "company_name": "Potential project",
            "service_need": "Project Promotion",
            "priority_score": 70,
            "evidence_summary": "Our crypto project needs a paid marketing campaign before launch. We need an agency.",
            "evidence_date": "2026-11-16",
            "evidence_url": "https://t.me/example/10",
            "telegram_group_url": "https://t.me/example",
            "contacts": [],
            "outreach_english": "Hello",
            "outreach_bengali": "হ্যালো",
            "telegram_deliveries": {},
            "notes": "",
        }
        calls = []
        outcomes = {"chat-a": (True, None), "chat-b": (False, "temporary failure")}

        async def send(http, chat_id, message, timeout=30):
            calls.append(chat_id)
            return outcomes[chat_id]

        namespace = {
            "BOT_TOKEN": "test-token",
            "BOT_CHAT_IDS": ["chat-a", "chat-b"],
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_OWNER_ID": "owner-1",
            "SUPABASE_SERVICE_ROLE_KEY": "server-key",
            "supabase_headers": lambda key: {"apikey": key},
            "telegram_notification_block_reason": lambda item: None,
            "recipient_key": lambda value: hashlib.sha256(str(value).encode()).hexdigest()[:20],
            "format_telegram_lead": lambda item: "test lead",
            "send_telegram_to_chat": send,
            "datetime": __import__("datetime").datetime,
            "timezone": __import__("datetime").timezone,
            "log": logging.getLogger("test-aenzo-worker"),
        }
        self.load_functions({"notify_pending_leads"}, namespace)
        first_http = self.FakeHttp(lead)
        first = await namespace["notify_pending_leads"](first_http)
        self.assertEqual(first["alerts_delivered"], 0)
        self.assertEqual(first["alerts_failed"], 1)
        self.assertEqual(first_http.lead["telegram_deliveries"], {
            namespace["recipient_key"]("chat-a"): first_http.lead["telegram_deliveries"][namespace["recipient_key"]("chat-a")]
        })
        self.assertNotIn("telegram_notified_at", first_http.lead)

        calls.clear()
        outcomes["chat-b"] = (True, None)
        second_http = self.FakeHttp(first_http.lead)
        second = await namespace["notify_pending_leads"](second_http)
        self.assertEqual(calls, ["chat-b"])
        self.assertEqual(second["alerts_delivered"], 1)
        self.assertEqual(second["alerts_failed"], 0)
        self.assertIn("telegram_notified_at", second_http.lead)
        self.assertEqual(len(second_http.lead["telegram_deliveries"]), 2)

    async def test_audit_queries_only_candidates_from_its_scan_run(self):
        namespace = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_OWNER_ID": "owner-1",
            "SUPABASE_SERVICE_ROLE_KEY": "server-key",
            "supabase_headers": lambda key: {"apikey": key},
            "SELLER_AD_CONTEXT": re.compile(r"(?!)"),
            "SELLER_POST_CONTEXT": re.compile(r"(?!)"),
            "SELLER_PITCH_CONTEXT": re.compile(r"(?!)"),
            "verify_buyer_evidence": lambda text: False,
            "classify": lambda text: [],
            "log": logging.getLogger("test-aenzo-worker"),
        }
        self.load_functions({"audit_current_scan_leads"}, namespace)
        http = self.FakeHttp({"id": "unused"})
        async def get_empty(url, headers=None, params=None, timeout=None):
            http.get_params.append(params or {})
            return self.Response(200, [])
        http.get = get_empty
        result = await namespace["audit_current_scan_leads"](http, "scan-run-123")
        self.assertTrue(result["ok"])
        self.assertEqual(http.get_params[0]["source_scan_run_id"], "eq.scan-run-123")
        self.assertEqual(http.get_params[0]["status"], "eq.new")
        self.assertNotIn("created_at", http.get_params[0])
        self.assertEqual(http.patches, [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
