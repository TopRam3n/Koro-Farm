"""Bearer-token authentication with immediate sign-out revocation (core/auth.py).

Token verification is tested everywhere with locally generated ES256 keys. The end-to-end cases run the real /me
route against PostgreSQL with Supabase's auth.users and auth.sessions tables simulated (only the columns the API
reads), so sign-out is the deletion of the session row, exactly what Supabase Auth does. They prove the API's
behaviour, not Supabase's: the release gate stays `npm run test:staging-auth` against the real staging project.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from src.backend.app.core import auth
from src.backend.app.core.auth import AuthUnavailable, InvalidToken, SigningKeys, verify_access_token
from src.backend.app.core.config import UnsafeConfigurationError, session_verification, validate_runtime_configuration

BASE = "https://abcdefgh.supabase.co"
APIKEY = "sb_publishable_PLACEHOLDERVALUE"
POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")


class Signer:
    """One project signing key: mints tokens and publishes the matching JWKS entry."""

    def __init__(self, kid="key-1"):
        self.kid = kid
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.jwk = {**json.loads(ECAlgorithm.to_jwk(self.private.public_key())), "kid": kid, "alg": "ES256", "use": "sig"}

    def token(self, subject, session, /, *, lifetime=3600, kid=None, **override) -> str:
        now = int(time.time())
        claims = {"iss": f"{BASE}/auth/v1", "aud": "authenticated", "role": "authenticated", "sub": str(subject),
                  "session_id": str(session), "iat": now, "exp": now + lifetime, "aal": "aal1",
                  "email": "claimed@example.test", **override}
        claims = {key: value for key, value in claims.items() if value is not None}
        return jwt.encode(claims, self.private, algorithm="ES256", headers={"kid": kid or self.kid})


def keys_for(*signers, calls=None, fail=False, clock=None) -> SigningKeys:
    def fetch(url, apikey):
        if calls is not None:
            calls.append(url)
        if fail:
            raise OSError("unreachable")
        return auth.usable_signing_keys({"keys": [signer.jwk for signer in signers]})
    return SigningKeys(fetch=fetch, clock=clock or time.monotonic)


# --- Step 1: the token itself --------------------------------------------------------------------------------------

def test_a_valid_token_yields_its_verified_claims() -> None:
    signer, sub, sid = Signer(), uuid4(), uuid4()
    claims = verify_access_token(signer.token(sub, sid), BASE, APIKEY, keys_for(signer))
    assert claims["sub"] == str(sub) and claims["session_id"] == str(sid)


@pytest.mark.parametrize("change", [
    {"lifetime": -60},                                  # expired (beyond the 10 s clock leeway)
    {"iss": "https://otherproject.supabase.co/auth/v1"},  # another project's token
    {"aud": "anon"},
    {"role": "anon"},
    {"role": "service_role"},
    {"session_id": None},                               # no session to check
    {"sub": "not-a-uuid"},
    {"is_anonymous": True},
])
def test_tokens_that_are_not_active_user_sessions_of_this_project_are_refused(change) -> None:
    signer = Signer()
    token = signer.token(uuid4(), uuid4(), **change)  # claims in `change` replace the defaults; None removes one
    with pytest.raises(InvalidToken):
        verify_access_token(token, BASE, APIKEY, keys_for(signer))


def test_forged_and_downgraded_tokens_are_refused() -> None:
    signer, impostor = Signer(), Signer()  # same key id, different private key
    with pytest.raises(InvalidToken):
        verify_access_token(impostor.token(uuid4(), uuid4()), BASE, APIKEY, keys_for(signer))
    claims = {"iss": f"{BASE}/auth/v1", "aud": "authenticated", "role": "authenticated", "sub": str(uuid4()),
              "session_id": str(uuid4()), "iat": int(time.time()), "exp": int(time.time()) + 600}
    hs256 = jwt.encode(claims, "guessable-shared-secret-of-sufficient-length", algorithm="HS256", headers={"kid": signer.kid})
    unsigned = jwt.encode(claims, None, algorithm="none", headers={"kid": signer.kid})
    for token in (hs256, unsigned, "not-a-jwt", signer.token(uuid4(), uuid4()) + "x"):
        with pytest.raises(InvalidToken):
            verify_access_token(token, BASE, APIKEY, keys_for(signer))
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # algorithm must match the published key
    with pytest.raises(InvalidToken):
        verify_access_token(jwt.encode(claims, rsa_key, algorithm="RS256", headers={"kid": signer.kid}),
                            BASE, APIKEY, keys_for(signer))


def test_signing_keys_are_cached_refetched_on_rotation_and_fail_closed() -> None:
    now = [1000.0]
    calls: list = []
    old, new = Signer("old"), Signer("new")
    keys = keys_for(old, calls=calls, clock=lambda: now[0])
    verify_access_token(old.token(uuid4(), uuid4()), BASE, APIKEY, keys)
    verify_access_token(old.token(uuid4(), uuid4()), BASE, APIKEY, keys)
    assert len(calls) == 1                                 # cached
    now[0] += auth.KEY_REFETCH_SECONDS
    with pytest.raises(InvalidToken):                      # unknown key id: one refetch, then refused
        verify_access_token(new.token(uuid4(), uuid4()), BASE, APIKEY, keys)
    with pytest.raises(InvalidToken):
        verify_access_token(new.token(uuid4(), uuid4()), BASE, APIKEY, keys)
    assert len(calls) == 2                                 # random key ids cannot force a fetch per request

    unreachable = keys_for(old, fail=True)
    with pytest.raises(AuthUnavailable):                   # no keys at all: never accept, never 401
        verify_access_token(old.token(uuid4(), uuid4()), BASE, APIKEY, unreachable)

    flaky_up = [True]
    def fetch(url, apikey):
        if not flaky_up[0]:
            raise OSError("unreachable")
        return auth.usable_signing_keys({"keys": [old.jwk]})
    flaky = SigningKeys(fetch=fetch, clock=lambda: now[0])
    verify_access_token(old.token(uuid4(), uuid4()), BASE, APIKEY, flaky)
    flaky_up[0] = False
    now[0] += auth.KEY_TTL_SECONDS + 1                     # stale but recent keys keep working during an outage
    verify_access_token(old.token(uuid4(), uuid4()), BASE, APIKEY, flaky)
    with pytest.raises(AuthUnavailable):                   # a rotated key we cannot fetch is unavailable, not invalid
        verify_access_token(new.token(uuid4(), uuid4()), BASE, APIKEY, flaky)
    now[0] += auth.KEY_MAX_STALE_SECONDS
    with pytest.raises(AuthUnavailable):
        verify_access_token(old.token(uuid4(), uuid4()), BASE, APIKEY, flaky)


def test_staging_and_production_must_check_sessions_in_the_database() -> None:
    staging = {"APP_ENV": "staging", "SUPABASE_URL": BASE, "SUPABASE_PUBLISHABLE_KEY": APIKEY,
               "DATABASE_URL": "postgresql+psycopg://app:pw@db.abcdefgh.supabase.co:5432/postgres?sslmode=require"}
    validate_runtime_configuration(staging)
    assert session_verification(staging) == "database"
    assert session_verification({"APP_ENV": "production"}) == "database"
    assert session_verification({"APP_ENV": "test"}) == "remote"
    assert session_verification({"APP_ENV": "test", "AUTH_SESSION_VERIFICATION": "bogus"}) == "database"
    for env in ({**staging, "AUTH_SESSION_VERIFICATION": "remote"}, {**staging, "APP_ENV": "production",
                                                                      "AUTH_SESSION_VERIFICATION": "remote"},
                {"APP_ENV": "development", "AUTH_SESSION_VERIFICATION": "bogus"}):
        with pytest.raises(UnsafeConfigurationError):
            validate_runtime_configuration(env)
    validate_runtime_configuration({"APP_ENV": "development", "AUTH_SESSION_VERIFICATION": "remote"})


# --- Step 2: the session, end to end through /me on PostgreSQL ------------------------------------------------------

AUTH_SCHEMA = """
create schema auth;
create table auth.users (id uuid primary key, email varchar(255), email_confirmed_at timestamptz,
                         banned_until timestamptz, deleted_at timestamptz);
create table auth.sessions (id uuid primary key, user_id uuid not null references auth.users (id) on delete cascade,
                            created_at timestamptz not null default now(), not_after timestamptz);
"""


@pytest.fixture()
def stack(monkeypatch):
    """A disposable PostgreSQL database with KoroFarm's schema and a simulated Supabase auth schema, the real auth
    dependency (only the signing-key fetch is local) and two organizations."""
    if not POSTGRES_URL:
        pytest.skip("dedicated PostgreSQL test database not configured")
    from src.backend.app.infrastructure.database.base import Base
    from src.backend.app.main import app
    from src.backend.app.main_dependencies import get_session
    from src.backend.app.supply.domain.crops import ensure_shared_crops
    from src.backend.tests.two_orgs import _org, ensure_roles

    name = f"korofarm_r1_disposable_auth_{uuid4().hex[:10]}"
    admin = create_engine(make_url(POSTGRES_URL).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(make_url(POSTGRES_URL).set(database=name))
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(AUTH_SCHEMA)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with factory() as setup:
            ensure_shared_crops(setup)
            ensure_roles(setup)
            setup.commit()
            a, b = _org(setup, "Alpha"), _org(setup, "Bravo")
        signer = Signer()
        monkeypatch.setenv("SUPABASE_URL", BASE)
        monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", APIKEY)
        monkeypatch.setenv("AUTH_SESSION_VERIFICATION", "database")
        monkeypatch.setattr(auth, "signing_keys", keys_for(signer))

        def session_override():
            db = factory()
            try:
                yield db
            finally:
                db.close()
        saved = dict(app.dependency_overrides)
        app.dependency_overrides.clear()
        app.dependency_overrides[get_session] = session_override
        with TestClient(app) as client:
            yield {"client": client, "engine": engine, "signer": signer, "a": a, "b": b}
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _auth_user(engine, user_id, email="person@example.test", **columns):
    with engine.begin() as connection:
        connection.execute(text("insert into auth.users (id, email, email_confirmed_at, banned_until, deleted_at) "
                                "values (:id, :email, now(), :banned_until, :deleted_at)"),
                           {"id": user_id, "email": email, "banned_until": columns.get("banned_until"),
                            "deleted_at": columns.get("deleted_at")})


def _session(engine, user_id, not_after=None):
    session_id = uuid4()
    with engine.begin() as connection:
        connection.execute(text("insert into auth.sessions (id, user_id, not_after) values (:id, :user, :not_after)"),
                           {"id": session_id, "user": user_id, "not_after": not_after})
    return session_id


def _sign_out(engine, session_id=None, user_id=None):
    """What Supabase Auth does on sign-out: local scope deletes the session row, global scope all of the user's."""
    with engine.begin() as connection:
        if session_id:
            connection.execute(text("delete from auth.sessions where id = :id"), {"id": session_id})
        else:
            connection.execute(text("delete from auth.sessions where user_id = :user"), {"user": user_id})


def _me(client, token, organization=None):
    headers = {"Authorization": f"Bearer {token}"}
    if organization:
        headers["X-Organization-ID"] = str(organization)
    return client.get("/me", headers=headers)


def test_an_active_session_is_accepted_and_refused_immediately_after_sign_out(stack) -> None:
    client, engine, signer, a = stack["client"], stack["engine"], stack["signer"], stack["a"]
    _auth_user(stack["engine"], a["user"])
    laptop, phone = _session(engine, a["user"]), _session(engine, a["user"])
    laptop_token, phone_token = signer.token(a["user"], laptop), signer.token(a["user"], phone)
    me = _me(client, laptop_token)
    assert me.status_code == 200, me.text
    assert me.json()["active_organization_id"] == str(a["org"])

    _sign_out(engine, session_id=laptop)                  # local sign-out on the laptop
    refused = _me(client, laptop_token)
    assert refused.status_code == 401 and refused.json()["detail"] == "Session is not active"
    assert _me(client, phone_token).status_code == 200    # the phone's session is untouched

    _sign_out(engine, user_id=a["user"])                  # global sign-out
    assert _me(client, phone_token).status_code == 401


def test_expired_ended_banned_deleted_and_invalid_sessions_are_refused(stack) -> None:
    client, engine, signer, a = stack["client"], stack["engine"], stack["signer"], stack["a"]
    _auth_user(engine, a["user"])
    active = _session(engine, a["user"])
    assert _me(client, signer.token(a["user"], active, lifetime=-60)).status_code == 401  # token expired
    ended = _session(engine, a["user"], not_after=datetime.now(timezone.utc) - timedelta(minutes=1))
    assert _me(client, signer.token(a["user"], ended)).status_code == 401                 # session past not_after
    assert _me(client, signer.token(a["user"], uuid4())).status_code == 401              # session never existed
    assert _me(client, Signer().token(a["user"], active)).status_code == 401              # forged signature
    assert _me(client, "garbage").status_code == 401
    assert client.get("/me").status_code == 401

    with engine.begin() as connection:
        connection.execute(text("update auth.users set banned_until = now() + interval '1 day' where id = :id"),
                           {"id": a["user"]})
    assert _me(client, signer.token(a["user"], active)).status_code == 401
    with engine.begin() as connection:
        connection.execute(text("update auth.users set banned_until = null, deleted_at = now() where id = :id"),
                           {"id": a["user"]})
    assert _me(client, signer.token(a["user"], active)).status_code == 401


def test_a_session_cannot_be_borrowed_and_membership_is_still_authorized_separately(stack) -> None:
    client, engine, signer, a, b = stack["client"], stack["engine"], stack["signer"], stack["a"], stack["b"]
    _auth_user(engine, a["user"], "alpha@example.test")
    _auth_user(engine, b["user"], "bravo@example.test")
    b_session = _session(engine, b["user"])
    # A's identity presented with B's live session: the row must belong to the token's subject.
    assert _me(client, signer.token(a["user"], b_session)).status_code == 401
    a_session = _session(engine, a["user"])
    token = signer.token(a["user"], a_session)
    assert _me(client, token, a["org"]).status_code == 200
    assert _me(client, token, b["org"]).status_code == 403  # authenticated, not a member: 403, not 401

    stranger = uuid4()  # signed in to Supabase, no KoroFarm account or membership
    _auth_user(engine, stranger, "stranger@example.test")
    refused = _me(client, signer.token(stranger, _session(engine, stranger)))
    assert refused.status_code == 403


def test_identity_details_come_from_auth_users_not_from_token_claims(stack) -> None:
    client, engine, signer, a = stack["client"], stack["engine"], stack["signer"], stack["a"]
    from src.backend.app.core.auth import active_session_identity
    _auth_user(engine, a["user"], "real@example.test")
    session_id = _session(engine, a["user"])
    with sessionmaker(bind=engine)() as session:
        identity = active_session_identity(session, {"sub": str(a["user"]), "session_id": str(session_id),
                                                     "email": "claimed@example.test"})
    assert identity["email"] == "real@example.test" and identity["email_confirmed_at"]
    assert identity["id"] == str(a["user"]) and identity["session_id"] == str(session_id)


def test_when_sessions_or_keys_cannot_be_read_requests_are_refused_with_503(stack, monkeypatch) -> None:
    client, engine, signer, a = stack["client"], stack["engine"], stack["signer"], stack["a"]
    _auth_user(engine, a["user"])
    token = signer.token(a["user"], _session(engine, a["user"]))
    with engine.begin() as connection:
        connection.execute(text("alter table auth.sessions rename to sessions_unavailable"))
    unavailable = _me(client, token)
    assert unavailable.status_code == 503
    with engine.begin() as connection:
        connection.execute(text("alter table auth.sessions_unavailable rename to sessions"))
    assert _me(client, token).status_code == 200          # nothing sticky after an outage
    monkeypatch.setattr(auth, "signing_keys", keys_for(signer, fail=True))
    assert _me(client, token).status_code == 503
