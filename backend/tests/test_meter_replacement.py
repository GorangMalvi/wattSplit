import random
from io import BytesIO

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app import calc, db, export, main

from .test_calc import household, month, reading

M4, M5, M6, M7 = "2026-04", "2026-05", "2026-06", "2026-07"
MONTHS = [month(M5, 1000, 1200, 2000), month(M6, 1200, 1400, 2000), month(M7, 1400, 1600, 2000)]

# B's meter reached 2100 in May. In June it was replaced at 2160: the new one
# started at 5 and read 45 at month end, so June is 60 + 40 = 100 units.
MAY, REPLACED = (2100, 2000, None), (45, 5, 2160)


def flat(june=REPLACED, july=None):
    rows = [reading(M5, "A", 1100, 1000), reading(M5, "B", 2100, 2000), reading(M6, "A", 1200)]
    current, start, old_final = june
    rows.append({**reading(M6, "B", current, start), "old_meter_final": old_final})
    if july is not None:
        rows += [reading(M7, "A", 1300), reading(M7, "B", july)]
    return household(MONTHS, rows)


def split(m, data):
    return {r["name"]: r for r in calc.calculate_month(m, data)["roommates"]}


def test_bills_both_meters_in_the_month_it_was_replaced():
    b = split(M6, flat())["B"]
    assert b["previous_reading"] == 2100 and b["current_reading"] == 45
    assert b["sub_units"] == 100 and b["total_bill"] == pytest.approx(1000)


def test_later_months_count_from_the_new_meter():
    b = split(M7, flat(july=145))["B"]
    assert b["previous_reading"] == 45 and b["sub_units"] == 100


def test_replaced_after_a_skipped_month():
    starts = calc.reading_starts([M5, M6, M7], {M5: MAY, M7: (45, 5, 2160)})
    assert starts[M7] == (2100, False, 2100)  # not the new meter's start
    assert calc.units_used(calc.Reading(45, 5, 2160), starts[M7].previous) == 100


def test_dashboard_agrees():
    june = calc.personal_dashboard("B", flat())["months"][1]
    assert june["sub_units"] == 100 and june["old_meter_final"] == 2160
    assert june["previous_reading"] == 2100 and not june["previous_editable"]


def test_excel_report_says_so():
    data = flat()
    sheet = openpyxl.load_workbook(BytesIO(export.generate_month_report(M6, data))).active
    text = " ".join(str(c.value) for row in sheet.iter_rows() for c in row if c.value is not None)
    assert "B's meter was replaced" in text and "2160" in text


@pytest.fixture
def save(monkeypatch):
    main.app.dependency_overrides[main.current_member] = lambda: main.Member(
        hid="00000000-0000-0000-0000-000000000001", user_id="user-b", role="member", roommate_id=7,
    )

    def run(history, m, body=None, fail=None):
        written = []

        def write(*args, **fields):
            if fail:
                raise fail
            written.append(fields)

        monkeypatch.setattr(db, "roommate_readings", lambda hid, rid: history)
        monkeypatch.setattr(db, "set_reading", write)
        monkeypatch.setattr(db, "delete_reading", lambda *a: written.append("deleted") or True)
        client, url = TestClient(main.app), f"/api/readings/{m}/7"
        return (client.delete(url) if body is None else client.put(url, json=body)), written

    yield run
    main.app.dependency_overrides.clear()


NONE = (None, None, None)
REPLACE = {"old_meter_final": 2160, "start_reading": 5, "current_reading": 45}


def test_records_a_replacement(save):
    response, written = save({M5: MAY, M6: NONE}, M6, REPLACE)
    assert response.status_code == 200 and written == [REPLACE]


def test_a_new_meter_at_zero_is_confirmed(save):
    body = {**REPLACE, "start_reading": 0}
    assert save({M5: MAY, M6: NONE}, M6, body)[0].status_code == 422
    assert save({M5: MAY, M6: NONE}, M6, {**body, "new_meter": True})[0].status_code == 200


@pytest.mark.parametrize("history, m, body", [
    ({M5: MAY, M6: NONE}, M6, {**REPLACE, "old_meter_final": 2090}),  # old meter ran backwards
    ({M5: MAY, M6: NONE}, M6, {**REPLACE, "current_reading": 3}),  # new meter ran backwards
    ({M5: MAY, M6: NONE}, M6, {"old_meter_final": 2160, "start_reading": 5}),  # no month-end
    ({M5: MAY, M6: NONE}, M6, {"old_meter_final": 2160, "current_reading": 2200}),  # no new start
    ({M5: NONE}, M5, REPLACE),  # nothing on the old meter to count from
    ({M5: MAY, M6: REPLACED}, M5, {"current_reading": 2170}),  # May above the old meter's last
    ({M5: MAY, M6: REPLACED}, M6, {"current_reading": None}),  # half a replacement
    ({M5: MAY, M6: REPLACED}, M6, {"old_meter_final": None}),  # 45 is no reading of the old meter
    ({M5: MAY, M6: REPLACED, M7: (145, None, None)}, M6, {"old_meter_final": None, "current_reading": None}),
])
def test_rejects(save, history, m, body):
    response, written = save(history, m, body)
    assert response.status_code == 422 and written == []


def test_a_replacement_recorded_late_fixes_the_month(save):
    stuck = {M5: MAY, M6: (None, None, None), M7: NONE}
    assert save(stuck, M6, REPLACE)[0].status_code == 200


def test_editing_the_new_meters_reading(save):
    assert save({M5: MAY, M6: REPLACED}, M6, {"current_reading": 50})[0].status_code == 200


def test_it_was_not_replaced(save):
    response, written = save({M5: MAY, M6: REPLACED}, M6, {"old_meter_final": None, "current_reading": None})
    assert response.status_code == 200
    assert written == [{"old_meter_final": None, "current_reading": None, "start_reading": None}]


def test_deleting_the_reading(save):
    assert save({M5: MAY, M6: REPLACED}, M6)[0].status_code == 204
    assert save({M5: MAY, M6: REPLACED, M7: (145, None, None)}, M6)[0].status_code == 422


def test_before_the_column_exists(save):
    response, _ = save({M5: MAY, M6: NONE}, M6, REPLACE, fail=db.SchemaBehind())
    assert response.status_code == 503 and "database" in response.json()["detail"]
    # Clearing what was never set doesn't touch the column.
    response, written = save({M5: MAY, M6: NONE}, M6, {"current_reading": 2200, "old_meter_final": None})
    assert response.status_code == 200 and written == [{"current_reading": 2200}]


def test_deleting_months_around_a_replacement():
    months = [M4, M5, M6, M7]
    with pytest.raises(ValueError, match="can't be deleted"):  # later readings are on the new meter
        calc.starts_to_keep(months, {M5: MAY, M6: REPLACED, M7: (145, None, None)}, M6)
    with pytest.raises(ValueError, match="can't be deleted"):  # nothing left for the old meter to count from
        calc.starts_to_keep([M5, M6], {M5: MAY, M6: REPLACED}, M5)
    assert calc.starts_to_keep([M5, M6], {M5: MAY, M6: REPLACED}, M6) == {}
    middle = {M4: (2050, 2000, None), M5: (2100, None, None), M6: REPLACED}
    assert calc.starts_to_keep([M4, M5, M6], middle, M5) == {}


def test_units_always_add_up_to_what_was_used():
    """Whatever is skipped, replaced or deleted, nobody is billed units they didn't use."""
    rnd = random.Random(3)
    months = [M4, M5, M6, M7]
    for _ in range(20000):
        meter = rnd.randint(0, 3000)
        readings, true_used, billed_upto, used = {}, {}, 0, 0
        for i, m in enumerate(months):
            before_month = meter
            grow = rnd.randint(0, 300)
            if i and rnd.random() < 0.3:
                part = rnd.randint(0, grow)
                old_last, new_start = meter + part, rnd.randint(0, 50)
                meter = new_start + grow - part
                readings[m] = (meter, new_start, old_last)
            else:
                meter += grow
                if i == 0 or rnd.random() < 0.7:
                    readings[m] = (meter, before_month if i == 0 else None, None)
            used += grow
            if m in readings:
                true_used[m], billed_upto = used - billed_upto, used
        starts = calc.reading_starts(months, readings)
        for m, values in readings.items():
            assert calc.units_used(calc.Reading(*values), starts[m].previous) == true_used[m]

        deleted = rnd.choice(months[1:])
        try:
            kept = calc.starts_to_keep(months, readings, deleted)
        except ValueError:
            continue
        assert kept == {}
        after = {m: v for m, v in readings.items() if m != deleted}
        now = calc.reading_starts([m for m in months if m != deleted], after)
        total = sum(calc.units_used(calc.Reading(*v), now[m].previous) for m, v in after.items())
        last = max(after)
        assert total == sum(u for m, u in true_used.items() if m <= last)
