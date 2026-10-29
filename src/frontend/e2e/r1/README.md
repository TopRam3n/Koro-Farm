# R1 browser E2E

Runs the R1 order workflow through the real UI against a live stack:

- production Next.js build (live mode, no demo replay);
- FastAPI backend with real membership-based authorization (`APP_ENV=test`, demo auth bypass **off**);
- a disposable PostgreSQL database migrated with Alembic;
- `support/auth-stub.mjs`, a **test-only** stand-in for the Supabase Auth endpoints the app calls
  (password sign-in, token refresh, `GET /auth/v1/user`, logout). The login page and the backend's token
  check run unchanged; they point at the stand-in instead of a hosted Supabase project.

The specs create every buyer, supplier, lot and order through the UI with run-unique names. The seed
creates only two organizations and three users.

## Procedure used (28 Oct 2026)

From the repository root, with a disposable PostgreSQL server (see `src/backend/.env.test.local`, not committed):

```bash
# 1. Fresh database, migrations, two test organizations and users
createdb -h 127.0.0.1 -p 55499 -U kf_r1_test korofarm_r1_disposable_e2e
export DATABASE_URL=postgresql+psycopg://kf_r1_test:<password>@127.0.0.1:55499/korofarm_r1_disposable_e2e
(cd src/backend && ../../.venv/Scripts/python.exe -m alembic upgrade head)
.venv/Scripts/python.exe -m src.backend.scripts.seed_e2e /path/outside/repo/users.json

# 2. Auth stand-in and API
node src/frontend/e2e/r1/support/auth-stub.mjs /path/outside/repo/users.json 54999 &
SUPABASE_URL=http://127.0.0.1:54999 SUPABASE_PUBLISHABLE_KEY=e2e-test-key APP_ENV=test \
  ALLOW_INSECURE_DEMO_AUTH=false CORS_ORIGINS=http://127.0.0.1:3100 \
  .venv/Scripts/python.exe -m uvicorn src.backend.app.main:app --host 127.0.0.1 --port 8100 &

# 3. Frontend (production build, live mode)
cd src/frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8100 NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54999 \
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=e2e-test-key NEXT_PUBLIC_APP_MODE=live NEXT_PUBLIC_AUTH_MODE=live npx next build
npx next start -p 3100 -H 127.0.0.1 &

# 4. Tests
R1_E2E_USERS=/path/outside/repo/users.json npx playwright test -c playwright.r1.config.ts
```

The users file holds generated test passwords; keep it outside the repository. Screenshots are written to
`artifacts/r1-e2e-screens/` (copies of one run are in `docs/product/evidence/wp1/`).
