"""
Emails about settle-up payments, and reminders for ones waiting to be confirmed.

Links only open the app: mail scanners follow links, so none changes anything.
They come from APP_URL alone, never the request's Origin, which a sender
controls. A failed email never fails the payment; the app shows it either way.
"""
from __future__ import annotations

import html
import logging
import os
import threading
from typing import Any, Dict, Optional, Tuple

from . import db, mailer

log = logging.getLogger("uvicorn.error")

CHECK_EVERY_SECONDS = 3600


def compose(event: str, row: Dict[str, Any]) -> Tuple[str, str]:
    """(subject, body) for an event."""
    payer, receiver = _line(row["from_roommate"]), _line(row["to_roommate"])
    amount = f"₹{row['amount']:,.2f}"
    both = f"{amount} from {payer} to {receiver}"
    asker, other = (payer, receiver) if row.get("undo_side") == "payer" else (receiver, payer)
    check = "Check your bank or UPI app, then open wattSplit and choose Mark received or Not received."
    if event == "verifying":
        return (
            f"{payer} says they paid you {amount}",
            f"{payer} says they paid you {amount}. It isn't settled until you confirm it. {check}",
        )
    if event == "reminder":
        return (
            f"Reminder: did {payer} pay you {amount}?",
            f"{payer} says they paid you {amount}, and it's still waiting for you. {check}",
        )
    if event == "received":
        return f"{receiver} received your {amount}", f"{receiver} marked {both} as received. It's settled."
    if event == "not_received":
        return (
            f"{receiver} didn't receive your {amount}",
            f"{receiver} says they didn't get the {amount}. Their reason: \"{_line(row.get('reject_reason') or '')}\". "
            "It still counts as owed. Check with them, then you can send it for verification again.",
        )
    if event == "cancel":
        return f"Cancelled: {amount} from {payer}", f"The payment of {both} was cancelled. Nothing to confirm."
    if event == "request_undo":
        return (
            f"{asker} asks to undo {amount}",
            f"{asker} asks to undo the payment of {both}. It stays settled unless {other} agrees in wattSplit.",
        )
    if event == "agree_undo":
        return f"Undone: {amount}", f"{other} agreed, so the payment of {both} is undone and owed again."
    if event == "decline_undo":
        return f"Not undone: {amount}", f"{other} didn't agree to undo the payment of {both}. It stays settled."
    raise ValueError(event)


def notify(event: str, hid: Any, row: Dict[str, Any], actor: Optional[str] = None) -> None:
    """Email whoever needs to know about the event. Never raises."""
    try:
        people = db.settlement_people(hid, row)
        payer, receiver = people["payer"], people["receiver"]
        if event in ("verifying", "reminder", "cancel"):
            # No login yet: the owner's invite address, with the link to join.
            to = receiver or people["invite"]
        elif event in ("received", "not_received"):
            to = payer or people["creator"]
        else:
            asked_by_payer = row.get("undo_side") == "payer"
            if event == "request_undo":
                to = receiver if asked_by_payer else payer
            else:
                to = payer if asked_by_payer else receiver
        if not to or (actor and to["user_id"] == str(actor)):
            return

        subject, body = compose(event, row)
        household, link = _line(people["household"]), None
        app_url = os.environ.get("APP_URL", "").strip().rstrip("/")
        if app_url:
            link = f"{app_url}/?invite={to['code']}" if to.get("code") else f"{app_url}/?household={hid}"
        text = f"{body}\n\nHousehold: {household}" + (f"\nOpen wattSplit: {link}" if link else "")
        markup = f"<p>{html.escape(body)}</p><p style=\"color:#64748b\">Household: {html.escape(household)}</p>"
        if link:
            markup += (
                f'<p><a href="{html.escape(link)}" style="background:#4f46e5;color:#fff;padding:10px 18px;'
                'border-radius:6px;text-decoration:none;display:inline-block">Open wattSplit</a></p>'
            )
        result = mailer.send_email(to["email"], subject, text, html=markup, category="Settle up")
        if not getattr(result, "success", None) and not (isinstance(result, dict) and result.get("success")):
            log.warning("Settle-up email (%s) wasn't accepted", event)
        elif event in ("verifying", "reminder"):
            db.mark_settlement_emailed(row["id"])
    except Exception as exc:  # type only: messages can hold addresses or connection details
        log.warning("Settle-up email (%s) failed: %s", event, type(exc).__name__)


def send_due_reminders() -> None:
    for hid, row in db.claim_due_reminders():
        notify("reminder", hid, row)


def start_reminders() -> Optional[threading.Event]:
    """
    Check for due reminders at startup and hourly. Off unless
    SETTLEMENT_REMINDERS=1, so a backend started on a PC never emails flatmates.
    Set the returned event to stop.
    """
    if os.environ.get("SETTLEMENT_REMINDERS", "").strip() != "1":
        return None
    stop = threading.Event()

    def run() -> None:
        while not stop.is_set():
            try:
                send_due_reminders()
            except Exception as exc:
                log.warning("Settle-up reminders failed: %s", type(exc).__name__)
            stop.wait(CHECK_EVERY_SECONDS)

    threading.Thread(target=run, name="settlement-reminders", daemon=True).start()
    return stop


def _line(text: str) -> str:
    """One line: names and reasons are typed by users and end up in subjects."""
    return " ".join(str(text).split())
