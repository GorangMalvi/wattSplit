import pandas as pd
import pytest

from app import calc, db

NAMES = ["A", "B", "C", "D"]


def household(months, readings):
    """A HouseholdData built in memory (no database)."""
    data = object.__new__(db.HouseholdData)
    roommates = [{"id": i + 1, "name": n, "join_date": "2026-05", "leave_date": "", "is_active": True, "linked": False}
                 for i, n in enumerate(NAMES)]
    data.roommate_rows, data.recharge_rows = roommates, []
    data.roommates = pd.DataFrame(roommates, columns=db.ROOMMATE_COLS)
    data.months = pd.DataFrame(months, columns=db.MONTH_COLS)
    data.readings = pd.DataFrame(readings, columns=db.READING_COLS)
    data.recharges = pd.DataFrame([], columns=db.RECHARGE_COLS)
    return data


def month(m, start, end, bill):
    return {"month": m, "main_start_reading": start, "main_end_reading": end, "monthly_bill": bill, "dg_bill": 0}


def reading(m, name, current, start=None):
    return {"month": m, "roommate_id": NAMES.index(name) + 1, "roommate": name,
            "current_reading": current, "start_reading": start}


MAY = [month("2026-05", 27485, 28742, 9628)]
MAY_READINGS = [
    reading("2026-05", "A", 1866, 1696),
    reading("2026-05", "B", 3172, 2802),
    reading("2026-05", "C", 3281, 2992),
    reading("2026-05", "D", 4300, 3874),
]


def test_common_units_in_the_summary():
    result = calc.calculate_month("2026-05", household(MAY, MAY_READINGS))
    s = result["summary"]
    assert s["main_units"] == 1257
    assert s["sub_units_total"] == 1255  # 170 + 370 + 289 + 426
    assert s["common_units"] == 2
    assert s["common_share"] == 0.5
    assert s["active_roommates"] == 4
    bills = {r["name"]: round(r["total_bill"], 2) for r in result["roommates"]}
    assert bills == {"A": 1305.95, "B": 2837.85, "C": 2217.43, "D": 3266.78}
    # Unrounded, the bills add up to the meter bill exactly (rounded ones can be a paisa off).
    assert sum(r["total_bill"] for r in result["roommates"]) == pytest.approx(9628)


def test_next_month_starts_from_last_months_end_readings():
    june = MAY + [month("2026-06", 28742, 29900, 9000)]
    june_readings = MAY_READINGS + [  # only end readings: no start readings for June
        reading("2026-06", "A", 2000),
        reading("2026-06", "B", 3500),
        reading("2026-06", "C", 3550),
        reading("2026-06", "D", 4700),
    ]
    rows = {r["name"]: r for r in calc.calculate_month("2026-06", household(june, june_readings))["roommates"]}
    assert {n: r["previous_reading"] for n, r in rows.items()} == {"A": 1866, "B": 3172, "C": 3281, "D": 4300}
    assert {n: r["sub_units"] for n, r in rows.items()} == {"A": 134, "B": 328, "C": 269, "D": 400}
    s = calc.calculate_month("2026-06", household(june, june_readings))["summary"]
    assert s["main_units"] == 1158 and s["common_units"] == pytest.approx(1158 - 1131)


# June 2026 (104_aims_boys): sub-meters read days after the main meter's report,
# so they show 1,415 units against the main meter's 1,258.
JUNE = MAY + [month("2026-06", 28742, 30000, 10671)]
JUNE_READINGS = MAY_READINGS + [
    reading("2026-06", "A", 2045),
    reading("2026-06", "B", 3538),
    reading("2026-06", "C", 3467),
    reading("2026-06", "D", 4984),
]


def test_sub_meters_above_main_split_the_real_bill_by_own_units():
    result = calc.calculate_month("2026-06", household(JUNE, JUNE_READINGS))
    s = result["summary"]
    assert s["main_units"] == 1258 and s["sub_units_total"] == 1415
    assert s["units_mismatch"] == 157
    assert s["common_units"] == 0 and s["common_share"] == 0
    assert s["rate_per_unit"] == pytest.approx(10671 / 1415)  # not 10671 / 1258
    bills = {r["name"]: round(r["total_bill"], 2) for r in result["roommates"]}
    assert bills == {"A": 1349.90, "B": 2760.13, "C": 1402.69, "D": 5158.28}
    assert sum(r["total_bill"] for r in result["roommates"]) == pytest.approx(10671)


def test_no_mismatch_reported_when_sub_meters_fit():
    assert calc.calculate_month("2026-05", household(MAY, MAY_READINGS))["summary"]["units_mismatch"] == 0


def test_missing_main_readings_still_bill_the_whole_amount():
    no_main = [month("2026-05", 27485, 27485, 9628)]  # end reading not entered yet
    result = calc.calculate_month("2026-05", household(no_main, MAY_READINGS))
    assert sum(r["total_bill"] for r in result["roommates"]) == pytest.approx(9628)
