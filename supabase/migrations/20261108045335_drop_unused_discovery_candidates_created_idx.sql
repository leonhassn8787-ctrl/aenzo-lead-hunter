-- This standalone created_at index was not used by the current owner/status-filtered review query.
-- The composite owner/status/score index remains for that workload.
drop index if exists public.discovery_candidates_created_idx;
