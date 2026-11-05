import ipaddress
import os
from collections.abc import Mapping
from urllib.parse import parse_qs, urlparse

# APP_ENV must be set explicitly to one of these; a missing or unrecognized value stops startup.
# staging and production both receive every production safeguard.
RECOGNIZED_ENVIRONMENTS = ("development", "test", "staging", "production")
NON_PRODUCTION_ENVIRONMENTS = frozenset({"test", "development"})
_LOCAL_SUFFIXES = (".local", ".localhost", ".test", ".internal", ".lan")
# The built-in development database credentials (infrastructure/database/session.py, alembic.ini).
DEVELOPMENT_DATABASE_CREDENTIALS = ("korofarm", "korofarm")
TLS_SSLMODES = frozenset({"require", "verify-ca", "verify-full"})
# How the API decides a bearer token's session is still active (core/auth.py). "database": verify the token locally
# against the project's signing keys, then require its auth.sessions row, which Supabase deletes on sign-out.
# "remote": ask Supabase Auth (GET /auth/v1/user); development and test only (the E2E auth stand-in).
SESSION_VERIFICATION_MODES = ("database", "remote")


class UnsafeConfigurationError(RuntimeError):
    """Raised at startup when configuration could weaken authentication."""


def environment(env: Mapping[str, str] | None = None) -> str:
    """The normalised APP_ENV value, or "" when it is not set."""
    env = os.environ if env is None else env
    return env.get("APP_ENV", "").strip().lower()


def is_production(env: Mapping[str, str] | None = None) -> bool:
    # Fail closed: anything that is not explicitly development or test is treated as production.
    return environment(env) not in NON_PRODUCTION_ENVIRONMENTS


def session_verification(env: Mapping[str, str] | None = None) -> str:
    """AUTH_SESSION_VERIFICATION, defaulting to "database" in staging and production and "remote" elsewhere. Anything
    unrecognized is treated as "database" (startup refuses it anyway)."""
    env = os.environ if env is None else env
    value = env.get("AUTH_SESSION_VERIFICATION", "").strip().lower()
    if not value:
        return "database" if is_production(env) else "remote"
    return value if value in SESSION_VERIFICATION_MODES else "database"


def cors_origins() -> list[str]:
    value = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


def _bypass_requested(env: Mapping[str, str]) -> bool:
    return env.get("ALLOW_INSECURE_DEMO_AUTH", "false").strip().lower() == "true"


def demo_auth_bypass_enabled(env: Mapping[str, str] | None = None) -> bool:
    """The insecure auth bypass works only in automated tests (APP_ENV=test)."""
    env = os.environ if env is None else env
    return _bypass_requested(env) and environment(env) == "test"


def _is_private_or_local(host: str) -> bool:
    host = host.strip("[]").lower()
    if host in {"localhost", "0.0.0.0"} or host.endswith(_LOCAL_SUFFIXES):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local or address.is_unspecified or address.is_reserved


def marketplace_orders_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Marketplace orders are outside R1 scope (P10): off unless MARKETPLACE_ORDERS_ENABLED=true, never in production."""
    env = os.environ if env is None else env
    return env.get("MARKETPLACE_ORDERS_ENABLED", "").strip().lower() == "true" and environment(env) != "production"


def validate_runtime_configuration(env: Mapping[str, str] | None = None) -> None:
    """Refuse to start with configuration that could let anyone mint or skip identities.

    * APP_ENV must be one of RECOGNIZED_ENVIRONMENTS; missing or unrecognized values are refused.
    * ALLOW_INSECURE_DEMO_AUTH=true is refused outright unless APP_ENV=test (it is never silently ignored).
    * In staging and production the identity provider must be an https URL on a public
      host, and its publishable key must be set. A loopback or private URL could only be a stand-in such
      as the E2E auth stub (src/frontend/e2e/r1/support/auth-stub.mjs), which must never back production.
    * AGENT_MODEL_PROVIDER is refused when APP_ENV=production: production model access stays disabled until provider,
      data-handling, security and evaluation requirements are approved (R1 WP3, decision 3).
    * AGENT_MODEL_PROVIDER in staging needs AGENT_MODEL_STAGING_APPROVAL, the reference of the product owner's recorded
      approval to send that environment's data to the provider. Without it the process refuses to start.
    * AUTH_SESSION_VERIFICATION must be database or remote; remote is refused in staging and production, where every
      request's session is checked against auth.sessions (core/auth.py).
    * In staging and production DATABASE_URL must be set explicitly (no development default), must not use the built-in
      development credentials, and must require TLS (sslmode=require, verify-ca or verify-full) unless the database
      host is local, private or a single-label service name on the deployment's own network.
    """
    env = os.environ if env is None else env
    app_env = environment(env)
    allowed = ", ".join(RECOGNIZED_ENVIRONMENTS)
    if not app_env:
        raise UnsafeConfigurationError(f"APP_ENV must be set to one of: {allowed}; refusing to start")
    if app_env not in RECOGNIZED_ENVIRONMENTS:
        raise UnsafeConfigurationError(f"APP_ENV={app_env!r} is not recognized (expected one of: {allowed}); refusing to start")
    if _bypass_requested(env) and app_env != "test":
        raise UnsafeConfigurationError(
            f"ALLOW_INSECURE_DEMO_AUTH=true is only permitted when APP_ENV=test (APP_ENV is {app_env!r}); refusing to start")
    if app_env == "production" and env.get("AGENT_MODEL_PROVIDER", "").strip().lower() not in ("", "none"):
        raise UnsafeConfigurationError("AGENT_MODEL_PROVIDER is not permitted in production until model use is approved; refusing to start")
    if app_env == "staging" and env.get("AGENT_MODEL_PROVIDER", "").strip().lower() not in ("", "none")             and not env.get("AGENT_MODEL_STAGING_APPROVAL", "").strip():
        raise UnsafeConfigurationError(
            "AGENT_MODEL_PROVIDER in staging requires AGENT_MODEL_STAGING_APPROVAL (the recorded approval reference for "
            "sending staging data to the provider); refusing to start")
    mode = env.get("AUTH_SESSION_VERIFICATION", "").strip().lower()
    if mode and mode not in SESSION_VERIFICATION_MODES:
        raise UnsafeConfigurationError(
            f"AUTH_SESSION_VERIFICATION={mode!r} is not recognized (expected database or remote); refusing to start")
    if not is_production(env):
        return
    if mode == "remote":
        raise UnsafeConfigurationError(
            "AUTH_SESSION_VERIFICATION=remote is not permitted in staging or production: signed-out sessions must be "
            "refused through auth.sessions; refusing to start")
    _validate_database_url(env.get("DATABASE_URL", "").strip())
    url = env.get("SUPABASE_URL") or env.get("NEXT_PUBLIC_SUPABASE_URL")
    key = env.get("SUPABASE_PUBLISHABLE_KEY") or env.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        raise UnsafeConfigurationError("production requires SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY; refusing to start")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise UnsafeConfigurationError(f"production SUPABASE_URL must be an https URL (got {url!r}); refusing to start")
    if _is_private_or_local(parsed.hostname):
        raise UnsafeConfigurationError(
            f"production SUPABASE_URL points at a local or private host ({parsed.hostname}); refusing to start")


def _validate_database_url(value: str) -> None:
    """Staging and production: an explicit, TLS-protected database URL without the development credentials."""
    if not value:
        raise UnsafeConfigurationError("production requires DATABASE_URL to be set explicitly; refusing to start")
    parsed = urlparse(value)
    if not parsed.scheme.startswith("postgresql") or not parsed.hostname:
        raise UnsafeConfigurationError("production DATABASE_URL must be a postgresql URL with a host; refusing to start")
    if (parsed.username, parsed.password) == DEVELOPMENT_DATABASE_CREDENTIALS:
        raise UnsafeConfigurationError("production DATABASE_URL uses the development credentials; refusing to start")
    host = parsed.hostname
    on_deployment_network = "." not in host.strip("[]") and ":" not in host or _is_private_or_local(host)
    sslmode = (parse_qs(parsed.query).get("sslmode") or [""])[0].lower()
    if not on_deployment_network and sslmode not in TLS_SSLMODES:
        raise UnsafeConfigurationError(
            "production DATABASE_URL must require TLS (add sslmode=require or verify-full) for a remote database host; "
            "refusing to start")


def model_staging_approval(env: Mapping[str, str] | None = None) -> str:
    """The recorded approval reference that lets a staging deployment call a model provider ("" when absent)."""
    env = os.environ if env is None else env
    return env.get("AGENT_MODEL_STAGING_APPROVAL", "").strip()
