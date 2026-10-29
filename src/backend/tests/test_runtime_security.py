"""Authentication fail-closed guarantees.

The insecure bypass works only under APP_ENV=test, and any other request for it stops the process.
In production the identity provider must be a public https host, so a local stand-in such as the
E2E auth stub (src/frontend/e2e/r1/support/auth-stub.mjs) cannot back a production API.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.backend.app.core.config import UnsafeConfigurationError, demo_auth_bypass_enabled, validate_runtime_configuration

REPO = Path(__file__).resolve().parents[3]
PUBLIC = {"SUPABASE_URL": "https://abcdefgh.supabase.co", "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_example"}


@pytest.mark.parametrize("app_env", [None, "development", "demo", "production", "prod", "staging", "TEST "])
def test_bypass_request_outside_test_stops_startup(app_env) -> None:
    env = {"ALLOW_INSECURE_DEMO_AUTH": "true", **PUBLIC}
    if app_env is not None:
        env["APP_ENV"] = app_env
    if (app_env or "").strip().lower() == "test":
        validate_runtime_configuration(env)  # "TEST " normalises to test and is allowed
        return
    with pytest.raises(UnsafeConfigurationError, match="only permitted when APP_ENV=test"):
        validate_runtime_configuration(env)
    assert demo_auth_bypass_enabled(env) is False


def test_bypass_is_honoured_only_in_test() -> None:
    assert demo_auth_bypass_enabled({"APP_ENV": "test", "ALLOW_INSECURE_DEMO_AUTH": "true"}) is True
    assert demo_auth_bypass_enabled({"APP_ENV": "demo", "ALLOW_INSECURE_DEMO_AUTH": "true"}) is False
    assert demo_auth_bypass_enabled({"APP_ENV": "test"}) is False


@pytest.mark.parametrize("url", [
    None, "http://abcdefgh.supabase.co", "https://localhost:54999", "https://127.0.0.1:54999", "http://127.0.0.1:54999",
    "https://[::1]:54999", "https://10.0.0.5", "https://192.168.1.20", "https://172.16.4.1", "https://169.254.1.1",
    "https://auth.local", "https://stub.test", "https://0.0.0.0", "not a url",
])
@pytest.mark.parametrize("app_env", ["production", "staging", "demo"])
def test_production_refuses_local_private_or_insecure_identity_provider(url, app_env) -> None:
    env = {"APP_ENV": app_env, "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_example"}
    if url is not None:
        env["SUPABASE_URL"] = url
    with pytest.raises(UnsafeConfigurationError):
        validate_runtime_configuration(env)


def test_production_requires_the_publishable_key() -> None:
    with pytest.raises(UnsafeConfigurationError):
        validate_runtime_configuration({"APP_ENV": "production", "SUPABASE_URL": PUBLIC["SUPABASE_URL"]})


def test_production_accepts_a_public_https_provider() -> None:
    validate_runtime_configuration({"APP_ENV": "production", **PUBLIC})


@pytest.mark.parametrize("app_env", ["test", "development"])
def test_local_provider_is_allowed_only_outside_production(app_env) -> None:
    validate_runtime_configuration({"APP_ENV": app_env, "SUPABASE_URL": "http://127.0.0.1:54999",
                                    "SUPABASE_PUBLISHABLE_KEY": "e2e-test-key"})


def _start_app(extra_env: dict) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items()
           if key not in {"APP_ENV", "ALLOW_INSECURE_DEMO_AUTH", "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY",
                          "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"}}
    env.update(extra_env)
    return subprocess.run([sys.executable, "-c", "import src.backend.app.main"], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("extra", [
    {"APP_ENV": "production", "SUPABASE_URL": "http://127.0.0.1:54999", "SUPABASE_PUBLISHABLE_KEY": "e2e-test-key"},
    {"APP_ENV": "production", "SUPABASE_URL": "https://127.0.0.1:54999", "SUPABASE_PUBLISHABLE_KEY": "e2e-test-key"},
    {"APP_ENV": "demo", "ALLOW_INSECURE_DEMO_AUTH": "true", **PUBLIC},
    {"ALLOW_INSECURE_DEMO_AUTH": "true"},
])
def test_the_real_application_refuses_to_start_with_unsafe_configuration(extra) -> None:
    result = _start_app(extra)
    assert result.returncode != 0
    assert "UnsafeConfigurationError" in result.stderr


def test_the_real_application_starts_with_safe_production_configuration() -> None:
    result = _start_app({"APP_ENV": "production", **PUBLIC})
    assert result.returncode == 0, result.stderr


def test_even_in_test_the_bypass_identity_reaches_no_organization_data(monkeypatch, session_factory) -> None:
    """With the bypass on (APP_ENV=test) the fixed demo identity is not a user with a membership."""
    from src.backend.app.main import app
    from src.backend.app.main_dependencies import get_session

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_INSECURE_DEMO_AUTH", "true")

    def override():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    saved = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override
    try:
        with TestClient(app) as client:
            for path in ("/requirements", "/buyers", "/production-lots", "/activity", "/me", "/me/organizations"):
                assert client.get(path).status_code in {401, 403}, path
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)
