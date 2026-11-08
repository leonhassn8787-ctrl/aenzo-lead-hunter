-- Keep indexes that cover foreign-key columns. They may have low read counts,
-- but support efficient parent-row updates/deletes and avoid FK table scans.
CREATE INDEX IF NOT EXISTS discovery_candidates_source_id_idx
  ON public.discovery_candidates (source_id);
CREATE INDEX IF NOT EXISTS scan_runs_owner_id_idx
  ON public.scan_runs (owner_id);
