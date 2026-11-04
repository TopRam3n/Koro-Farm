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
PUBLIC = {"SUPABASE_URL": "https://abcdefgh.supabase.co", "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_example",
          "DATABASE_URL": "postgresql+psycopg://app_user:placeholder@aws-0-region.pooler.supabase.com:5432/postgres?sslmode=require"}


@pytest.mark.parametrize("app_env", [None, "", "development", "demo", "production", "prod", "staging", "TEST "])
def test_bypass_request_outside_test_stops_startup(app_env) -> None:
    env = {"ALLOW_INSECURE_DEMO_AUTH": "true", **PUBLIC}
    if app_env is not None:
        env["APP_ENV"] = app_env
    if (app_env or "").strip().lower() == "test":
        validate_runtime_configuration(env)  # "TEST " normalises to test and is allowed
        return
    with pytest.raises(UnsafeConfigurationError):
        validate_runtime_configuration(env)
    assert demo_auth_bypass_enabled(env) is False


@pytest.mark.parametrize("app_env", [None, "", "   ", "demo", "prod", "dev", "local", "qa", "productoin"])
def test_missing_or_unrecognized_app_env_stops_startup(app_env) -> None:
    env = dict(PUBLIC)
    if app_env is not None:
        env["APP_ENV"] = app_env
    with pytest.raises(UnsafeConfigurationError, match="APP_ENV"):
        validate_runtime_configuration(env)


@pytest.mark.parametrize("app_env", ["development", "test", "staging", "production", "Production"])
def test_each_recognized_environment_starts_with_safe_settings(app_env) -> None:
    validate_runtime_configuration({"APP_ENV": app_env, **PUBLIC})


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


@pytest.mark.parametrize("database_url", [
    None, "",
    "postgresql+psycopg://korofarm:korofarm@db.example.com:5432/korofarm?sslmode=require",  # development credentials
    "postgresql+psycopg://app:placeholder@aws-0-region.pooler.supabase.com:5432/postgres",  # remote without TLS
    "postgresql+psycopg://app:placeholder@db.abcdefgh.supabase.co:5432/postgres?sslmode=prefer",
    "postgresql+psycopg://app:placeholder@db.abcdefgh.supabase.co:5432/postgres?sslmode=disable",
    "mysql://app:placeholder@db.example.com/korofarm?sslmode=require",
    "not a url",
])
@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_staging_and_production_refuse_a_missing_default_or_unencrypted_database(database_url, app_env) -> None:
    env = {"APP_ENV": app_env, **PUBLIC}
    env.pop("DATABASE_URL")
    if database_url is not None:
        env["DATABASE_URL"] = database_url
    with pytest.raises(UnsafeConfigurationError, match="DATABASE_URL"):
        validate_runtime_configuration(env)


@pytest.mark.parametrize("database_url", [
    "postgresql+psycopg://app:placeholder@db.abcdefgh.supabase.co:5432/postgres?sslmode=verify-full",
    "postgresql+psycopg://app:placeholder@aws-0-region.pooler.supabase.com:6543/postgres?sslmode=require",
    "postgresql+psycopg://app:placeholder@db:5432/korofarm",          # a service on the deployment's own network
    "postgresql+psycopg://app:placeholder@10.0.0.7:5432/korofarm",    # private address
])
def test_staging_accepts_an_explicit_tls_or_private_database(database_url) -> None:
    validate_runtime_configuration({"APP_ENV": "staging", **PUBLIC, "DATABASE_URL": database_url})


def test_development_and_test_keep_the_local_database_default() -> None:
    validate_runtime_configuration({"APP_ENV": "development"})
    validate_runtime_configuration({"APP_ENV": "test"})


def test_a_staging_model_provider_needs_a_recorded_data_approval() -> None:
    staged = {"APP_ENV": "staging", **PUBLIC, "AGENT_MODEL_PROVIDER": "minimax"}
    with pytest.raises(UnsafeConfigurationError, match="AGENT_MODEL_STAGING_APPROVAL"):
        validate_runtime_configuration(staged)
    with pytest.raises(UnsafeConfigurationError, match="AGENT_MODEL_STAGING_APPROVAL"):
        validate_runtime_configuration({**staged, "AGENT_MODEL_STAGING_APPROVAL": "   "})
    validate_runtime_configuration({**staged, "AGENT_MODEL_STAGING_APPROVAL": "PO-2026-11-03-synthetic-only"})
    validate_runtime_configuration({"APP_ENV": "staging", **PUBLIC, "AGENT_MODEL_PROVIDER": "none"})
    # Development keeps working without an approval: it holds synthetic data only.
    validate_runtime_configuration({"APP_ENV": "development", "AGENT_MODEL_PROVIDER": "minimax"})


@pytest.mark.parametrize("app_env", ["test", "development"])
def test_local_provider_is_allowed_only_outside_production(app_env) -> None:
    validate_runtime_configuration({"APP_ENV": app_env, "SUPABASE_URL": "http://127.0.0.1:54999",
                                    "SUPABASE_PUBLISHABLE_KEY": "e2e-test-key"})


def _start_app(extra_env: dict) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items()
           if key not in {"APP_ENV", "ALLOW_INSECURE_DEMO_AUTH", "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY",
                          "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "DATABASE_URL",
                          "AGENT_MODEL_PROVIDER", "AGENT_MODEL_STAGING_APPROVAL"}}
    env.update(extra_env)
    return subprocess.run([sys.executable, "-c", "import src.backend.app.main"], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("extra", [
    {},
    {"APP_ENV": ""},
    {"APP_ENV": "demo"},
    {"APP_ENV": "prod", **PUBLIC},
    {"APP_ENV": "staging", "SUPABASE_URL": "http://127.0.0.1:54999", "SUPABASE_PUBLISHABLE_KEY": "e2e-test-key"},
    {"APP_ENV": "production", "SUPABASE_URL": "http://127.0.0.1:54999", "SUPABASE_PUBLISHABLE_KEY": "e2e-test-key"},
    {"APP_ENV": "production", "SUPABASE_URL": "https://127.0.0.1:54999", "SUPABASE_PUBLISHABLE_KEY": "e2e-test-key"},
    {"APP_ENV": "demo", "ALLOW_INSECURE_DEMO_AUTH": "true", **PUBLIC},
    {"ALLOW_INSECURE_DEMO_AUTH": "true"},
    {"APP_ENV": "staging", **{k: v for k, v in PUBLIC.items() if k != "DATABASE_URL"}},
    {"APP_ENV": "staging", **PUBLIC, "AGENT_MODEL_PROVIDER": "nebius"},
])
def test_the_real_application_refuses_to_start_with_unsafe_configuration(extra) -> None:
    result = _start_app(extra)
    assert result.returncode != 0
    assert "UnsafeConfigurationError" in result.stderr


@pytest.mark.parametrize("extra", [
    {"APP_ENV": "production", **PUBLIC},
    {"APP_ENV": "staging", **PUBLIC},
    {"APP_ENV": "development"},
    {"APP_ENV": "test"},
])
def test_the_real_application_starts_with_safe_configuration(extra) -> None:
    result = _start_app(extra)
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


@pytest.mark.parametrize("app_env, database, allowed", [
    ("test", "korofarm_ci_test", True), ("development", "korofarm_demo", True),
    ("demo", "korofarm_demo", False), ("production", "korofarm_test", False), ("", "korofarm_test", False),
    ("test", "korofarm", False),
])
def test_destructive_demo_reset_requires_a_safe_environment_and_database(monkeypatch, app_env, database, allowed) -> None:
    from src.backend.scripts.reset_demo import assert_safe
    monkeypatch.setenv("APP_ENV", app_env)
    url = f"postgresql+psycopg://u:p@localhost:5432/{database}"
    if allowed:
        assert_safe(url)
    else:
        with pytest.raises(SystemExit):
            assert_safe(url)
