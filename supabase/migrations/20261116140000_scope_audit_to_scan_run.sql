-- Tie every automatically collected lead to the exact scan run that found it.
-- The post-scan evidence audit can then touch only this run's candidates.
alter table public.leads
  add column if not exists source_scan_run_id uuid;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.leads'::regclass
      and conname = 'leads_source_scan_run_id_fkey'
  ) then
    alter table public.leads
      add constraint leads_source_scan_run_id_fkey
      foreign key (source_scan_run_id)
      references public.scan_runs(id)
      on delete set null;
  end if;
end
$$;

create index if not exists leads_owner_scan_run_status_idx
  on public.leads (owner_id, source_scan_run_id, status)
  where source_scan_run_id is not null;
