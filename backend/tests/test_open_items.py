import random

import pytest

from app import calc, db

from .test_calc import NAMES, household, month, reading

M4, M5, M6, M7 = "2026-04", "2026-05", "2026-06", "2026-07"


# ---- unticking Active

def person(active=True, join=M5, leave=""):
    return {"is_active": active, "join_date": join, "leave_date": leave}


@pytest.mark.parametrize("before, active, leave, read, saved", [
    (person(), False, "", [M5, M6], M6),  # unticked: left after the last billed month
    (person(), False, M5, [M5, M6], M5),  # a Left month given is respected
    (person(), False, "", [], ""),  # nothing billed, nothing to keep
    (person(), False, "", [M4], ""),  # a reading from before joining was never billed
    (person(False, leave=M5), False, "", [M5, M6], M5),  # clearing Left while inactive can't rewrite
    (person(False), False, "", [M5], ""),  # saved like this earlier: a rename doesn't change bills
    (person(False), False, M5, [M5], M5),  # and can be repaired with a Left month
    (person(False, leave=M6), True, M6, [M5, M6], ""),  # ticked again: back
    (person(False, leave=M5), True, M5, [M5, M6], M5),  # unless that would bill a later reading
    (person(), True, "", [M5], ""),
    (person(leave=M5), True, "", [M5], ""),
])
def test_left_month_saved(before, active, leave, read, saved):
    assert db.saved_leave_month(before, active, leave, read) == saved


def test_unticking_does_not_change_any_past_bill():
    rnd = random.Random(5)
    months = [month(m, 5000 + i * 900, 5900 + i * 900, 4000) for i, m in enumerate((M4, M5, M6, M7))]
    for _ in range(300):
        rows = []
        for i, name in enumerate(NAMES):
            at = 1000 * (i + 1)
            for m in (M4, M5, M6, M7):
                at += rnd.randint(0, 200)
                if rnd.random() < 0.8:
                    rows.append(reading(m, name, at, at - 10))
        data = household(months, rows)  # everyone joined in May
        who = rnd.choice(NAMES)
        pick = data.roommates["name"] == who
        if rnd.random() < 0.3:
            data.roommates.loc[pick, "leave_date"] = rnd.choice((M5, M6))
        bills = calc.running_balances(data)

        before = data.roommates[pick].iloc[0].to_dict()
        read = [r["month"] for r in rows if r["roommate"] == who]
        saved = db.saved_leave_month(before, False, "", read)
        data.roommates.loc[pick, "is_active"] = False
        data.roommates.loc[pick, "leave_date"] = saved
        assert calc.running_balances(data) == bills


def test_inactive_with_a_left_month_is_not_active_before_joining():
    data = household([month(M4, 0, 10, 100)], [])
    pick = data.roommates["name"] == "A"
    data.roommates.loc[pick, "is_active"] = False
    data.roommates.loc[pick, "leave_date"] = M6
    active = [m for m in (M4, M5, M6, M7) if calc._roommate_is_active("A", m, data.roommates)]
    assert active == [M5, M6]


# ---- deleting a month

def after_delete(months, readings, deleted):
    kept = calc.starts_to_keep(months, readings, deleted)
    left = [m for m in months if m != deleted]
    changed = {m: v for m, v in readings.items() if m != deleted}
    for m, start in kept.items():
        changed[m] = (changed.get(m, (None, None))[0], start)
    return kept, calc.reading_starts(left, changed)


def test_deleting_the_first_month_keeps_what_the_next_counts_from():
    kept, starts = after_delete([M5, M6], {M5: (2100, 2000), M6: (2200, None)}, M5)
    assert kept == {M6: 2100} and starts[M6].previous == 2100


def test_deleting_the_first_month_before_the_next_reading_is_in():
    kept, starts = after_delete([M5, M6, M7], {M5: (2100, 2000), M7: (2300, None)}, M5)
    assert kept == {M6: 2100} and starts[M7].previous == 2100


def test_deleting_a_middle_month_carries_on_from_the_one_before():
    kept, starts = after_delete([M5, M6, M7], {M5: (2100, 2000), M6: (2200, None), M7: (2300, None)}, M6)
    assert kept == {} and starts[M7].previous == 2100


def test_an_old_start_reading_does_not_take_over():
    kept, starts = after_delete([M5, M6], {M5: (2100, 2000), M6: (2200, 50)}, M5)
    assert kept == {M6: 2100} and starts[M6].previous == 2100


def test_deleting_the_last_month_needs_nothing():
    assert calc.starts_to_keep([M5, M6], {M5: (2100, 2000), M6: (2200, None)}, M6) == {}


def test_refuses_when_a_meter_would_run_backwards():
    with pytest.raises(ValueError, match="July 2026"):
        calc.starts_to_keep([M5, M6, M7], {M5: (2100, 2000), M6: (50, None), M7: (90, None)}, M6)


def test_deleting_any_month_never_bills_a_whole_meter():
    rnd = random.Random(9)
    months = [M4, M5, M6, M7]
    for _ in range(5000):
        at, readings = rnd.randint(500, 3000), {}
        for m in months:
            start = at
            at += rnd.randint(0, 300)
            current = at if rnd.random() < 0.7 else None
            first = start if rnd.random() < 0.4 else None
            if current is not None or first is not None:
                readings[m] = (current, first)
        was = calc.reading_starts(months, readings)
        for deleted in months:
            try:
                _, now = after_delete(months, readings, deleted)
            except ValueError:
                continue
            for m in months:
                current = readings.get(m, (None, None))[0]
                if m == deleted or current is None or was[m].previous is None:
                    continue
                assert now[m].previous is not None
                assert current >= now[m].previous
                if m < deleted:
                    assert now[m].previous == was[m].previous
