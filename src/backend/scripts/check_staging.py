"""Check a staging deployment end to end without revealing credentials. Read-only: no row is written anywhere; the
only statements beyond SELECT create probe objects inside a savepoint that is always rolled back (data_api_grants).

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
  data_api_grants Supabase client roles hold no effective privilege (direct, through PUBLIC or role membership,
                  table or column) on KoroFarm's tables, sequences or functions; no default privilege of any role
                  owning objects in public would expose new objects, and a rolled-back probe confirms it; every
                  table has RLS (0026, 0027). FAILs if new objects cannot be probed as the connected role.
  auth_session_store the API's connection can run its active-session query on auth.sessions and auth.users
  data_api_http   the Data API is switched off: PASS only on Supabase's disabled signature. The publishable key goes
                  only in `apikey`; a control request first proves Supabase accepts it, so an authentication failure
                  is never mistaken for protection. A permission-denied answer still FAILs (the Data API is on).
  auth_settings   Supabase Auth answers; email sign-in enabled; whether public sign-up is open
  auth_signing_keys the project publishes an ES256/RS256 signing key the API can verify tokens against
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
DISABLED_SIGNATURE = "pg_pgrst_no_exposed_schemas"
OBJECT_KINDS = {"r": "tables", "S": "sequences", "f": "functions"}


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
    future = findings["future_objects"]
    parts = []
    if findings["table_privileges"]:
        parts.append(f"{len({row['object'] for row in findings['table_privileges']})} tables granted to client roles")
    if findings["sequence_privileges"]:
        parts.append(f"{len({row['object'] for row in findings['sequence_privileges']})} sequences granted to client roles")
    if findings["function_privileges"]:
        public = any(row["via_public"] for row in findings["function_privileges"])
        parts.append(f"{len({row['object'] for row in findings['function_privileges']})} functions executable by client "
                     f"roles{' (through PUBLIC)' if public else ''}")
    if findings["tables_without_rls"]:
        parts.append(f"RLS off on {', '.join(findings['tables_without_rls'][:5])}"
                     f"{' ...' if len(findings['tables_without_rls']) > 5 else ''}")
    if findings["default_privileges"]:
        entries = sorted({f"{row['owner']}:{OBJECT_KINDS.get(row['object_type'], row['object_type'])}->{row['grantee']}"
                          for row in findings["default_privileges"]})
        parts.append(f"default privileges would expose new objects ({', '.join(entries[:4])}"
                     f"{' ...' if len(entries) > 4 else ''})")
    if future["exposed"]:
        parts.append("a newly created " + ", ".join(sorted({f"{row['object']} ({row['role']})" for row in future["exposed"]}))
                     + " would be reachable")
    if parts:
        return Check("data_api_grants", "FAIL", "; ".join(parts) + " (run the migrations or scripts/data_api_lockdown.py; "
                                                                   "objects owned by another role need that role)")
    if not future["ran"]:
        return Check("data_api_grants", "FAIL", f"existing objects are locked down, but objects created later could not be "
                                                f"verified ({future.get('reason')}); run this check as the role that runs "
                                                f"the migrations")
    detail = (f"roles {', '.join(findings['roles'])} hold no privilege, now or on new objects (probe as "
              f"{future['role']}); every table has RLS")
    if findings["objects_not_owned"]:
        detail += f"; {len(findings['objects_not_owned'])} objects in public owned by other roles (none reachable)"
    return Check("data_api_grants", "PASS", detail)


def _postgrest_error(body: str) -> dict:
    try:
        parsed = json.loads(body or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def classify_data_api_response(result: HttpResult) -> tuple[str, str]:
    """What a GET /rest/v1/<table> answer proves. Returns (verdict, detail); verdict is one of disabled, readable,
    reachable, permission_denied, not_served, auth_failure, unrecognized. Only `disabled` is acceptable for KoroFarm.

    * Supabase does not stop PostgREST when the Data API is switched off: it exposes only the placeholder schema
      pg_pgrst_no_exposed_schemas, and requests fail naming it. That name is the signature looked for.
    * PostgREST reports a missing privilege as SQLSTATE 42501 with HTTP 401 for the anonymous role, so a 401 alone
      says nothing: it is also what an invalid or wrongly sent key gets from the gateway (PGRST301/302, "Invalid API
      key"). A status code is therefore never taken as proof on its own."""
    error = _postgrest_error(result.body)
    code = str(error.get("code") or "")
    message = " ".join(str(error.get(field) or "") for field in ("message", "hint", "details", "msg", "error"))
    summary = f"HTTP {result.status}{f' {code}' if code else ''}"
    if DISABLED_SIGNATURE in result.body:
        return "disabled", f"{summary}: Data API switched off (only {DISABLED_SIGNATURE} is exposed)"
    if result.status == 200:
        try:
            rows = json.loads(result.body or "[]")
        except json.JSONDecodeError:
            rows = None
        if rows:
            return "readable", f"{summary}: the publishable key can READ {PROBE_TABLE} through the Data API"
        return "reachable", f"{summary}: the Data API serves {PROBE_TABLE} to the publishable key (no rows visible)"
    if code == "42501":
        return "permission_denied", (f"{summary}: the Data API is ON; the database refused it (permission denied), so "
                                     "the grants hold, but the Data API must be switched off")
    if code in ("PGRST205", "PGRST106", "42P01", "PGRST002"):
        return "not_served", f"{summary}: the Data API is ON but does not serve {PROBE_TABLE}; switch the Data API off"
    lowered = message.lower()
    if code.startswith("PGRST3") or (result.status in (401, 403) and ("api key" in lowered or "jwt" in lowered or not code)):
        return "auth_failure", (f"{summary}: refused before reaching the database (authentication failure); this "
                                "proves nothing about table protection")
    return "unrecognized", f"{summary}: unrecognized answer ({message.strip()[:120] or 'no error body'})"


def check_data_api_http(env: Mapping[str, str], http: Http) -> Check:
    """The publishable key is sent only as `apikey`, the way a browser using it as the anonymous role would, never as
    a bearer token (it is not a JWT). A control request to Supabase Auth first proves the key itself is accepted, so a
    rejected key can never be mistaken for a protected table."""
    url, key = _supabase(env)
    if not url or not key:
        return Check("data_api_http", "SKIP", "SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY not set")
    try:
        control = http("GET", f"{url}/auth/v1/settings", {"apikey": key})
        if control.status != 200:
            return Check("data_api_http", "FAIL", f"inconclusive: Supabase rejected the publishable key itself "
                                                  f"(HTTP {control.status} from Auth); fix the key and run again")
        result = http("GET", f"{url}/rest/v1/{PROBE_TABLE}?select=id&limit=1",
                      {"apikey": key, "Accept": "application/json"})
    except (URLError, TimeoutError, OSError) as exc:
        return Check("data_api_http", "FAIL", f"Supabase unreachable ({type(exc).__name__})")
    verdict, detail = classify_data_api_response(result)
    return Check("data_api_http", "PASS" if verdict == "disabled" else "FAIL", detail)


def check_auth_signing_keys(env: Mapping[str, str], http: Http) -> Check:
    """The API verifies access tokens locally against the project's published asymmetric signing keys."""
    from src.backend.app.core.auth import usable_signing_keys
    url, key = _supabase(env)
    if not url or not key:
        return Check("auth_signing_keys", "SKIP", "SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY not set")
    try:
        result = http("GET", f"{url}/auth/v1/.well-known/jwks.json", {"apikey": key})
    except (URLError, TimeoutError, OSError) as exc:
        return Check("auth_signing_keys", "FAIL", f"signing keys unreachable ({type(exc).__name__})")
    if result.status != 200:
        return Check("auth_signing_keys", "FAIL", f"signing keys returned HTTP {result.status}")
    try:
        keys = usable_signing_keys(json.loads(result.body))
    except (json.JSONDecodeError, ValueError):
        return Check("auth_signing_keys", "FAIL", "signing keys were not a JSON key set")
    if not keys:
        return Check("auth_signing_keys", "FAIL", "no ES256/RS256 signing key published: the project still signs with "
                                                  "the legacy shared secret (setup guide: rotate to an asymmetric key)")
    algorithms = sorted({item.algorithm_name for item in keys.values()})
    return Check("auth_signing_keys", "PASS", f"{len(keys)} asymmetric signing key(s) ({', '.join(algorithms)})")


def check_auth_session_store(engine) -> Check:
    """The API's connection can run the exact active-session query the API uses (auth.sessions, auth.users)."""
    from uuid import uuid4

    from src.backend.app.core.auth import ACTIVE_SESSION
    try:
        with engine.connect() as connection:
            if connection.dialect.name != "postgresql":
                return Check("auth_session_store", "SKIP", "not PostgreSQL")
            connection.execute(ACTIVE_SESSION, {"session_id": str(uuid4()), "user_id": str(uuid4())}).first()
    except Exception as exc:
        return Check("auth_session_store", "FAIL", f"the API could not read Supabase's session records "
                                                   f"({type(exc).__name__}); sign-out could not be enforced")
    return Check("auth_session_store", "PASS", "auth.sessions and auth.users readable; signed-out sessions are refused")


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
            checks += [check_migrations(engine), check_data_api_grants(engine), check_auth_session_store(engine)]
    checks += [check_data_api_http(env, http), check_auth_settings(env, http), check_auth_signing_keys(env, http)]
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
