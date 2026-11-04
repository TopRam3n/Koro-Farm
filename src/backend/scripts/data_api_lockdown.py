"""Re-apply the Supabase Data API lockdown (migration 0026) after a restore. Dry run unless --apply.

  python -m src.backend.scripts.data_api_lockdown            # print what would be revoked / enabled
  python -m src.backend.scripts.data_api_lockdown --apply    # execute, in one transaction

Needed when a dump taken with --no-privileges is restored into a new Supabase project, whose default grants may give
the restored tables to the Data API roles again. Changes privileges and table settings only; no row is read or
written. Refuses APP_ENV=production without --production (production changes need their own approval).
"""
import argparse
import os
import sys

from sqlalchemy import text


def main(argv=None, env=None, engine=None) -> int:
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description="Re-apply the Supabase Data API lockdown")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--production", action="store_true", help="allow APP_ENV=production (separately approved)")
    args = parser.parse_args(argv)
    if env.get("APP_ENV", "").strip().lower() == "production" and not args.production:
        print("refusing to change production without --production", file=sys.stderr)
        return 2
    from src.backend.app.infrastructure.database.data_api import exposure_findings, lockdown_statements
    if engine is None:
        from src.backend.app.infrastructure.database.session import create_engine_from_url
        engine = create_engine_from_url(env.get("DATABASE_URL") or None)
    with engine.begin() as connection:
        statements = lockdown_statements(connection)
        if not statements:
            print("no Supabase client roles in this database: nothing to do")
            return 0
        for statement in statements:
            print(statement)
        if not args.apply:
            print("dry run: nothing was changed")
            return 0
        for statement in statements:
            connection.execute(text(statement))
        findings = exposure_findings(connection)
    print("applied; still exposed" if findings["exposed"] else "applied; nothing exposed")
    return 1 if findings["exposed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
