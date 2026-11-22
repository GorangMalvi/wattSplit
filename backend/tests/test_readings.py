import pytest
from fastapi.testclient import TestClient

from app import calc, db, main

from .test_calc import NAMES, household, month, reading

HID = "00000000-0000-0000-0000-000000000001"
M5, M6, M7, M8 = "2026-05", "2026-06", "2026-07", "2026-08"
MONTHS = [month(M5, 1000, 1500, 5000), month(M6, 1500, 2000, 5000), month(M7, 2000, 2500, 5000)]


def everyone(m, values, starts=(None,) * 4):
    return [reading(m, n, v, s) for n, v, s in zip(NAMES, values, starts)]


MAY = everyone(M5, [1100, 2100, 3100, 4100], [1000, 2000, 3000, 4000])


def row(m, readings, name="B"):
    rows = calc.calculate_month(m, household(MONTHS, readings))["roommates"]
    return next(r for r in rows if r["name"] == name)


# ---- where a month starts

def test_a_skipped_month_counts_from_the_last_known_reading():
    readings = MAY + everyone(M6, [1200, None, 3200, 4200]) + everyone(M7, [1300, 2300, 3300, 4300])
    b = row(M7, readings)
    assert b["previous_reading"] == 2100 and b["sub_units"] == 200  # two months, not the whole meter
    assert b["total_bill"] == pytest.approx(2000)
    assert row(M7, readings, "A")["total_bill"] == pytest.approx(1000)


def test_several_skipped_months():
    starts = calc.reading_starts([M8, M7, M6, M5], {M5: (2100, 2000)})
    assert starts[M8] == (2100, True, 2100)


def test_a_start_reading_beats_the_last_known_one():
    readings = MAY + everyone(M7, [1300, 2300, 3300, 4300], [None, 2250, None, None])
    assert row(M7, readings)["sub_units"] == 50


def test_last_months_reading_beats_a_start_reading():
    assert row(M6, MAY + [reading(M6, "B", 2200, 2150)])["sub_units"] == 100


def test_a_start_without_an_end_carries_forward():
    readings = [reading(M5, "B", None, 2000), reading(M6, "B", 2200)]
    assert row(M6, readings)["sub_units"] == 200


def test_zero_is_a_reading_not_a_blank():
    assert calc.reading_starts([M5, M6], {M5: (0.0, None)})[M6] == (0.0, False, 0.0)


def test_dashboard_counts_the_same_way():
    data = household(MONTHS, MAY + [reading(M7, "B", 2300)])
    june, july = calc.personal_dashboard("B", data)["months"][1:]
    assert june["previous_reading"] == 2100 and not june["previous_editable"]
    assert july["previous_reading"] == july["fallback_reading"] == 2100 and july["previous_editable"]
    assert july["sub_units"] == 200


# ---- saving a reading

@pytest.fixture
def save(monkeypatch):
    """save(history, month, body) -> (response, what was written)."""
    main.app.dependency_overrides[main.current_member] = lambda: main.Member(
        hid=HID, user_id="user-1", role="member", roommate_id=7,
    )

    def run(history, m, body=None, roommate_id=7):
        written = []
        monkeypatch.setattr(db, "roommate_readings", lambda hid, rid: history)
        monkeypatch.setattr(db, "set_reading", lambda *a, **fields: written.append(fields))
        monkeypatch.setattr(db, "delete_reading", lambda *a: written.append("deleted") or True)
        client, url = TestClient(main.app), f"/api/readings/{m}/{roommate_id}"
        return (client.delete(url) if body is None else client.put(url, json=body)), written

    yield run
    main.app.dependency_overrides.clear()


NONE = (None, None)


@pytest.mark.parametrize("history, m, body", [
    ({M5: (2100, None), M6: NONE}, M6, {"current_reading": 1500}),  # below last month
    ({M5: (2100, None), M6: NONE, M7: NONE}, M7, {"current_reading": 1500}),  # below the last known
    ({M5: (2100, None)}, M5, {"start_reading": 2500}),  # start above the end
    ({M5: NONE}, M5, {"start_reading": 2500, "current_reading": 2100}),  # both at once
    ({M5: (2100, None), M6: (2200, None)}, M5, {"current_reading": 2500}),  # above next month
    ({M5: (2100, None), M6: NONE, M7: (2300, None)}, M5, {"current_reading": 2500}),  # above a later one
    ({M5: (2100, None), M6: NONE, M7: (500, 100)}, M7, {"start_reading": None}),  # clearing exposes it
])
def test_rejects_a_meter_running_backwards(save, history, m, body):
    response, written = save(history, m, body)
    assert response.status_code == 422 and "Check" in response.json()["detail"]
    assert written == []


@pytest.mark.parametrize("history, m, body", [
    ({M5: (2100, None), M6: NONE}, M6, {"current_reading": 2100}),  # no units used
    ({M5: (2100, None), M6: NONE, M7: NONE}, M7, {"start_reading": 50, "current_reading": 90}),  # new meter
    ({M5: (2100, None), M6: (2050, None), M7: (2000, None)}, M6, {"current_reading": 2150}),  # fixing old mistakes
    ({M5: (2100, None), M6: (2050, None)}, M6, {"current_reading": None}),  # clearing a bad one
])
def test_accepts_valid_changes_and_corrections(save, history, m, body):
    response, written = save(history, m, body)
    assert response.status_code == 200 and written == [body]


def test_a_first_reading_needs_a_start(save):
    response, written = save({M5: NONE}, M5, {"current_reading": 2100})
    assert response.status_code == 422 and "start reading" in response.json()["detail"]
    assert written == []
    assert save({M5: NONE}, M5, {"current_reading": 2100, "start_reading": 2000})[0].status_code == 200
    assert save({M5: (None, 2000)}, M5, {"current_reading": 2100})[0].status_code == 200


def test_months_saved_before_the_rule(save):
    old = {M5: (2100, None), M6: NONE}
    assert save(old, M5, {"current_reading": 2100})[0].status_code == 200  # unchanged
    assert save(old, M5, {"current_reading": 2150})[0].status_code == 422  # changed: needs a start now
    assert save(old, M5, {"start_reading": 2000})[0].status_code == 200
    assert save(old, M6, {"current_reading": 2200})[0].status_code == 200  # later months aren't stuck


def test_a_start_cannot_be_taken_away(save):
    assert save({M5: (2100, 2000)}, M5, {"start_reading": None})[0].status_code == 422
    history = {M5: (2100, 2000), M6: (2200, None)}
    response, written = save(history, M5)
    assert response.status_code == 422 and "counted from this one" in response.json()["detail"]
    assert written == []


def test_a_start_of_zero_must_be_confirmed(save):
    both = {"start_reading": 0, "current_reading": 90}
    response, written = save({M5: NONE}, M5, both)
    assert response.status_code == 422 and "brand-new" in response.json()["detail"] and written == []
    response, written = save({M5: NONE}, M5, {**both, "new_meter": True})
    assert response.status_code == 200 and written == [both]  # new_meter itself isn't stored


def test_deleting_cannot_make_a_later_month_negative(save):
    history = {M5: (2100, None), M6: (50, None), M7: (90, None)}
    response, written = save(history, M6)
    assert response.status_code == 422 and written == []


def test_deleting_a_reading(save):
    response, written = save({M5: (2100, None)}, M5)
    assert response.status_code == 204 and written == ["deleted"]


def test_missing_month_and_someone_elses_reading(save):
    assert save({M5: NONE}, M6, {"current_reading": 5})[0].status_code == 404
    assert save({M5: NONE}, M5, {"current_reading": 5}, roommate_id=8)[0].status_code == 403
