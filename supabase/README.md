# Supabase project files

- `schema_snapshot.sql` is a bootstrap snapshot of the current public schema, RLS policies, indexes, and grants. It contains no user/lead data.
- The numbered migrations are changes made after that schema existed.
- On a brand-new Supabase project, make sure Supabase Auth is enabled, apply `schema_snapshot.sql` once, then apply the numbered migrations in order.
- On the existing AENZO project, do **not** re-run the snapshot; its tables and policies are already present and the two numbered migrations are recorded.
- Back up actual lead rows separately. A schema snapshot is not a data backup.

Edge Function source is version-controlled under `functions/<function-name>/index.ts`. The live functions require JWT verification; deploy them with the Supabase CLI or the Supabase dashboard after reviewing the project URL and secrets. Never commit service-role or Telegram credentials.
