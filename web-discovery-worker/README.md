# AENZO Web Discovery Worker

Scans public RSS and Google News RSS discovery indexes for Web3/crypto/AI project, funding, grant and product launch signals.

Important:
- Discovery records are stored in `public.discovery_candidates`, not promoted to confirmed leads.
- A human review is required before a candidate becomes a lead. After successful enrichment, records with no explicit marketing/buyer need are automatically marked `rejected`; explicit-need records remain in the review queue. Failed or incomplete enrichment stays unverified for human review.
- CoinDesk and Product Hunt use public RSS feeds.
- Other directory sources use Google News RSS site-restricted search because no verified public feed was configured for them.
- The worker respects each source row’s `is_active` setting in `public.lead_sources`; inactive sources are skipped.
- RootData's free API requires an API key; CryptoRank funding endpoints require a paid tier. Neither paid API is called by this worker.
- No paid service or API is enabled.
- Modern Supabase `sb_secret_...` keys are sent only in the `apikey` header, not as a Bearer JWT.
- The GitHub Actions workflow is manual-dispatch only; automatic web-discovery scheduling is disabled to avoid extra recurring runs. Manual runs record results in `public.scan_runs`.
