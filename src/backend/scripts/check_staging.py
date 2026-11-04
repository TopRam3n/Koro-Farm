"""Check a staging deployment end to end without revealing credentials. Read-only: no row is written anywhere.

  python -m src.backend.scripts.check_staging                                   # configuration, database, Supabase
  python -m src.backend.scripts.check_staging --api-url https://api.staging.example.org \\
      --frontend-origin https://staging.example.org                             # plus the deployed API and CORS

Reads the same environment as the API (APP_ENV, DATABASE_URL, SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, ...). Prints one
line per check, PASS / FAIL / WARN / SKIP, and exits 1 if anything failed. Never prints a password, key or token: the
database URL is shown with its password hidden and keys only as "present".

Checks
  configuration   the API's own fail-closed startup checks (core/config.py) and APP_ENV=staging
  database        connects; server version; whether this connection uses TLS; pooler mode from the port
  migrations      the database is at the newest Alembic revision
  data_api_grants Supabase client roles hold no privilege on KoroFarm's tables and every table has RLS (0026)
  data_api_http   the publishable key cannot read a KoroFarm table through Supabase's REST endpoint
  auth_settings   Supabase Auth answers; email sign-in enabled; whether public sign-up is open
  api_health      GET /health (process) and GET /health/worker (exception monitoring; 503 unless OPERATIONAL)
  api_auth        a request without a token is refused with 401
  cors            the frontend origin is allowed and an unrelated origin is not
  model_provider  which recovery model provider is configured and whether it may run here
This is not the staging authentication test (signing in real users, refresh, sign-out, cross-tenant): run
`npm run test:staging-auth` for that (docs/product/STAGING_AUTH_VERIFICATION.md).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BACKEND = Path(__file__).resolve().parents[1]
UNRELATED_ORIGIN = "https://unrelated-origin.invalid"
PROBE_TABLE = "organizations"


@dataclass
class Check:
    name: str
    status: str  # PASS | FAIL | WARN | SKIP
    detail: str

    def line(self) -> str:
        return f"{self.status:<4}  {self.name:<16} {self.detail}"


@dataclass
class HttpResult:
    status: int
    headers: dict
    body: str


def http_request(method: str, url: str, headers: Mapping[str, str] | None = None, timeout: float = 10) -> HttpResult:
    request = Request(url, method=method, headers=dict(headers or {}))
    try:
        with urlopen(request, timeout=timeout) as response:
            return HttpResult(response.status, {k.lower(): v for k, v in response.headers.items()},
                              response.read(4096).decode("utf-8", "replace"))
    except HTTPError as exc:
        return HttpResult(exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()},
                          exc.read(4096).decode("utf-8", "replace") if exc.fp else "")


Http = Callable[..., HttpResult]


def _supabase(env: Mapping[str, str]) -> tuple[str, str]:
    url = (env.get("SUPABASE_URL") or env.get("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = env.get("SUPABASE_PUBLISHABLE_KEY") or env.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY") or ""
    return url, key


def check_configuration(env: Mapping[str, str]) -> Check:
    from src.backend.app.core.config import UnsafeConfigurationError, environment, validate_runtime_configuration
    try:
        validate_runtime_configuration(env)
    except UnsafeConfigurationError as exc:
        return Check("configuration", "FAIL", str(exc))
    if environment(env) != "staging":
        return Check("configuration", "WARN", f"startup checks pass, but APP_ENV is {environment(env)!r}, not 'staging'")
    if env.get("ALLOW_INSECURE_DEMO_AUTH"):
        return Check("configuration", "FAIL", "ALLOW_INSECURE_DEMO_AUTH must be unset in staging")
    return Check("configuration", "PASS", "APP_ENV=staging; startup checks pass")


def check_database(engine) -> list[Check]:
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    url = make_url(engine.url)
    shown = url.render_as_string(hide_password=True)
    try:
        with engine.connect() as connection:
            if connection.dialect.name != "postgresql":
                return [Check("database", "WARN", f"connected to {connection.dialect.name}, not PostgreSQL ({shown})")]
            version = connection.execute(text("show server_version")).scalar()
            tls = connection.execute(text("select ssl from pg_stat_ssl where pid = pg_backend_pid()")).scalar()
    except Exception as exc:  # report the class only: driver messages can echo connection details
        return [Check("database", "FAIL", f"cannot connect to {shown}: {type(exc).__name__}")]
    mode = {6543: "Supabase transaction pooler", 5432: "session pooler or direct"}.get(url.port or 5432, f"port {url.port}")
    checks = [Check("database", "PASS", f"PostgreSQL {version} at {url.host} ({mode})")]
    checks.append(Check("database_tls", "PASS" if tls else "FAIL",
                        "this connection is encrypted" if tls else "this connection is NOT encrypted (add sslmode=require)"))
    return checks


def check_migrations(engine) -> Check:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    head = ScriptDirectory.from_config(config).get_current_head()
    try:
        with engine.connect() as connection:
            current = connection.execute(text("select version_num from alembic_version")).scalar()
    except Exception as exc:
        return Check("migrations", "FAIL", f"no alembic_version table ({type(exc).__name__}); run the migrations")
    if current == head:
        return Check("migrations", "PASS", f"at head ({head})")
    return Check("migrations", "FAIL", f"database at {current}, code expects {head}")


def check_data_api_grants(engine) -> Check:
    from src.backend.app.infrastructure.database.data_api import exposure_findings
    try:
        with engine.connect() as connection:
            if connection.dialect.name != "postgresql":
                return Check("data_api_grants", "SKIP", "not PostgreSQL")
            findings = exposure_findings(connection)
    except Exception as exc:
        return Check("data_api_grants", "FAIL", f"could not inspect privileges ({type(exc).__name__})")
    if not findings["applicable"]:
        return Check("data_api_grants", "SKIP", "no Supabase client roles in this database (not a Supabase project)")
    if not findings["exposed"]:
        return Check("data_api_grants", "PASS", f"roles {', '.join(findings['roles'])} hold no privilege; every table has RLS")
    parts = []
    if findings["table_privileges"]:
        parts.append(f"{len({row['object'] for row in findings['table_privileges']})} tables granted to client roles")
    if findings["sequence_privileges"] or findings["function_privileges"]:
        parts.append("sequences or functions granted to client roles")
    if findings["tables_without_rls"]:
        parts.append(f"RLS off on {', '.join(findings['tables_without_rls'][:5])}"
                     f"{' ...' if len(findings['tables_without_rls']) > 5 else ''}")
    return Check("data_api_grants", "FAIL", "; ".join(parts) + " (run the migrations; see data_api.py)")


def check_data_api_http(env: Mapping[str, str], http: Http) -> Check:
    url, key = _supabase(env)
    if not url or not key:
        return Check("data_api_http", "SKIP", "SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY not set")
    try:
        result = http("GET", f"{url}/rest/v1/{PROBE_TABLE}?select=id&limit=1",
                      {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"})
    except (URLError, TimeoutError, OSError) as exc:
        return Check("data_api_http", "FAIL", f"Supabase REST endpoint unreachable ({type(exc).__name__})")
    if result.status == 200:
        try:
            rows = json.loads(result.body or "[]")
        except json.JSONDecodeError:
            rows = None
        if rows:
            return Check("data_api_http", "FAIL", f"the publishable key can READ {PROBE_TABLE} through the Data API")
        return Check("data_api_http", "WARN", f"Data API answers for {PROBE_TABLE} (no rows visible); "
                                              "switch the Data API off in the Supabase dashboard")
    return Check("data_api_http", "PASS", f"{PROBE_TABLE} not readable with the publishable key (HTTP {result.status})")


def check_auth_settings(env: Mapping[str, str], http: Http) -> Check:
    url, key = _supabase(env)
    if not url or not key:
        return Check("auth_settings", "SKIP", "SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY not set")
    try:
        result = http("GET", f"{url}/auth/v1/settings", {"apikey": key})
    except (URLError, TimeoutError, OSError) as exc:
        return Check("auth_settings", "FAIL", f"Supabase Auth unreachable ({type(exc).__name__})")
    if result.status != 200:
        return Check("auth_settings", "FAIL", f"Supabase Auth settings returned HTTP {result.status} (check the key)")
    try:
        settings = json.loads(result.body)
    except json.JSONDecodeError:
        return Check("auth_settings", "FAIL", "Supabase Auth settings were not JSON")
    email = bool((settings.get("external") or {}).get("email"))
    signup_open = not settings.get("disable_signup", False)
    autoconfirm = bool(settings.get("mailer_autoconfirm"))
    if not email:
        return Check("auth_settings", "FAIL", "email sign-in is disabled; KoroFarm signs in with email and password")
    notes = [f"email sign-in on; public sign-up {'OPEN' if signup_open else 'closed'}"]
    if autoconfirm:
        notes.append("email confirmation OFF")
    status = "WARN" if signup_open or autoconfirm else "PASS"
    return Check("auth_settings", status, "; ".join(notes))


def check_api(api_url: str, frontend_origin: str | None, http: Http) -> list[Check]:
    api_url = api_url.rstrip("/")
    checks: list[Check] = []
    try:
        health = http("GET", f"{api_url}/health")
        checks.append(Check("api_health", "PASS" if health.status == 200 else "FAIL", f"/health HTTP {health.status}"))
        worker = http("GET", f"{api_url}/health/worker")
        try:
            state = json.loads(worker.body or "{}")
        except json.JSONDecodeError:
            state = {}
        detail = f"/health/worker HTTP {worker.status} status={state.get('status')} worker={state.get('worker')}"
        if state.get("reasons"):
            detail += f" reasons={','.join(state['reasons'])}"
        checks.append(Check("worker_health", "PASS" if worker.status == 200 else "FAIL", detail))
        anonymous = http("GET", f"{api_url}/me")
        checks.append(Check("api_auth", "PASS" if anonymous.status == 401 else "FAIL",
                            f"/me without a token: HTTP {anonymous.status} (expected 401)"))
        if frontend_origin:
            origin = frontend_origin.rstrip("/")
            preflight = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}
            allowed = http("OPTIONS", f"{api_url}/me", {"Origin": origin, **preflight})
            other = http("OPTIONS", f"{api_url}/me", {"Origin": UNRELATED_ORIGIN, **preflight})
            ok = allowed.headers.get("access-control-allow-origin") == origin
            leak = other.headers.get("access-control-allow-origin") in (UNRELATED_ORIGIN, "*")
            checks.append(Check("cors", "PASS" if ok and not leak else "FAIL",
                                f"{origin} {'allowed' if ok else 'NOT allowed'}; unrelated origin "
                                f"{'ALLOWED' if leak else 'refused'}"))
        else:
            checks.append(Check("cors", "SKIP", "pass --frontend-origin to check CORS"))
    except (URLError, TimeoutError, OSError) as exc:
        checks.append(Check("api_health", "FAIL", f"API unreachable at {api_url} ({type(exc).__name__})"))
    return checks


def check_model_provider(env: Mapping[str, str]) -> Check:
    from src.backend.app.agents.infrastructure.model import model_enabled
    provider = env.get("AGENT_MODEL_PROVIDER", "").strip().lower()
    if provider in ("", "none"):
        return Check("model_provider", "PASS", "none configured; recovery decisions are deterministic")
    if model_enabled(env):
        return Check("model_provider", "WARN", f"{provider} enabled under approval "
                                               f"{env.get('AGENT_MODEL_STAGING_APPROVAL', '').strip() or '(development)'}")
    return Check("model_provider", "PASS", f"{provider} configured but not permitted here; deterministic decisions")


def run(env: Mapping[str, str], api_url: str | None = None, frontend_origin: str | None = None,
        http: Http = http_request, engine=None) -> list[Check]:
    checks = [check_configuration(env)]
    if engine is None and env.get("DATABASE_URL"):
        from src.backend.app.infrastructure.database.session import create_engine_from_url
        engine = create_engine_from_url(env["DATABASE_URL"])
    if engine is None:
        checks.append(Check("database", "FAIL", "DATABASE_URL not set"))
    else:
        database = check_database(engine)
        checks += database
        if database[0].status == "PASS":
            checks += [check_migrations(engine), check_data_api_grants(engine)]
    checks += [check_data_api_http(env, http), check_auth_settings(env, http)]
    checks += check_api(api_url, frontend_origin, http) if api_url else [Check("api_health", "SKIP", "pass --api-url")]
    checks.append(check_model_provider(env))
    return checks


def main(argv=None, env=None, http: Http = http_request, engine=None) -> int:
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description="Check a staging deployment without revealing credentials")
    parser.add_argument("--api-url")
    parser.add_argument("--frontend-origin")
    parser.add_argument("--json", type=Path, help="also write the results to this file")
    args = parser.parse_args(argv)
    if env.get("APP_ENV", "").strip().lower() == "production":
        print("refusing to run against production from this tool", file=sys.stderr)
        return 2
    checks = run(env, args.api_url, args.frontend_origin, http, engine)
    for check in checks:
        print(check.line())
    failed = [check for check in checks if check.status == "FAIL"]
    print(f"\n{len(failed)} failed, {sum(c.status == 'WARN' for c in checks)} warnings, "
          f"{sum(c.status == 'PASS' for c in checks)} passed, {sum(c.status == 'SKIP' for c in checks)} skipped")
    if args.json:
        args.json.write_text(json.dumps([vars(check) for check in checks], indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
