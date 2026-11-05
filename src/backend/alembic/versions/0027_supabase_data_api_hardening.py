"""close what 0026 left open to Supabase's client roles: PUBLIC function execution and global default privileges

Revision ID: 0027_supabase_data_api_hardening
Revises: 0026_supabase_data_api_lockdown

Applies only on PostgreSQL where Supabase's client roles (anon, authenticated, service_role) exist; elsewhere it
does nothing. No rows are read or changed.
* PostgreSQL grants EXECUTE on every new function to PUBLIC, which every client role inherits; 0026 revoked only
  direct grants. This revokes PUBLIC's EXECUTE on the public schema's functions the migration role owns, and adds the
  global default-privilege entry that stops new functions getting it (a schema-level entry cannot remove it).
* Revokes the client roles' global (schema-less) default privileges too, in case the project has any.
See app/infrastructure/database/data_api.py. Downgrade does nothing: re-exposing objects is never automated.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0027_supabase_data_api_hardening"
down_revision: Union[str, None] = "0026_supabase_data_api_lockdown"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

HARDENING = """
do $$
declare
    grantees text;
    item record;
begin
    select string_agg(quote_ident(rolname), ', ' order by rolname) into grantees
    from pg_roles where rolname in ('anon', 'authenticated', 'service_role');
    if grantees is null then
        return;
    end if;
    execute format('alter default privileges revoke all on tables from %s', grantees);
    execute format('alter default privileges revoke all on sequences from %s', grantees);
    execute format('alter default privileges revoke all on functions from %s', grantees);
    execute 'alter default privileges revoke execute on functions from public';
    for item in
        select format('%I.%I(%s)', n.nspname, p.proname, pg_get_function_identity_arguments(p.oid)) as signature
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and pg_get_userbyid(p.proowner) = current_user
    loop
        execute format('revoke execute on function %s from public', item.signature);
    end loop;
end
$$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(HARDENING)


def downgrade() -> None:
    pass
