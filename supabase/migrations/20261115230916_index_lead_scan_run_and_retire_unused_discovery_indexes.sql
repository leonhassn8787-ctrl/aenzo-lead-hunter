create index if not exists leads_source_scan_run_id_idx
  on public.leads (source_scan_run_id)
  where source_scan_run_id is not null;

drop index if exists public.discovery_candidates_owner_status_idx;
drop index if exists public.discovery_candidates_source_id_idx;
drop index if exists public.discovery_candidates_buyer_intent_idx;
