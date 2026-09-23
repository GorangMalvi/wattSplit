"""
Supabase Auth: verify the access token the frontend sends as a Bearer header.

Supports both Supabase JWT setups:
- JWT signing keys (default for new projects, ES256/RS256): verified against
  the project's public JWKS endpoint, no secret needed.
- Legacy shared secret (HS256): set SUPABASE_JWT_SECRET.
"""
from __future__ import annotations

import os
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException, status


ASYMMETRIC_ALGS = ["ES256", "RS256"]


def _supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL is not set")
    return url


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{_supabase_url()}/auth/v1/.well-known/jwks.json", cache_keys=True)


def verify_token(token: str) -> dict:
    """Return the token's claims, or raise ``jwt.PyJWTError``."""
    alg = jwt.get_unverified_header(token).get("alg")
    if alg == "HS256":
        secret = os.environ.get("SUPABASE_JWT_SECRET", "")
        if not secret:
            raise jwt.InvalidTokenError("HS256 token but SUPABASE_JWT_SECRET is not set")
        key, algorithms = secret, ["HS256"]
    elif alg in ASYMMETRIC_ALGS:
        key, algorithms = _jwks_client().get_signing_key_from_jwt(token).key, ASYMMETRIC_ALGS
    else:
        raise jwt.InvalidTokenError(f"Unsupported token algorithm: {alg}")

    return jwt.decode(
        token,
        key,
        algorithms=algorithms,
        audience="authenticated",
        issuer=f"{_supabase_url()}/auth/v1",
    )


def current_user_id(authorization: str | None = Header(None)) -> str:
    """FastAPI dependency: the signed-in user's id (``sub`` claim)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        claims = verify_token(authorization[7:].strip())
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid session: {exc}")
    return claims["sub"]
