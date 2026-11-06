# Tristan's existing database: legacy source

**Status:** UNTOUCHED.

KoroFarm has not connected to, read, copied or changed this database. Nothing in the code refers to it. It is a
separate legacy source, and any migration decision follows a read-only assessment that has not started.

**Product-owner decision (5 November 2026):** preserve it unchanged. No connection, migration, deletion or
modification is authorized.

## Future read-only assessment (needs the product owner's and the owner's authorization)

1. **Access.** A read-only database role or an export, provided by its owner. Its credentials are kept outside this
   repository and outside chat.
2. **Inventory.** Tables, row counts, date ranges, and which fields hold personal or commercial data. No data is
   copied at this stage.
3. **Mapping report.** For each table, which KoroFarm structure it would map to (operational `public` tables, or
   statistics in `agri`), with quality issues, duplicates and gaps.
4. **Decision** by the product owner: migrate, reference, or leave. Any migration would then be designed as:
   - a dry-run-first, idempotent import with provenance, like the agricultural importer;
   - never a direct copy;
   - never overwriting KoroFarm records.
