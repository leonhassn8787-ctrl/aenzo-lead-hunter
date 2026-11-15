-- Keep ambiguous Telegram matches in a review queue instead of discarding them.
alter table public.leads drop constraint if exists leads_status_check;
alter table public.leads add constraint leads_status_check
  check (status = any (array['review'::text,'new'::text,'contacted'::text,'interested'::text,'negotiation'::text,'converted'::text,'rejected'::text]));
