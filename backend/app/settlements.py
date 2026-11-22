"""
Who may do what with a settle-up payment.

    verifying --received--> received --request_undo, agree_undo--> undone
              --not_received--> not_received
              --cancel--> cancelled

Only ``received`` moves balances; ``verifying`` reserves the amount. Only the
receiver's own login can mark a payment received, and undoing one takes both
roommates. The same rules decide what the API allows and which buttons show.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

VERIFYING, RECEIVED = "verifying", "received"

Action = Literal["received", "not_received", "cancel", "request_undo", "agree_undo", "decline_undo", "withdraw_undo"]
Logins = Iterable[Tuple[int, str]]  # (roommate id, a login it has had)

MAX_NEW_PER_DAY = 20  # per person; each one can send an email


class NotAllowed(ValueError):
    """A settle-up change that can't be made; ``status`` is the HTTP status to answer with."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def allowed_actions(row: Dict[str, Any], user_id: str, roommate_id: Optional[int], logins: Logins) -> List[Action]:
    """What this login, linked to ``roommate_id``, may do with the payment."""
    user, logins = str(user_id), set(logins)
    payer, receiver = row["from_roommate_id"], row["to_roommate_id"]

    if row["status"] == VERIFYING:
        actions: List[Action] = []
        # Locked to the receiver's login from when it was sent, or when they joined.
        if roommate_id == receiver and row["receiver_user_id"] == user:
            # Never from a login that sent it, or that has been the payer.
            sent_it = user in (row["created_by"], row["payer_user_id"]) or (payer, user) in logins
            if not sent_it:
                actions.append("received")
            actions.append("not_received")
        if roommate_id == payer or row["created_by"] == user:
            actions.append("cancel")
        return actions

    if row["status"] != RECEIVED:
        return []
    if roommate_id == payer and row["payer_user_id"] in (None, user):
        side, other = "payer", receiver
    elif roommate_id == receiver and row["receiver_user_id"] in (None, user):
        side, other = "receiver", payer
    else:
        return []
    if not row["undo_side"]:
        return [] if row["undo_recent"] else ["request_undo"]
    if row["undo_side"] == side:
        return ["withdraw_undo"]
    if row["undo_requested_by"] == user or (other, user) in logins:
        return ["decline_undo"]  # the same person can't be both who asks and who agrees
    return ["agree_undo", "decline_undo"]


def new_status(
    plan: Dict[str, Any],
    rows: List[Dict[str, Any]],
    logins: Logins,
    names: Dict[int, str],
    *,
    user_id: str,
    roommate_id: Optional[int],
    from_id: int,
    to_id: int,
    amount: float,
    sent_today: int,
) -> str:
    """
    The status a new payment starts in: received when the receiver records it,
    otherwise verifying. Who may record for whom is checked by the caller.
    Raises NotAllowed.
    """
    payer, receiver = names[from_id], names[to_id]
    is_receipt = roommate_id == to_id
    if is_receipt and (from_id, str(user_id)) in set(logins):
        raise NotAllowed(403, f"You've been signed in as {payer}, so you can't confirm {payer}'s payment.")
    if sent_today >= MAX_NEW_PER_DAY:
        raise NotAllowed(429, "That's a lot of payments for one day. Try again tomorrow.")

    waiting = [r for r in rows if r["status"] == VERIFYING
               and (r["from_roommate_id"], r["to_roommate_id"]) == (from_id, to_id)]
    if is_receipt and waiting:
        raise NotAllowed(409, f"A payment from {payer} is already waiting for you. Mark that one received instead.")
    if any(abs(r["amount"] - amount) < 0.005 for r in waiting):
        raise NotAllowed(409, f"₹{amount:,.2f} from {payer} is already waiting for {receiver} to confirm.")

    if plan["through_month"] is None:
        raise NotAllowed(409, "Settle up opens once a month has its bill and everyone's readings.")
    positions = {p["roommate_id"]: p for p in plan["positions"]}
    limit = min(positions.get(from_id, {}).get("to_pay", 0.0), positions.get(to_id, {}).get("to_receive", 0.0))
    if limit < 0.01:
        raise NotAllowed(
            409, f"{payer} has nothing left to pay {receiver}. Amounts waiting to be confirmed are already counted."
        )
    if amount > limit + 0.011:  # suggested amounts are rounded to the paisa
        raise NotAllowed(409, f"That's more than {payer} has left to pay {receiver}: ₹{limit:,.2f} at most.")
    return RECEIVED if is_receipt else VERIFYING
