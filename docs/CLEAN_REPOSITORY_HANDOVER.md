# Clean integration branch — October 21, 2026

Integrated the agricultural intelligence implementation and reliability hotfix with `origin/main` at `731c459`, preserving the newer role-based authentication and marketplace changes. This is a Git branch handover, not a production deployment.

Included: backend/frontend application code, validation tests, ingestion commands, original official-source snapshots, manifests, frozen forecast versions and handover documents. Generated videos, screenshots and browser reports are no longer versioned; local copies in the original workspace are preserved. Local agent assets, temporary work and environment credentials are excluded. The existing video-recording source script remains tracked. Source receipts and saved model files have Git attributes preventing line-ending conversion, because their bytes are hashed.

Verification from a separate clean worktree:

- Backend: 137 passed, 9 skipped; the skips require `POSTGRES_TEST_DATABASE_URL`. Two existing dependency deprecation warnings remain.
- Frontend: 21 unit tests passed; ESLint, TypeScript and the production demo build passed.
- Chromium offline rehearsal: 13 passed, including Intelligence Lab, separate FAOSTAT context, invalid snapshot handling and the synthetic ginger dropout/recovery.
- Preserved provenance verification passed against all 37 original PDFs and 120 normalized records. Saved forecast SHA-256 remains `35afa002842522eaffed6eac0792248719a10acfb69f3f6a72dd59ddbe8b8b00`. No model training command was run.
- The newer profile page used `replaceAll` with an older configured TypeScript library target; changed to equivalent global replacement. No role behavior changed.
- Intelligence browser failure tests now intercept either cached or backend transport. `PLAYWRIGHT_BASE_URL` optionally selects a separate preview port; default remains 3000.
- CI installs the agricultural intelligence dependency extra and builds before checking generated Next type references. Remote CI results are separate from these local checks.

`npm ci` reported 18 dependency advisories: 5 moderate, 10 high and 3 critical. This branch is not a security certification. No automatic or breaking dependency updates were applied; review the dependency audit separately before a production release. PostgreSQL concurrency and historical training-execution/publication-vintage limitations remain as documented in `ML_RELIABILITY_HOTFIX.md`.

Offline startup and validation commands are in the root README. Public official snapshots are committed so running the demo does not depend on source websites being reachable. The original workspace and local creative assets were not deleted.
