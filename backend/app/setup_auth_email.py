"""
Send Supabase Auth emails through Mailtrap SMTP and make them one-time codes.

Supabase's built-in email service can't use custom templates on the free plan,
so this configures Mailtrap as the project's SMTP provider, then replaces the
"Confirm signup" and "Magic Link" templates with a code ({{ .Token }}) email.

Needs SUPABASE_URL, SUPABASE_ACCESS_TOKEN (personal access token),
MAILTRAP_API_TOKEN, MAIL_FROM_EMAIL and MAIL_FROM_NAME in the environment.

Usage (safe to re-run):
    python -m app.setup_auth_email
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

MAILTRAP_SMTP_HOST = "live.smtp.mailtrap.io"
MAILTRAP_SMTP_PORT = "587"
MAILTRAP_SMTP_USER = "api"

CODE_SUBJECT = "Your wattSplit sign-in code"
CODE_TEMPLATE = """<h2>Your wattSplit sign-in code</h2>
<p>Enter this code to sign in to wattSplit:</p>
<p style="font-size:28px;font-weight:bold;letter-spacing:6px;font-family:monospace">{{ .Token }}</p>
<p>It expires in 1 hour. If you didn't request it, you can ignore this email.</p>
"""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"{name} is not set")
    return value


def _patch_auth_config(project_ref: str, access_token: str, changes: dict) -> None:
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{project_ref}/config/auth",
        data=json.dumps(changes).encode(),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "wattsplit-setup",
        },
        method="PATCH",
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as exc:
        message = json.loads(exc.read() or b"{}").get("message", "")
        sys.exit(f"Supabase rejected the change (HTTP {exc.code}): {message}")


def main() -> None:
    project_ref = urlsplit(_required("SUPABASE_URL")).hostname.split(".")[0]
    access_token = _required("SUPABASE_ACCESS_TOKEN")
    # The public web app (APP_URL) when there is one, else the local Docker address.
    local_url = os.environ.get("LOCAL_HOST_URL", "http://wattsplit.localhost").rstrip("/")
    app_url = (os.environ.get("APP_URL") or local_url).rstrip("/")
    allowed = ",".join(dict.fromkeys([app_url, local_url, "http://localhost:5173"]))

    # SMTP first: Supabase only allows template edits once a custom provider is set.
    _patch_auth_config(project_ref, access_token, {
        "smtp_host": MAILTRAP_SMTP_HOST,
        "smtp_port": MAILTRAP_SMTP_PORT,
        "smtp_user": MAILTRAP_SMTP_USER,
        "smtp_pass": _required("MAILTRAP_API_TOKEN"),
        "smtp_admin_email": _required("MAIL_FROM_EMAIL"),
        "smtp_sender_name": os.environ.get("MAIL_FROM_NAME", "wattSplit"),
        # Custom SMTP lifts the built-in 2 emails/hour limit.
        "rate_limit_email_sent": 30,
    })
    print(f"SMTP: Supabase Auth now sends through {MAILTRAP_SMTP_HOST}")

    _patch_auth_config(project_ref, access_token, {
        "mailer_subjects_confirmation": CODE_SUBJECT,
        "mailer_templates_confirmation_content": CODE_TEMPLATE,
        "mailer_subjects_magic_link": CODE_SUBJECT,
        "mailer_templates_magic_link_content": CODE_TEMPLATE,
        "site_url": app_url,
        "uri_allow_list": allowed,
    })
    print("Templates: sign-up and sign-in emails now contain a one-time code")


if __name__ == "__main__":
    main()
