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
