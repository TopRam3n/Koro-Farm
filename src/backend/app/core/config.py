import ipaddress
import os
from collections.abc import Mapping
from urllib.parse import urlparse

# APP_ENV must be set explicitly to one of these; a missing or unrecognized value stops startup.
# staging and production both receive every production safeguard.
RECOGNIZED_ENVIRONMENTS = ("development", "test", "staging", "production")
NON_PRODUCTION_ENVIRONMENTS = frozenset({"test", "development"})
_LOCAL_SUFFIXES = (".local", ".localhost", ".test", ".internal", ".lan")


class UnsafeConfigurationError(RuntimeError):
    """Raised at startup when configuration could weaken authentication."""


def environment(env: Mapping[str, str] | None = None) -> str:
    """The normalised APP_ENV value, or "" when it is not set."""
    env = os.environ if env is None else env
    return env.get("APP_ENV", "").strip().lower()


def is_production(env: Mapping[str, str] | None = None) -> bool:
    # Fail closed: anything that is not explicitly development or test is treated as production.
    return environment(env) not in NON_PRODUCTION_ENVIRONMENTS


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


def validate_runtime_configuration(env: Mapping[str, str] | None = None) -> None:
    """Refuse to start with configuration that could let anyone mint or skip identities.

    * APP_ENV must be one of RECOGNIZED_ENVIRONMENTS; missing or unrecognized values are refused.
    * ALLOW_INSECURE_DEMO_AUTH=true is refused outright unless APP_ENV=test (it is never silently ignored).
    * In staging and production the identity provider must be an https URL on a public
      host, and its publishable key must be set. A loopback or private URL could only be a stand-in such
      as the E2E auth stub (src/frontend/e2e/r1/support/auth-stub.mjs), which must never back production.
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
    if not is_production(env):
        return
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
