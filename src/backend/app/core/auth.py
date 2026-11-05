"""Authentication: who is calling, and whether their session is still active.

Which organization and role the caller may act for is a separate step (identity/application/authorization.py):
an authenticated user with no active membership is refused there with 403, never here.

Staging and production (AUTH_SESSION_VERIFICATION=database, enforced at startup) check every request in two steps:
  1. The access token is verified locally: signature against the project's published asymmetric signing keys
     (GET {SUPABASE_URL}/auth/v1/.well-known/jwks.json, cached; ES256 or RS256 only, never HS256 or none), issuer
     {SUPABASE_URL}/auth/v1, audience and role "authenticated", unexpired, and sub and session_id UUIDs.
  2. The session is still active: its row in auth.sessions exists for that user and has not passed not_after, and the
     user is neither deleted nor banned. Supabase deletes the row when the user signs out (any scope), so a token is
     refused immediately, not when it expires. The row is read on every request, never cached.
Failure behaviour: an invalid, expired or signed-out token gets 401. If the signing keys or the session records cannot
be read, the request gets 503: it is never accepted. Keys are refetched on an unknown key id (at most every
KEY_REFETCH_SECONDS) and every KEY_TTL_SECONDS; if a refetch fails, keys fetched within KEY_MAX_STALE_SECONDS are still
used. The email and its confirmation come from auth.users, not from token claims.

Development and test default to AUTH_SESSION_VERIFICATION=remote: Supabase Auth's GET /auth/v1/user, which the E2E
auth stand-in (src/frontend/e2e/r1/support/auth-stub.mjs) implements.
"""
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.backend.app.core.config import demo_auth_bypass_enabled, session_verification
from src.backend.app.main_dependencies import get_session

logger = logging.getLogger(__name__)

ALGORITHMS = ("ES256", "RS256")
AUDIENCE = "authenticated"
KEY_TTL_SECONDS = 600
KEY_REFETCH_SECONDS = 30
KEY_MAX_STALE_SECONDS = 3600
CLOCK_LEEWAY_SECONDS = 10  # tolerated clock difference with Supabase Auth, for iat and exp

ACTIVE_SESSION = text("""
    select u.email, u.email_confirmed_at
    from auth.sessions s join auth.users u on u.id = s.user_id
    where s.id = cast(:session_id as uuid) and s.user_id = cast(:user_id as uuid)
      and (s.not_after is null or s.not_after > now())
      and u.deleted_at is null and (u.banned_until is null or u.banned_until <= now())""")


class InvalidToken(Exception):
    """The token is not a valid, unexpired access token for this project (401)."""


class AuthUnavailable(Exception):
    """The signing keys or the session records could not be read (503)."""


def _supabase() -> tuple[str, str]:
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY") or ""
    return url, key


def usable_signing_keys(jwks: dict) -> dict[str, jwt.PyJWK]:
    """The ES256/RS256 public keys in a JWKS document, by key id. Symmetric or unidentified keys are ignored."""
    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise ValueError("not a JWKS document")
    keys: dict[str, jwt.PyJWK] = {}
    for item in jwks["keys"]:
        if not isinstance(item, dict) or not item.get("kid") or item.get("kty") not in ("EC", "RSA"):
            continue
        algorithm = item.get("alg") or ("ES256" if item.get("kty") == "EC" else "RS256")
        if algorithm not in ALGORITHMS:
            continue
        try:
            keys[item["kid"]] = jwt.PyJWK(item, algorithm=algorithm)
        except jwt.PyJWTError:
            continue
    return keys


def fetch_signing_keys(base_url: str, apikey: str) -> dict[str, jwt.PyJWK]:
    request = Request(f"{base_url}/auth/v1/.well-known/jwks.json", headers={"apikey": apikey} if apikey else {})
    with urlopen(request, timeout=5) as response:
        return usable_signing_keys(json.load(response))


class SigningKeys:
    """Thread-safe cache of one project's signing keys."""

    def __init__(self, fetch: Callable[[str, str], dict[str, jwt.PyJWK]] = fetch_signing_keys,
                 clock: Callable[[], float] = time.monotonic):
        self._fetch, self._clock = fetch, clock
        self._lock = threading.Lock()
        self._url: str | None = None
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = self._attempted_at = float("-inf")

    def key(self, base_url: str, apikey: str, kid: str) -> jwt.PyJWK | None:
        with self._lock:
            now = self._clock()
            if base_url != self._url:
                self._url, self._keys = base_url, {}
                self._fetched_at = self._attempted_at = float("-inf")
            expired = now - self._fetched_at >= KEY_TTL_SECONDS
            unknown = kid not in self._keys and now - self._attempted_at >= KEY_REFETCH_SECONDS
            failed = False
            if expired or unknown:
                self._attempted_at = now
                try:
                    self._keys, self._fetched_at = self._fetch(base_url, apikey), now
                except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                    failed = True
                    logger.warning("could not refresh the Supabase signing keys (%s)", type(exc).__name__)
            if now - self._fetched_at >= KEY_MAX_STALE_SECONDS:
                raise AuthUnavailable("signing keys unavailable")
            if failed and kid not in self._keys:
                raise AuthUnavailable("signing key not cached and the key set could not be refreshed")
            return self._keys.get(kid)


signing_keys = SigningKeys()


def verify_access_token(token: str, base_url: str, apikey: str, keys: SigningKeys | None = None) -> dict[str, Any]:
    """Step 1: the verified claims of a Supabase access token. Raises InvalidToken or AuthUnavailable."""
    keys = signing_keys if keys is None else keys
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise InvalidToken("malformed token") from exc
    algorithm, kid = header.get("alg"), header.get("kid")
    if algorithm not in ALGORITHMS or not isinstance(kid, str) or not kid:
        raise InvalidToken("unsupported algorithm or missing key id")
    key = keys.key(base_url, apikey, kid)
    if key is None or key.algorithm_name != algorithm:
        raise InvalidToken("unknown signing key")
    try:
        claims = jwt.decode(token, key.key, algorithms=[algorithm], audience=AUDIENCE, issuer=f"{base_url}/auth/v1",
                            leeway=CLOCK_LEEWAY_SECONDS, options={"require": ["exp", "iat", "iss", "aud", "sub", "session_id"]})
    except jwt.PyJWTError as exc:
        raise InvalidToken(type(exc).__name__) from exc
    if claims.get("role") != "authenticated" or claims.get("is_anonymous") is True:
        raise InvalidToken("not an authenticated user session")
    try:
        UUID(str(claims["sub"])), UUID(str(claims["session_id"]))
    except ValueError as exc:
        raise InvalidToken("subject or session id is not a UUID") from exc
    return claims


def active_session_identity(session: Session, claims: dict[str, Any]) -> dict[str, Any] | None:
    """Step 2: the identity if the token's session is still active for its user, else None. Raises AuthUnavailable."""
    try:
        row = session.execute(ACTIVE_SESSION, {"session_id": claims["session_id"], "user_id": claims["sub"]}).first()
    except SQLAlchemyError as exc:
        session.rollback()
        raise AuthUnavailable(type(exc).__name__) from exc
    if row is None:
        return None
    confirmed = row.email_confirmed_at
    return {"id": str(claims["sub"]), "email": row.email,
            "email_confirmed_at": confirmed.isoformat() if hasattr(confirmed, "isoformat") else confirmed,
            "session_id": str(claims["session_id"]), "aal": claims.get("aal"), "auth_mode": "supabase_session"}


def _remote_user(base_url: str, apikey: str, token: str) -> dict[str, Any]:
    request = Request(f"{base_url}/auth/v1/user", headers={"apikey": apikey, "Authorization": f"Bearer {token}"})
    try:
        with urlopen(request, timeout=5) as response:
            user = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
    return user


def get_current_user(authorization: str | None = Header(default=None),
                     session: Session = Depends(get_session)) -> dict[str, Any]:
    if demo_auth_bypass_enabled():
        return {"id": "competition-demo-operator", "auth_mode": "demo"}
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    base_url, apikey = _supabase()
    if not base_url or not apikey:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Supabase auth is not configured")
    if session_verification() == "remote":
        return _remote_user(base_url, apikey, token)
    try:
        identity = active_session_identity(session, verify_access_token(token, base_url, apikey))
    except InvalidToken as exc:
        logger.info("bearer token refused: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc
    except AuthUnavailable as exc:
        logger.warning("authentication unavailable: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Authentication is temporarily unavailable") from exc
    if identity is None:
        logger.info("bearer token refused: session not active")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is not active")
    return identity
