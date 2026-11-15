-- Atomic two-hour scan-window claims and durable Telegram delivery evidence.
alter table public.scan_runs
  add column if not exists window_start timestamptz,
  add column if not exists window_end timestamptz,
  add column if not exists report_deliveries jsonb not null default '{}'::jsonb,
  add column if not exists report_delivered_at timestamptz,
  add column if not exists report_delivery_error text;

create unique index if not exists scan_runs_owner_window_start_uidx
  on public.scan_runs (owner_id, window_start)
  where window_start is not null;

alter table public.leads
  add column if not exists telegram_deliveries jsonb not null default '{}'::jsonb;
