"""Keep KoroFarm's tables out of Supabase's auto-generated Data API.

KoroFarm reaches its database only through the FastAPI backend. Supabase also serves every table in the `public`
schema over HTTPS (PostgREST) to its `anon` and `authenticated` roles, using the publishable key that every browser
holds. On a Supabase project, without the protections below anyone could read or change KoroFarm's tables directly,
skipping authentication, tenancy and every business rule.

Three layers (migration 0026 applies the first two; the product-owner setup guide covers the third):
  1. no privileges for the Supabase client roles on KoroFarm's tables, sequences or functions, now or for objects
     created later (default privileges);
  2. row-level security enabled on every table with no policies, so the client roles see nothing even if a grant
     reappears (the table owner, which the backend connects as, is not subject to it);
  3. the Data API switched off in the Supabase dashboard.

`exposure_findings` reports what is still exposed; `scripts/check_staging.py` runs it. `lockdown_statements`
re-applies layers 1 and 2 (for example after restoring a dump taken with --no-privileges into a new project).
Outside Supabase the client roles do not exist and nothing applies.
"""
from sqlalchemy import Connection, text

SUPABASE_CLIENT_ROLES = ("anon", "authenticated", "service_role")
SCHEMA = "public"


def present_roles(connection: Connection, roles: tuple[str, ...] = SUPABASE_CLIENT_ROLES) -> list[str]:
    if connection.dialect.name != "postgresql":
        return []
    return list(connection.execute(text("select rolname from pg_roles where rolname = any(:roles) order by rolname"),
                                   {"roles": list(roles)}).scalars())


def exposure_findings(connection: Connection, roles: tuple[str, ...] = SUPABASE_CLIENT_ROLES) -> dict:
    """Read-only. Which client roles can reach which objects, which tables lack RLS, which default grants remain."""
    found = present_roles(connection, roles)
    if not found:
        return {"applicable": False, "roles": [], "table_privileges": [], "sequence_privileges": [],
                "function_privileges": [], "tables_without_rls": [], "default_privileges": [], "exposed": False}
    params = {"roles": found, "schema": SCHEMA}
    table_privileges = [dict(row._mapping) for row in connection.execute(text("""
        select c.relname as object, r.rolname as role
        from pg_class c join pg_namespace n on n.oid = c.relnamespace cross join pg_roles r
        where n.nspname = :schema and c.relkind in ('r', 'p', 'v', 'm', 'f') and r.rolname = any(:roles)
          and (has_table_privilege(r.oid, c.oid, 'SELECT') or has_table_privilege(r.oid, c.oid, 'INSERT')
               or has_table_privilege(r.oid, c.oid, 'UPDATE') or has_table_privilege(r.oid, c.oid, 'DELETE')
               or has_table_privilege(r.oid, c.oid, 'TRUNCATE'))
        order by 1, 2"""), params)]
    sequence_privileges = [dict(row._mapping) for row in connection.execute(text("""
        select c.relname as object, r.rolname as role
        from pg_class c join pg_namespace n on n.oid = c.relnamespace cross join pg_roles r
        where n.nspname = :schema and c.relkind = 'S' and r.rolname = any(:roles)
          and (has_sequence_privilege(r.oid, c.oid, 'USAGE') or has_sequence_privilege(r.oid, c.oid, 'UPDATE'))
        order by 1, 2"""), params)]
    function_privileges = [dict(row._mapping) for row in connection.execute(text("""
        select p.proname as object, r.rolname as role
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace cross join pg_roles r
        where n.nspname = :schema and r.rolname = any(:roles) and has_function_privilege(r.oid, p.oid, 'EXECUTE')
        order by 1, 2"""), params)]
    tables_without_rls = list(connection.execute(text("""
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = :schema and c.relkind in ('r', 'p') and not c.relrowsecurity order by 1"""),
        {"schema": SCHEMA}).scalars())
    default_privileges = [dict(row._mapping) for row in connection.execute(text("""
        select pg_get_userbyid(d.defaclrole) as owner, d.defaclobjtype as object_type, a.grantee::regrole::text as role
        from pg_default_acl d left join pg_namespace n on n.oid = d.defaclnamespace
        cross join lateral aclexplode(d.defaclacl) a
        where (n.nspname = :schema or d.defaclnamespace = 0) and a.grantee::regrole::text = any(:roles)
          and pg_get_userbyid(d.defaclrole) = current_user
        order by 1, 2, 3"""), params)]
    exposed = bool(table_privileges or sequence_privileges or function_privileges or tables_without_rls)
    return {"applicable": True, "roles": found, "table_privileges": table_privileges,
            "sequence_privileges": sequence_privileges, "function_privileges": function_privileges,
            "tables_without_rls": tables_without_rls, "default_privileges": default_privileges, "exposed": exposed}


def lockdown_statements(connection: Connection, roles: tuple[str, ...] = SUPABASE_CLIENT_ROLES) -> list[str]:
    """The statements that apply layers 1 and 2 for the roles present (none outside Supabase). Idempotent."""
    found = present_roles(connection, roles)
    if not found:
        return []
    grantees = ", ".join(f'"{role}"' for role in found)
    statements = [
        f"revoke all on all tables in schema {SCHEMA} from {grantees}",
        f"revoke all on all sequences in schema {SCHEMA} from {grantees}",
        f"revoke all on all functions in schema {SCHEMA} from {grantees}",
        f"alter default privileges in schema {SCHEMA} revoke all on tables from {grantees}",
        f"alter default privileges in schema {SCHEMA} revoke all on sequences from {grantees}",
        f"alter default privileges in schema {SCHEMA} revoke all on functions from {grantees}",
    ]
    tables = connection.execute(text("""
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = :schema and c.relkind in ('r', 'p') and not c.relrowsecurity
          and pg_get_userbyid(c.relowner) = current_user order by 1"""), {"schema": SCHEMA}).scalars()
    statements += [f'alter table {SCHEMA}."{table}" enable row level security' for table in tables]
    return statements
