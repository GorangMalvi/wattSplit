"""
Local development sign-in: code 123456, no email sent.

The app normally signs in with a one-time code that Supabase emails. For
local work that's slow (and uses the email quota), so in development the app
can call ``POST /api/dev/login`` instead: with code 123456 and an email listed
in ``DEV_LOGIN_EMAILS``, the backend asks Supabase's admin API for a sign-in
token (``generate_link`` sends no email) and the app turns it into a normal
session with ``verifyOtp``.

Off unless both are set in the local .env (never on Render):
    SUPABASE_SERVICE_ROLE_KEY  the project's service_role / secret key
    DEV_LOGIN_EMAILS           who may sign in this way: emails, "@domain"
                               entries, or "*" for anyone
"""
from __future__ import annotations

import os
from typing import Dict, List

import requests

DEV_LOGIN_CODE = "123456"


class DevLoginError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _service_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def allowed_emails() -> List[str]:
    raw = os.environ.get("DEV_LOGIN_EMAILS", "")
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def enabled() -> bool:
    return bool(_service_key() and allowed_emails() and os.environ.get("SUPABASE_URL", "").strip())


def email_allowed(email: str) -> bool:
    email = email.strip().lower()
    for entry in allowed_emails():
        if entry == "*" or entry == email or (entry.startswith("@") and email.endswith(entry)):
            return True
    return False


def _admin_headers() -> Dict[str, str]:
    key = _service_key()
    headers = {"apikey": key}
    if key.startswith("eyJ"):  # legacy service_role JWT; new sb_secret_ keys go in apikey only
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _generate_link(email: str) -> requests.Response:
    url = os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1/admin/generate_link"
    return requests.post(url, headers=_admin_headers(), json={"type": "magiclink", "email": email}, timeout=20)


def _create_user(email: str) -> None:
    url = os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1/admin/users"
    resp = requests.post(url, headers=_admin_headers(), json={"email": email, "email_confirm": True}, timeout=20)
    if resp.status_code >= 400 and resp.status_code != 422:  # 422: already exists
        raise DevLoginError(502, f"Supabase couldn't create the user (HTTP {resp.status_code})")


def sign_in_token(email: str, code: str) -> Dict[str, str]:
    """``{"token_hash", "type"}`` for supabase.auth.verifyOtp. Sends no email."""
    if not enabled():
        raise DevLoginError(404, "Not found")
    if not email_allowed(email):
        raise DevLoginError(403, "This email isn't in DEV_LOGIN_EMAILS")
    if code.strip() != DEV_LOGIN_CODE:
        raise DevLoginError(401, f"Wrong code (dev sign-in uses {DEV_LOGIN_CODE})")
    email = email.strip().lower()
    try:
        resp = _generate_link(email)
        if resp.status_code in (400, 404, 422):  # no such user yet: create it, then retry
            _create_user(email)
            resp = _generate_link(email)
    except requests.RequestException:
        raise DevLoginError(502, "Couldn't reach Supabase")
    if resp.status_code in (401, 403):
        raise DevLoginError(502, "Supabase rejected SUPABASE_SERVICE_ROLE_KEY")
    if resp.status_code >= 400:
        # Never pass Supabase's body on.
        raise DevLoginError(502, f"Supabase couldn't make a sign-in token (HTTP {resp.status_code})")
    data = resp.json()
    props = data.get("properties") or data  # older Auth versions nest these
    token_hash, kind = props.get("hashed_token"), props.get("verification_type") or "magiclink"
    if not token_hash:
        raise DevLoginError(502, "Supabase's reply had no sign-in token")
    return {"token_hash": token_hash, "type": kind}
