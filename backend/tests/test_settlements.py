import pandas as pd
import pytest

from app import calc, db, settlement_mail, settlements

from .test_calc import NAMES, household, month, reading

A, B, C, D = 1, 2, 3, 4
NAME = {i + 1: n for i, n in enumerate(NAMES)}
LOGIN = {A: "user-a", B: "user-b", C: "user-c", D: "user-d"}
LOGINS = set(LOGIN.items())


def settlement(status="verifying", amount=200.0, payer=A, receiver=B, **changes):
    return {
        "id": 1, "date": "2026-06-02", "status": status, "amount": amount,
        "from_roommate_id": payer, "from_roommate": NAME[payer],
        "to_roommate_id": receiver, "to_roommate": NAME[receiver],
        "created_by": LOGIN[payer], "payer_user_id": LOGIN[payer], "receiver_user_id": LOGIN[receiver],
        "undo_side": None, "undo_requested_by": None, "undo_recent": False, "reject_reason": None,
        **changes,
    }


def flat(*rows, ends=(1100, 2100, 3100, 4100), bill=800):
    """B paid the whole May bill of 800, so A, C and D owe B 200 each."""
    readings = [reading("2026-05", n, end, start)
                for n, end, start in zip(NAMES, ends, (1000, 2000, 3000, 4000)) if end is not None]
    data = household([month("2026-05", 5000, 5500, bill)], readings)
    paid = [{"id": 1, "date": "2026-05-20", "roommate_id": B, "roommate": "B", "amount": 800.0,
             "notes": "", "meter": "main"}]
    data.recharge_rows, data.recharges = paid, pd.DataFrame(paid, columns=db.RECHARGE_COLS)
    data.settlement_rows = list(rows)
    return data


def plan_of(data):
    return calc.household_settle_up(data, today="2026-06-10")


def position(data, rid):
    return next(p for p in plan_of(data)["positions"] if p["roommate_id"] == rid)


def suggested(data):
    return {(t["from_roommate"], t["to_roommate"]): t["amount"] for t in plan_of(data)["transfers"]}


def send(data, amount, payer=A, receiver=B, by=None, user=None, logins=LOGINS, sent_today=0):
    by = payer if by is None else by
    return settlements.new_status(
        plan_of(data), data.settlement_rows, logins, NAME,
        user_id=user or LOGIN[by], roommate_id=by, from_id=payer, to_id=receiver,
        amount=amount, sent_today=sent_today,
    )


def actions(row, who, user=None, logins=LOGINS):
    return settlements.allowed_actions(row, user or LOGIN[who], who, logins)


# ---- how the money behaves

def test_before_paying():
    assert position(flat(), A)["balance"] == 200
    assert suggested(flat())[("A", "B")] == 200


def test_in_verification_still_owes_but_is_reserved():
    data = flat(settlement())
    a = position(data, A)
    assert (a["balance"], a["waiting_out"], a["to_pay"]) == (200, 200, 0)
    assert ("A", "B") not in suggested(data)
    b = next(r for r in calc.household_balances(data) if r["name"] == "A")
    assert b["balance"] == 200 and b["settled_cumulative"] == 0


def test_received_settles_it():
    data = flat(settlement("received"))
    assert position(data, A)["balance"] == 0
    assert ("A", "B") not in suggested(data)


@pytest.mark.parametrize("status", ["not_received", "cancelled", "undone"])
def test_closed_without_receiving_is_owed_again(status):
    data = flat(settlement(status))
    assert position(data, A)["balance"] == 200
    assert suggested(data)[("A", "B")] == 200


def test_part_payment():
    waiting = flat(settlement(amount=120.0))
    assert position(waiting, A)["balance"] == 200 and suggested(waiting)[("A", "B")] == 80
    assert send(waiting, 80) == "verifying"
    assert position(flat(settlement("received", amount=120.0)), A)["balance"] == 80


# ---- sending one

def test_payer_sends_for_verification_and_receiver_records_at_once():
    assert send(flat(), 200) == "verifying"
    assert send(flat(), 200, by=B) == "received"
    assert send(flat(), 200, by=C) == "verifying"  # the owner, for A: still needs B


@pytest.mark.parametrize("rows, amount, by", [
    ([], 200.5, A),  # more than owed
    ([settlement()], 200, A),  # the same one again
    ([settlement()], 10, A),  # all of it is reserved
    ([settlement(amount=120.0)], 81, A),  # more than what's left
    ([settlement(amount=50.0)], 50, A),  # same amount already waiting
    ([settlement(amount=50.0)], 20, B),  # receiver must answer the waiting one
])
def test_refuses_double_or_too_much(rows, amount, by):
    with pytest.raises(settlements.NotAllowed) as exc:
        send(flat(*rows), amount, by=by)
    assert exc.value.status == 409


def test_cannot_pay_someone_who_is_owed_nothing():
    with pytest.raises(settlements.NotAllowed):
        send(flat(), 50, payer=A, receiver=C)


def test_cannot_confirm_as_a_former_payer():
    with pytest.raises(settlements.NotAllowed) as exc:
        send(flat(), 200, by=B, user="user-a")  # A's login, now linked as B
    assert exc.value.status == 403


def test_daily_limit():
    with pytest.raises(settlements.NotAllowed) as exc:
        send(flat(), 200, sent_today=settlements.MAX_NEW_PER_DAY)
    assert exc.value.status == 429


# ---- who can answer

def test_only_the_receiver_marks_received():
    row = settlement()
    assert actions(row, B) == ["received", "not_received"]
    assert actions(row, A) == ["cancel"]
    assert actions(row, C) == []  # anyone else, the owner included


def test_locked_to_the_receivers_login():
    assert actions(settlement(), B, user="someone-relinked-as-b") == []
    assert actions(settlement(receiver_user_id=None), B) == []  # until they join by invite


def test_the_senders_login_never_marks_received():
    switched = settlement(receiver_user_id="user-a")
    assert "received" not in actions(switched, B, user="user-a")
    sent_by_b = settlement(created_by="user-b")
    assert "received" not in actions(sent_by_b, B)
    was_a = LOGINS | {(A, "user-b")}
    assert "received" not in actions(settlement(), B, logins=was_a)


def test_whoever_sent_it_can_cancel():
    assert actions(settlement(created_by="user-c"), C) == ["cancel"]


def test_undo_takes_both():
    row = settlement("received")
    assert actions(row, A) == actions(row, B) == ["request_undo"]
    assert actions(row, C) == []
    asked = settlement("received", undo_side="payer", undo_requested_by="user-a")
    assert actions(asked, A) == ["withdraw_undo"]
    assert actions(asked, B) == ["agree_undo", "decline_undo"]
    assert actions(asked, C) == []
    assert "agree_undo" not in actions(asked, B, logins=LOGINS | {(A, "user-b")})


def test_undo_requests_are_not_repeated_the_same_day():
    assert actions(settlement("received", undo_recent=True), A) == []


def test_payments_from_before_verification_can_still_be_undone():
    old = settlement("received", payer_user_id=None, receiver_user_id=None)
    assert actions(old, A) == actions(old, B) == ["request_undo"]


@pytest.mark.parametrize("status", ["not_received", "cancelled", "undone"])
def test_closed_payments_have_no_actions(status):
    assert actions(settlement(status), A) == actions(settlement(status), B) == []


# ---- half-entered months

def test_a_half_entered_month_is_not_settled():
    data = flat(ends=(1100, None, None, None))
    plan = plan_of(data)
    assert plan["through_month"] is None and plan["transfers"] == []
    assert plan["waiting_for"] == [{"month": "2026-05", "missing": ["B", "C", "D"], "needs_bill": False}]
    with pytest.raises(settlements.NotAllowed):
        send(data, 10)


def test_a_month_without_a_bill_is_not_settled():
    plan = plan_of(flat(bill=0))
    assert plan["through_month"] is None
    assert plan["waiting_for"] == [{"month": "2026-05", "missing": [], "needs_bill": True}]


MONTHS = [month("2026-05", 5000, 5500, 800), month("2026-06", 5500, 6000, 800), month("2026-07", 6000, 6500, 800)]


def readings_for(m, ends):
    starts = (1000, 2000, 3000, 4000) if m == "2026-05" else (None,) * 4
    return [reading(m, n, e, s) for n, e, s in zip(NAMES, ends, starts) if e is not None]


def test_settles_up_to_the_last_complete_month():
    data = household(MONTHS[:2], readings_for("2026-05", (1100, 2100, 3100, 4100))
                     + readings_for("2026-06", (1200, None, None, None)))
    plan = plan_of(data)
    assert plan["through_month"] == "2026-05"
    assert plan["waiting_for"] == [{"month": "2026-06", "missing": ["B", "C", "D"], "needs_bill": False}]


def test_a_skipped_month_settles_with_the_reading_that_catches_it_up():
    may = readings_for("2026-05", (1100, 2100, 3100, 4100))
    june = readings_for("2026-06", (1200, None, 3200, 4200))
    july = readings_for("2026-07", (1300, 2300, 3300, 4300))
    assert calc.settle_through(household(MONTHS[:2], may + june))[0] == "2026-05"
    assert calc.settle_through(household(MONTHS, may + june + july)) == ("2026-07", [])


# ---- emails

@pytest.fixture
def outbox(monkeypatch):
    sent = []
    people = {
        "household": "Flat\r\nBcc: x@example.com",
        "payer": {"user_id": "user-a", "email": "a@example.com"},
        "receiver": {"user_id": "user-b", "email": "b@example.com"},
        "creator": None, "invite": None,
    }
    monkeypatch.setattr(db, "settlement_people", lambda hid, row: people)
    monkeypatch.setattr(db, "mark_settlement_emailed", lambda sid: None)
    monkeypatch.setenv("APP_URL", "https://app.example")
    monkeypatch.setattr(settlement_mail.mailer, "send_email",
                        lambda to, subject, text, **kw: sent.append((to, subject, text, kw["html"])) or {"success": True})
    return sent, people


@pytest.mark.parametrize("event, to", [
    ("verifying", "b@example.com"), ("reminder", "b@example.com"), ("cancel", "b@example.com"),
    ("received", "a@example.com"), ("not_received", "a@example.com"),
])
def test_who_is_emailed(outbox, event, to):
    settlement_mail.notify(event, "hid", settlement())
    assert [m[0] for m in outbox[0]] == [to]


@pytest.mark.parametrize("event, to", [
    ("request_undo", "b@example.com"), ("agree_undo", "a@example.com"), ("decline_undo", "a@example.com"),
])
def test_who_is_emailed_about_an_undo(outbox, event, to):
    settlement_mail.notify(event, "hid", settlement("received", undo_side="payer"))
    assert [m[0] for m in outbox[0]] == [to]


def test_the_email_says_says_and_only_opens_the_app(outbox):
    sent, _ = outbox
    settlement_mail.notify("verifying", "hid", settlement(from_roommate="<b>A</b>\r\nBcc: y"))
    to, subject, text, markup = sent[0]
    assert "says they paid you ₹200.00" in subject and "\n" not in subject and "\r" not in subject
    assert "isn't settled until you confirm" in text
    assert "https://app.example/?household=hid" in text
    assert "<b>A</b>" not in markup


def test_a_receiver_without_a_login_gets_the_invite(outbox):
    sent, people = outbox
    people.update(receiver=None, invite={"user_id": None, "email": "new@example.com", "code": "CODE"})
    settlement_mail.notify("verifying", "hid", settlement(receiver_user_id=None))
    assert sent[0][0] == "new@example.com" and "?invite=CODE" in sent[0][2]


def test_nobody_is_emailed_about_their_own_action(outbox):
    settlement_mail.notify("received", "hid", settlement(), actor="user-a")
    assert outbox[0] == []


def test_a_failed_email_does_not_raise(outbox, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider detail")

    monkeypatch.setattr(settlement_mail.mailer, "send_email", boom)
    settlement_mail.notify("verifying", "hid", settlement())


def test_reminders_are_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("SETTLEMENT_REMINDERS", raising=False)
    assert settlement_mail.start_reminders() is None
