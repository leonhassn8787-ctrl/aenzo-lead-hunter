-- Restrict browser-authenticated roles from high-impact table privileges.
-- Existing owner-scoped CRUD policies remain unchanged.
REVOKE TRUNCATE, TRIGGER, REFERENCES ON ALL TABLES IN SCHEMA public FROM authenticated;

-- New public tables created by the migration owner should not be exposed to anon
-- by default. Authenticated retains CRUD but not TRUNCATE/TRIGGER/REFERENCES.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE TRUNCATE, TRIGGER, REFERENCES ON TABLES FROM authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM anon, authenticated;
