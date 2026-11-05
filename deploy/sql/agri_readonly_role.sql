-- KoroFarm: read-only role for agricultural statistics (agri schema). REVIEWED ARTIFACT; NOT RUN BY ANY MIGRATION.
--
-- Purpose: the future read-only analytics path (evidence-grounded answers, dashboards) reads public statistics through a
-- role that cannot see operational trade data and cannot write anything. Run it only after the product owner approves
-- read-only analytics on the target database (AFTER_WP5_INTEGRATION_CHECKLIST.md, step 7).
--
-- What it does:
--   * creates a NOLOGIN group role korofarm_agri_reader (idempotent);
--   * grants USAGE on schema agri and SELECT on its tables, now and for tables the migration role creates later;
--   * grants nothing in public (operational data) and no write privilege anywhere;
--   * never grants anything to anon, authenticated, service_role or PUBLIC.
-- What it does not do: create a login. A login role with its own password is created separately by the database
-- owner and granted membership: CREATE ROLE <name> LOGIN PASSWORD '<from your password manager>' IN ROLE korofarm_agri_reader;
-- Never put that password in this repository.
--
-- Verify afterwards (expected: true, false, false):
--   select has_table_privilege('korofarm_agri_reader', 'agri.observations', 'SELECT'),
--          has_table_privilege('korofarm_agri_reader', 'agri.observations', 'INSERT'),
--          has_table_privilege('korofarm_agri_reader', 'public.requirements', 'SELECT');

begin;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'korofarm_agri_reader') then
        create role korofarm_agri_reader nologin;
    end if;
end
$$;

revoke all on schema public from korofarm_agri_reader;
grant usage on schema agri to korofarm_agri_reader;
grant select on all tables in schema agri to korofarm_agri_reader;
alter default privileges in schema agri grant select on tables to korofarm_agri_reader;

-- Row-level security is enabled on agri tables only where Supabase client roles exist (it is not, by default); if it
-- is enabled later, add explicit read policies for this role, never for the client roles.

commit;
