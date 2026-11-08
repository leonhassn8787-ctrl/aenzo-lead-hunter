-- Remove two helper indexes added during audit that remained unused.
-- Keeping unused indexes increases write overhead without improving current queries.
DROP INDEX IF EXISTS public.discovery_candidates_source_id_idx;
DROP INDEX IF EXISTS public.scan_runs_owner_id_idx;
