# Reviewed SQL artifacts

**Alembic is the only migration mechanism.** The files here are for review and for databases where a reviewer wants
to read exactly what will run; they are generated from, or kept beside, the Alembic migrations in
`src/backend/alembic/versions/`. Do not edit a generated file by hand, and do not apply both a file and the
matching migration.

| File | What it is | How it is produced or used |
|---|---|---|
| `wp5_0028_0029_upgrade.sql` | Exactly what migrations 0028 (notifications and contact consent) and 0029 (agricultural intelligence schema) run on PostgreSQL, from revision 0027, including the `alembic_version` updates | Generated offline (below). Verified on 5 November 2026: applied with `psql` to a disposable PostgreSQL 17 database at 0027 with Supabase's client roles simulated. Result: revision 0029, row-level security on the new public tables, 20 `agri` tables, no `agri` access for `anon`, and `check_staging`'s `data_api_grants` PASS |
| `agri_readonly_role.sql` | An opt-in, read-only role for agricultural statistics (no access to operational data, no writes) | Not part of any migration. Run only after the product owner approves read-only analytics (`docs/product/AFTER_WP5_INTEGRATION_CHECKLIST.md`) |

## Regenerating the upgrade file

From `src/backend`, with a placeholder PostgreSQL URL (offline mode connects to nothing):

```bash
DATABASE_URL="postgresql+psycopg://offline:offline@offline.invalid/korofarm" \
  ../../.venv/Scripts/python -m alembic upgrade 0027_supabase_data_api_hardening:head --sql > ../../deploy/sql/wp5_0028_0029_upgrade.sql
sed -i 's/%%/%/g' ../../deploy/sql/wp5_0028_0029_upgrade.sql
```

The `sed` step is required: SQLAlchemy doubles `%` for the psycopg driver, which un-doubles it at run time. In a file
run by `psql`, a doubled `%%I` inside `format()` would be a literal `%` and the `DO` blocks would fail.

## Applying it (only with the product owner's go-ahead, and only to the intended database)

1. Back up first (`docs/product/R1_INFRASTRUCTURE_PLAN.md`, section 6).
2. Prefer `python -m alembic upgrade head` (setup guide §1.9). Use the file only when a reviewer must apply the
   reviewed text itself: `psql ... -v ON_ERROR_STOP=1 -f deploy/sql/wp5_0028_0029_upgrade.sql`.
3. Run `python -m src.backend.scripts.check_staging` afterwards; `migrations` and `data_api_grants` must PASS.
