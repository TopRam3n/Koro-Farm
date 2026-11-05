"""Keep KoroFarm's tables out of Supabase's auto-generated Data API.

KoroFarm reaches its database only through the FastAPI backend. Supabase also serves the `public` schema over HTTPS
(PostgREST, and GraphQL) to its `anon` and `authenticated` roles, using the publishable key that every browser holds,
and to `service_role` with the secret key. On a Supabase project, without the protections below anyone could read or
change KoroFarm's tables directly, skipping authentication, tenancy and every business rule.

Three layers (migrations 0026 and 0027 apply the first two; the product-owner setup guide covers the third):
  1. no privileges for the Supabase client roles on KoroFarm's tables (or their columns), sequences or functions,
     including EXECUTE that functions get through PUBLIC, and no default privileges that would grant them on objects
     created later;
  2. row-level security enabled on every table with no policies, so `anon` and `authenticated` see nothing even if a
     grant reappears. The table owner, which the backend connects as, is not subject to it. `service_role` bypasses
     RLS in Supabase, so for it layer 1 is the only database-side control;
  3. the Data API switched off in the Supabase dashboard.

Effective privileges are evaluated with has_*_privilege, so grants reaching a client role through PUBLIC or through
role membership count. Future objects are checked two ways: the default-privilege catalog for every role that owns
objects in `public` (plus the connected role), and `probe_future_objects`, which creates a table, view, sequence and
function inside a savepoint, measures what the client roles could do with them, and rolls the savepoint back.

`exposure_findings` reports what is still exposed; `scripts/check_staging.py` runs it. `lockdown_statements`
re-applies layers 1 and 2 for objects the connected role owns (for example after restoring a dump taken with
--no-privileges into a new project). Outside Supabase the client roles do not exist and nothing applies.
"""
from uuid import uuid4

from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError

SUPABASE_CLIENT_ROLES = ("anon", "authenticated", "service_role")
SCHEMA = "public"
# Schemas that must stay entirely closed to the client roles: no usage, no table or sequence privilege (migration 0029).
CLOSED_SCHEMAS = ("agri",)
OBJECT_TYPES = {"r": "tables", "S": "sequences", "f": "functions", "T": "types", "n": "schemas"}

# A client role "reaches" a grantee if it is the grantee, is a member of it, or the grantee is PUBLIC (oid 0).
_REACHES = "(case when a.grantee = 0 then true else pg_has_role(r.oid, a.grantee, 'USAGE') end)"

TABLE_REACH = """(has_table_privilege(r.oid, c.oid, 'SELECT') or has_table_privilege(r.oid, c.oid, 'INSERT')
    or has_table_privilege(r.oid, c.oid, 'UPDATE') or has_table_privilege(r.oid, c.oid, 'DELETE')
    or has_table_privilege(r.oid, c.oid, 'TRUNCATE') or has_table_privilege(r.oid, c.oid, 'REFERENCES')
    or has_table_privilege(r.oid, c.oid, 'TRIGGER')
    or has_any_column_privilege(r.oid, c.oid, 'SELECT') or has_any_column_privilege(r.oid, c.oid, 'INSERT')
    or has_any_column_privilege(r.oid, c.oid, 'UPDATE') or has_any_column_privilege(r.oid, c.oid, 'REFERENCES'))"""
SEQUENCE_REACH = """(has_sequence_privilege(r.oid, c.oid, 'USAGE') or has_sequence_privilege(r.oid, c.oid, 'SELECT')
    or has_sequence_privilege(r.oid, c.oid, 'UPDATE'))"""


def present_roles(connection: Connection, roles: tuple[str, ...] = SUPABASE_CLIENT_ROLES) -> list[str]:
    if connection.dialect.name != "postgresql":
        return []
    return list(connection.execute(text("select rolname from pg_roles where rolname = any(:roles) order by rolname"),
                                   {"roles": list(roles)}).scalars())


def _rows(connection: Connection, sql: str, params: dict) -> list[dict]:
    return [dict(row._mapping) for row in connection.execute(text(sql), params)]


def default_privilege_findings(connection: Connection, roles: list[str]) -> list[dict]:
    """Default privileges that would give a client role (directly, via membership or via PUBLIC) access to an object
    created later in `public` by any role that owns objects there, or by the connected role.

    PostgreSQL's built-in default grants EXECUTE on new functions to PUBLIC unless the owner has a global
    (schema-less) default-privilege entry for functions that leaves PUBLIC out; a schema-level entry cannot remove it.
    That implicit grant is reported with source 'built-in default'."""
    owners = list(connection.execute(text("""
        select distinct o from (
            select pg_get_userbyid(c.relowner) as o from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = :schema
            union select pg_get_userbyid(p.proowner) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = :schema
            union select current_user::text) owners order by 1"""), {"schema": SCHEMA}).scalars())
    findings = _rows(connection, f"""
        select distinct pg_get_userbyid(d.defaclrole) as owner, d.defaclobjtype as object_type,
               case when a.grantee = 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end as grantee,
               r.rolname as role, case when d.defaclnamespace = 0 then 'global' else 'schema public' end as source
        from pg_default_acl d left join pg_namespace n on n.oid = d.defaclnamespace
        cross join lateral aclexplode(d.defaclacl) a
        join pg_roles r on r.rolname = any(:roles)
        where (n.nspname = :schema or d.defaclnamespace = 0) and pg_get_userbyid(d.defaclrole) = any(:owners)
          and d.defaclobjtype in ('r', 'S', 'f') and {_REACHES}
        order by 1, 2, 3, 4""", {"schema": SCHEMA, "roles": roles, "owners": owners})
    without_global_function_entry = connection.execute(text("""
        select o from unnest(cast(:owners as text[])) o
        where not exists (select 1 from pg_default_acl d where d.defaclnamespace = 0 and d.defaclobjtype = 'f'
                            and pg_get_userbyid(d.defaclrole) = o)
        order by 1"""), {"owners": owners}).scalars()
    for owner in without_global_function_entry:
        findings += [{"owner": owner, "object_type": "f", "grantee": "PUBLIC", "role": role,
                      "source": "built-in default"} for role in roles]
    return findings


def probe_future_objects(connection: Connection, roles: list[str]) -> dict:
    """Create one table, view, sequence and function in `public` as the connected role inside a savepoint, record
    which client roles could use them, then roll the savepoint back. Nothing persists. Needs CREATE on `public`."""
    suffix = uuid4().hex[:12]
    names = {kind: f"kf_readiness_probe_{kind}_{suffix}" for kind in ("table", "view", "sequence", "function")}
    savepoint = connection.begin_nested()
    try:
        connection.execute(text(f'create table {SCHEMA}."{names["table"]}" (id integer)'))
        connection.execute(text(f'create view {SCHEMA}."{names["view"]}" as select 1 as one'))
        connection.execute(text(f'create sequence {SCHEMA}."{names["sequence"]}"'))
        connection.execute(text(f'create function {SCHEMA}."{names["function"]}"() returns integer '
                                f"language sql as 'select 1'"))
        params = {"roles": roles, "schema": SCHEMA, "table": names["table"], "view": names["view"],
                  "sequence": names["sequence"], "function": names["function"]}
        exposed = _rows(connection, f"""
            select case c.relname when :table then 'table' else 'view' end as object, r.rolname as role
            from pg_class c join pg_namespace n on n.oid = c.relnamespace cross join pg_roles r
            where n.nspname = :schema and c.relname in (:table, :view) and r.rolname = any(:roles) and {TABLE_REACH}
            union all
            select 'sequence', r.rolname from pg_class c join pg_namespace n on n.oid = c.relnamespace cross join pg_roles r
            where n.nspname = :schema and c.relname = :sequence and r.rolname = any(:roles) and {SEQUENCE_REACH}
            union all
            select 'function', r.rolname from pg_proc p join pg_namespace n on n.oid = p.pronamespace cross join pg_roles r
            where n.nspname = :schema and p.proname = :function and r.rolname = any(:roles)
              and has_function_privilege(r.oid, p.oid, 'EXECUTE')
            order by 1, 2""", params)
        return {"ran": True, "role": connection.execute(text("select current_user")).scalar(), "exposed": exposed}
    except SQLAlchemyError as exc:
        return {"ran": False, "reason": type(exc).__name__, "exposed": []}
    finally:
        savepoint.rollback()


def exposure_findings(connection: Connection, roles: tuple[str, ...] = SUPABASE_CLIENT_ROLES,
                      probe: bool = True) -> dict:
    """Read-only (the optional probe is rolled back). Which client roles can reach which objects now and which objects
    created later would be reachable, which tables lack RLS, and who owns what."""
    found = present_roles(connection, roles)
    if not found:
        return {"applicable": False, "roles": [], "table_privileges": [], "sequence_privileges": [],
                "function_privileges": [], "tables_without_rls": [], "default_privileges": [],
                "future_objects": {"ran": False, "reason": "not applicable", "exposed": []},
                "objects_not_owned": [], "schema_usage": [], "closed_schema_usage": [], "rls_bypass_roles": [],
                "exposed": False, "verified": True}
    params = {"roles": found, "schema": SCHEMA, "schemas": [SCHEMA, *CLOSED_SCHEMAS]}
    table_privileges = _rows(connection, f"""
        select case when n.nspname = :schema then c.relname else n.nspname || '.' || c.relname end as object, r.rolname as role
        from pg_class c join pg_namespace n on n.oid = c.relnamespace cross join pg_roles r
        where n.nspname = any(:schemas) and c.relkind in ('r', 'p', 'v', 'm', 'f') and r.rolname = any(:roles) and {TABLE_REACH}
        order by 1, 2""", params)
    sequence_privileges = _rows(connection, f"""
        select case when n.nspname = :schema then c.relname else n.nspname || '.' || c.relname end as object, r.rolname as role
        from pg_class c join pg_namespace n on n.oid = c.relnamespace cross join pg_roles r
        where n.nspname = any(:schemas) and c.relkind = 'S' and r.rolname = any(:roles) and {SEQUENCE_REACH}
        order by 1, 2""", params)
    function_privileges = _rows(connection, """
        select p.oid::regprocedure::text as object, r.rolname as role,
               (p.proacl is null or exists (select 1 from aclexplode(p.proacl) a
                                            where a.grantee = 0 and a.privilege_type = 'EXECUTE')) as via_public
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace cross join pg_roles r
        where n.nspname = :schema and r.rolname = any(:roles) and has_function_privilege(r.oid, p.oid, 'EXECUTE')
        order by 1, 2""", params)
    tables_without_rls = list(connection.execute(text("""
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = :schema and c.relkind in ('r', 'p') and not c.relrowsecurity order by 1"""),
        {"schema": SCHEMA}).scalars())
    objects_not_owned = _rows(connection, """
        select c.relname as object, c.relkind::text as kind, pg_get_userbyid(c.relowner) as owner
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = :schema and c.relkind in ('r', 'p', 'v', 'm', 'f', 'S') and pg_get_userbyid(c.relowner) <> current_user
        union all
        select p.oid::regprocedure::text, 'function', pg_get_userbyid(p.proowner)
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = :schema and pg_get_userbyid(p.proowner) <> current_user
        order by 1""", {"schema": SCHEMA})
    schema_usage = list(connection.execute(text("""
        select rolname from pg_roles where rolname = any(:roles) and has_schema_privilege(oid, :schema, 'USAGE')
        order by 1"""), params).scalars())
    closed_schema_usage = _rows(connection, """
        select n.nspname as schema, r.rolname as role from pg_namespace n cross join pg_roles r
        where n.nspname = any(:closed) and r.rolname = any(:roles) and has_schema_privilege(r.oid, n.oid, 'USAGE')
        order by 1, 2""", {"closed": list(CLOSED_SCHEMAS), "roles": found})
    rls_bypass_roles = list(connection.execute(text(
        "select rolname from pg_roles where rolname = any(:roles) and rolbypassrls order by 1"), params).scalars())
    default_privileges = default_privilege_findings(connection, found)
    future = probe_future_objects(connection, found) if probe else {"ran": False, "reason": "not requested", "exposed": []}
    exposed = bool(table_privileges or sequence_privileges or function_privileges or tables_without_rls
                   or default_privileges or future["exposed"] or closed_schema_usage)
    return {"applicable": True, "roles": found, "table_privileges": table_privileges,
            "sequence_privileges": sequence_privileges, "function_privileges": function_privileges,
            "tables_without_rls": tables_without_rls, "default_privileges": default_privileges,
            "future_objects": future, "objects_not_owned": objects_not_owned, "schema_usage": schema_usage,
            "closed_schema_usage": closed_schema_usage,
            "rls_bypass_roles": rls_bypass_roles, "exposed": exposed, "verified": future["ran"]}


def lockdown_statements(connection: Connection, roles: tuple[str, ...] = SUPABASE_CLIENT_ROLES) -> list[str]:
    """The statements that apply layers 1 and 2 for the roles present (none outside Supabase). Idempotent. Covers
    objects and default privileges of the connected role only; objects_not_owned in the findings need their owner."""
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
        f"alter default privileges revoke all on tables from {grantees}",
        f"alter default privileges revoke all on sequences from {grantees}",
        f"alter default privileges revoke all on functions from {grantees}",
        "alter default privileges revoke execute on functions from public",
    ]
    functions = connection.execute(text("""
        select format('%I.%I(%s)', n.nspname, p.proname, pg_get_function_identity_arguments(p.oid))
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = :schema and pg_get_userbyid(p.proowner) = current_user
          and (p.proacl is null or exists (select 1 from aclexplode(p.proacl) a where a.grantee = 0))
        order by 1"""), {"schema": SCHEMA}).scalars()
    statements += [f"revoke execute on function {function} from public" for function in functions]
    tables = connection.execute(text("""
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = :schema and c.relkind in ('r', 'p') and not c.relrowsecurity
          and pg_get_userbyid(c.relowner) = current_user order by 1"""), {"schema": SCHEMA}).scalars()
    statements += [f'alter table {SCHEMA}."{table}" enable row level security' for table in tables]
    return statements
