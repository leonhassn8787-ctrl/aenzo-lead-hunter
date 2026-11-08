-- Schema snapshot for restoring the current AENZO Lead Hunter database.
-- This is a bootstrap snapshot, not a numbered migration. On a fresh Supabase
-- project, apply it before running the numbered files in supabase/migrations.
-- Existing production projects should not re-run it; their tables already exist.

create table if not exists public.lead_sources (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  source_name text not null,
  source_type text not null default 'public_web',
  source_url text not null,
  is_active boolean not null default true,
  notes text,
  last_checked_at timestamptz,
  created_at timestamptz not null default now(),
  unique (owner_id, source_url)
);

create table if not exists public.leads (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  company_name text not null,
  website text,
  industry text,
  service_need text,
  lead_type text not null default 'potential_buyer'
    check (lead_type in ('direct_buyer', 'potential_buyer', 'partnership_opportunity')),
  priority_score integer not null default 50
    check (priority_score between 1 and 100),
  status text not null default 'new'
    check (status in ('new', 'contacted', 'interested', 'negotiation', 'converted', 'rejected')),
  evidence_summary text,
  evidence_url text,
  evidence_date date,
  telegram_group_url text,
  contacts jsonb not null default '[]'::jsonb,
  outreach_english text,
  outreach_bengali text,
  notes text,
  dedupe_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  telegram_notified_at timestamptz,
  telegram_notification_error text
);

create table if not exists public.discovery_candidates (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  source_id uuid references public.lead_sources(id) on delete set null,
  source_name text not null,
  title text not null,
  summary text,
  evidence_url text not null,
  published_at timestamptz,
  signal_type text not null default 'potential_buyer',
  signal_score integer not null default 0 check (signal_score between 0 and 100),
  review_status text not null default 'new'
    check (review_status in ('new', 'reviewed', 'converted', 'rejected')),
  dedupe_key text not null,
  created_at timestamptz not null default now(),
  unique (owner_id, dedupe_key)
);

create table if not exists public.scan_runs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'completed', 'failed', 'cancelled')),
  sources_checked integer not null default 0,
  leads_found integer not null default 0,
  leads_saved integer not null default 0,
  error_summary text,
  created_at timestamptz not null default now()
);

create table if not exists public.user_settings (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  report_timezone text not null default 'Asia/Riyadh',
  report_time time not null default '19:30:00',
  telegram_chat_id text,
  preferred_language text not null default 'bn',
  include_non_web3 boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Supporting indexes and the database-level identity/evidence dedupe guards.
create index if not exists discovery_candidates_created_idx
  on public.discovery_candidates (created_at desc);
create index if not exists discovery_candidates_owner_status_idx
  on public.discovery_candidates (owner_id, review_status, signal_score desc);
create index if not exists discovery_candidates_source_id_idx
  on public.discovery_candidates (source_id);
create index if not exists leads_created_at_idx
  on public.leads (created_at desc);
create unique index if not exists leads_owner_dedupe_key_uidx
  on public.leads (owner_id, dedupe_key) where dedupe_key is not null;
create index if not exists leads_owner_priority_idx
  on public.leads (owner_id, priority_score desc);
create index if not exists leads_owner_status_idx
  on public.leads (owner_id, status);
create index if not exists scan_runs_owner_id_idx
  on public.scan_runs (owner_id);

-- All browser-facing tables are owner-scoped by RLS.
alter table public.lead_sources enable row level security;
alter table public.leads enable row level security;
alter table public.discovery_candidates enable row level security;
alter table public.scan_runs enable row level security;
alter table public.user_settings enable row level security;

do $$
begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='lead_sources' and policyname='Owners manage their lead sources') then
    create policy "Owners manage their lead sources" on public.lead_sources
      for all to authenticated using ((select auth.uid()) = owner_id)
      with check ((select auth.uid()) = owner_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='leads' and policyname='Owners manage their leads') then
    create policy "Owners manage their leads" on public.leads
      for all to authenticated using ((select auth.uid()) = owner_id)
      with check ((select auth.uid()) = owner_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='discovery_candidates' and policyname='discovery_candidates_owner_all') then
    create policy discovery_candidates_owner_all on public.discovery_candidates
      for all to authenticated using ((select auth.uid()) = owner_id)
      with check ((select auth.uid()) = owner_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='scan_runs' and policyname='Owners manage their scan runs') then
    create policy "Owners manage their scan runs" on public.scan_runs
      for all to authenticated using ((select auth.uid()) = owner_id)
      with check ((select auth.uid()) = owner_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='user_settings' and policyname='Owners manage their settings') then
    create policy "Owners manage their settings" on public.user_settings
      for all to authenticated using ((select auth.uid()) = owner_id)
      with check ((select auth.uid()) = owner_id);
  end if;
end
$$;

-- Authenticated users receive only row-scoped CRUD. service_role is reserved
-- for trusted server-side workers; anon receives no table privileges.
grant select, insert, update, delete on all tables in schema public to authenticated;
grant all on all tables in schema public to service_role;
revoke all on all tables in schema public from anon;
revoke truncate, trigger, references on all tables in schema public from authenticated;
