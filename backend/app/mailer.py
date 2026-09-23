"""
Transactional email through Mailtrap's Email API.

Sign-in codes are sent by Supabase Auth itself over Mailtrap SMTP (see
setup_auth_email.py); use ``send_email`` for any email the app sends directly.

Check the Mailtrap setup with a test email:
    python -m app.mailer you@example.com
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import mailtrap as mt


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def send_email(to: str, subject: str, text: str, html: Optional[str] = None,
               category: str = "wattSplit") -> dict:
    """Send one email and return Mailtrap's response (``success``, ``message_ids``)."""
    mail = mt.Mail(
        sender=mt.Address(
            email=_required("MAIL_FROM_EMAIL"),
            name=os.environ.get("MAIL_FROM_NAME", "wattSplit"),
        ),
        to=[mt.Address(email=to)],
        subject=subject,
        text=text,
        html=html,
        category=category,
    )
    client = mt.MailtrapClient(token=_required("MAILTRAP_API_TOKEN"))
    return client.send(mail)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m app.mailer you@example.com")
    response = send_email(
        to=sys.argv[1],
        subject="wattSplit test email",
        text="Mailtrap is set up for wattSplit.",
        category="Integration Test",
    )
    print(response)
