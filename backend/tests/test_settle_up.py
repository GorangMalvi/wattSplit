import pytest

from app import calc

from .test_calc import JUNE, JUNE_READINGS, household


def bal(rid, name, balance):
    return {"roommate_id": rid, "name": name, "balance": balance}


# The Balances to Date cards from 7 Oct 2026 (positive = owes).
CARDS = [bal(1, "Gorang", 2595.65), bal(2, "Naveen", -8411.43), bal(3, "UD", 8139.80), bal(4, "akash", 1574.99)]


def test_shares_the_unpaid_gap_equally_and_settles_everyone():
    result = calc.settle_up(CARDS)
    assert result["unpaid_total"] == 3899.01
    assert result["unpaid_each"] == 974.75
    pays = {(t["from_roommate"], t["to_roommate"]): t["amount"] for t in result["transfers"]}
    assert pays == {("UD", "Naveen"): 7165.05, ("Gorang", "Naveen"): 1620.90, ("akash", "Naveen"): 600.23}  # rounded per payment


def test_after_the_transfers_everyone_is_left_with_the_same_share():
    result = calc.settle_up(CARDS)
    left = {b["name"]: b["balance"] for b in CARDS}
    for t in result["transfers"]:
        left[t["from_roommate"]] -= t["amount"]
        left[t["to_roommate"]] += t["amount"]
    assert all(v == pytest.approx(974.75, abs=0.02) for v in left.values())


def test_nothing_to_settle():
    assert calc.settle_up([bal(1, "A", 0), bal(2, "B", 0)])["transfers"] == []
    assert calc.settle_up([])["transfers"] == []


def test_several_creditors():
    result = calc.settle_up([bal(1, "A", 300), bal(2, "B", -100), bal(3, "C", -200)])
    pays = {(t["from_roommate"], t["to_roommate"]): t["amount"] for t in result["transfers"]}
    assert pays == {("A", "C"): 200, ("A", "B"): 100}
    assert result["unpaid_total"] == 0


def test_a_recorded_settlement_moves_both_balances():
    data = household(JUNE, JUNE_READINGS)
    before = {b["name"]: b["balance"] for b in calc.household_balances(data)}
    data.settlement_rows = [{"date": "2026-07-02", "from_roommate": "D", "to_roommate": "A", "amount": 500.0}]
    after = {b["name"]: b for b in calc.household_balances(data)}
    assert after["D"]["balance"] == pytest.approx(before["D"] - 500)
    assert after["A"]["balance"] == pytest.approx(before["A"] + 500)
    assert after["D"]["settled_cumulative"] == 500 and after["A"]["settled_cumulative"] == -500
    # Main + DG still add up to the total.
    for b in after.values():
        assert b["main_balance"] + b["dg_balance"] == pytest.approx(b["balance"])


def payment(rid, name, date, amount, meter="main"):
    return {"id": rid, "date": date, "roommate": name, "roommate_id": rid, "amount": amount, "notes": "", "meter": meter}


def may_household(payments):
    """May with the meter report's figures: 708 opening + 9,000 recharge - 80 closing = 9,628."""
    import pandas as pd
    from app import db
    from .test_calc import MAY_READINGS, month

    m = month("2026-05", 27485, 28742, 9628)
    m.update({"meter_opening_balance": 708, "meter_recharge": 9000, "meter_closing_balance": 80})
    data = household([m], MAY_READINGS)
    data.recharge_rows = payments
    data.recharges = pd.DataFrame(payments, columns=db.RECHARGE_COLS)
    return data


# Everything the meter got in May, recorded: 708 already in it (236 x 3) + 9,000.
MAY_PAID = [payment(1, "A", "2026-05-31", 236), payment(2, "B", "2026-05-05", 3000),
            payment(3, "C", "2026-05-31", 236 + 3000), payment(4, "D", "2026-05-31", 236 + 3000)]


def test_every_payment_recorded_means_no_gap():
    plan = calc.household_settle_up(may_household(MAY_PAID), today="2026-10-07")
    assert plan["through_month"] == "2026-05"
    assert plan["meter_balance"] == 80
    assert plan["unpaid_total"] == 0 and plan["unpaid_each"] == 0


def test_money_left_in_the_meter_stays_as_credit():
    plan = calc.household_settle_up(may_household(MAY_PAID), today="2026-10-07")
    balances = {b["name"]: b["balance"] for b in calc.household_balances(may_household(MAY_PAID))}
    for t in plan["transfers"]:
        balances[t["from_roommate"]] -= t["amount"]
        balances[t["to_roommate"]] += t["amount"]
    assert all(v <= 0.01 for v in balances.values())  # nobody owes
    assert sum(balances.values()) == pytest.approx(-80, abs=0.05)  # the meter's 80 is still credit


def test_payments_after_the_last_billed_month_wait_and_future_dates_are_flagged():
    later = [payment(9, "A", "2026-06-10", 1000), payment(10, "B", "2026-10-21", 1500)]
    plan = calc.household_settle_up(may_household(MAY_PAID + later), today="2026-10-07")
    assert plan["unpaid_total"] == 0  # not distorted by June/October money
    assert plan["later_payments_total"] == 2500
    assert [p["id"] for p in plan["future_payments"]] == [10]


def test_units_to_date_per_roommate():
    rows = {b["name"]: b for b in calc.household_balances(may_household(MAY_PAID))}
    assert rows["A"]["own_units_cumulative"] == 170
    assert rows["A"]["units_cumulative"] == 170.5  # + half a common unit
    assert sum(b["units_cumulative"] for b in rows.values()) == pytest.approx(1257)
