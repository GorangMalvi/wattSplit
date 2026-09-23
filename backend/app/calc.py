"""
Bill-splitting logic per the spec formula.
"""
from __future__ import annotations

from calendar import monthrange
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .db import HouseholdData


def _month_end_date(month: str) -> str:
    """Return the last day of ``month`` (YYYY-MM) as YYYY-MM-DD."""
    year, mon = int(month[:4]), int(month[5:7])
    last_day = monthrange(year, mon)[1]
    return f"{year:04d}-{mon:02d}-{last_day:02d}"


def _roommate_is_active(roommate: str, month: str, roommates_df: pd.DataFrame) -> bool:
    """
    A roommate is active for a given month if they are marked active and
    their join/leave dates (when present) bracket the month.
    """
    row = roommates_df[roommates_df["name"] == roommate]
    if row.empty:
        return True  # Default to active if not in registry.
    r = row.iloc[0]
    if not bool(r.get("is_active", True)):
        # If a leave_date is set, allow participation up to that month.
        leave = str(r.get("leave_date") or "").strip()
        if leave and month <= leave:
            return True
        return False

    join = str(r.get("join_date") or "").strip()
    leave = str(r.get("leave_date") or "").strip()
    if join and month < join:
        return False
    if leave and month > leave:
        return False
    return True


def _split_month(month: str, data: HouseholdData) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Split ``month``'s bill between the roommates active that month.

    Returns ``(summary, rows)``, one row per roommate keyed by name.
    Raises ValueError when the month is missing or has no usable readings.
    """
    month_row = data.get_month(month)
    if month_row is None:
        raise ValueError(f"Month {month} not found")

    monthly_bill = float(month_row["monthly_bill"]) if pd.notna(month_row["monthly_bill"]) else 0.0
    dg_bill = float(month_row["dg_bill"]) if pd.notna(month_row["dg_bill"]) else 0.0
    main_start = float(month_row["main_start_reading"]) if pd.notna(month_row["main_start_reading"]) else 0.0
    main_end = float(month_row["main_end_reading"]) if pd.notna(month_row["main_end_reading"]) else main_start

    main_units = main_end - main_start

    readings_df = data.get_readings(month)
    if readings_df.empty:
        raise ValueError(f"No readings found for {month}")

    roommates_df = data.get_roommates()

    prev_month = data.get_previous_month(month)
    prev_readings: Dict[str, float] = {}
    if prev_month:
        prev_df = data.get_readings(prev_month)
        for _, r in prev_df.iterrows():
            if pd.notna(r["current_reading"]):
                prev_readings[str(r["roommate"])] = float(r["current_reading"])

    # Active roommates = those with a current reading and still active this month.
    active_rows = []
    for _, r in readings_df.iterrows():
        name = str(r["roommate"]).strip()
        if pd.isna(r["current_reading"]):
            continue
        if not _roommate_is_active(name, month, roommates_df):
            continue
        # Start of the month: last month's reading, else the start reading entered.
        start = r.get("start_reading")
        if name not in prev_readings and start is not None and pd.notna(start):
            prev_readings[name] = float(start)
        active_rows.append((name, float(r["current_reading"])))

    active_count = len(active_rows)
    if active_count == 0:
        raise ValueError(f"No active roommates for {month}")

    sum_sub_units = 0.0
    split_rows: List[Dict[str, Any]] = []
    for name, current in active_rows:
        previous = prev_readings.get(name)
        if previous is None:
            # No prior or start reading => treat the whole current reading as
            # consumption (a first month entered without a start reading).
            sub_units = current
        else:
            sub_units = current - previous
        sum_sub_units += sub_units
        split_rows.append({
            "roommate": name,
            "previous_reading": previous,
            "current_reading": current,
            "sub_units": sub_units,
        })

    common_units = main_units - sum_sub_units
    if common_units < 0:
        # Main meter is lower than the sum of sub-meters; clamp to zero.
        common_units = 0.0
    common_share = common_units / active_count

    rate = monthly_bill / main_units if main_units else 0.0
    dg_share = dg_bill / active_count

    # Recharges for this month only, per meter.
    recharges_df = data.get_recharges()
    month_start = f"{month}-01"
    month_end = _month_end_date(month)
    month_recharges: Dict[str, Dict[str, float]] = {}
    for _, rec in recharges_df.iterrows():
        name = str(rec["roommate"]).strip()
        amount = float(rec["amount"]) if pd.notna(rec["amount"]) else 0.0
        date = str(rec["date"]) if pd.notna(rec["date"]) else ""
        if month_start <= date <= month_end:
            paid = month_recharges.setdefault(name, {"main": 0.0, "dg": 0.0})
            paid[_meter(rec)] += amount

    for row in split_rows:
        total_units = row["sub_units"] + common_share
        energy_charge = total_units * rate
        total_bill = energy_charge + dg_share
        paid = month_recharges.get(row["roommate"], {"main": 0.0, "dg": 0.0})
        rec = paid["main"] + paid["dg"]
        row.update({
            "common_share": common_share,
            "total_units": total_units,
            "energy_charge": energy_charge,
            "dg_share": dg_share,
            "total_bill": total_bill,
            "recharges": rec,
            "balance": total_bill - rec,
            # Main meter: energy charge vs main payments; DG: DG share vs DG payments.
            "recharges_main": paid["main"],
            "recharges_dg": paid["dg"],
            "main_balance": energy_charge - paid["main"],
            "dg_balance": dg_share - paid["dg"],
        })

    summary = {
        "main_units": main_units,
        "rate_per_unit": rate,
        "total_bill": monthly_bill + dg_bill,
        "dg_bill": dg_bill,
    }
    return summary, split_rows


def running_balances(data: HouseholdData, upto: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Cumulative bill, payments and balance per roommate: the sum of every
    month's split up to ``upto`` (YYYY-MM) and every recharge dated on or
    before the end of that month. ``upto=None`` means all months and all
    recharges so far.
    """
    totals: Dict[str, Dict[str, float]] = {}

    def entry(name: str) -> Dict[str, float]:
        return totals.setdefault(name, {"main_bill": 0.0, "dg_bill": 0.0, "main": 0.0, "dg": 0.0})

    for m in sorted(data.get_months()["month"].dropna().astype(str).tolist()):
        if upto is not None and m > upto:
            break
        try:
            _, rows = _split_month(m, data)
        except ValueError:
            continue  # month without readings yet: nothing billed
        for row in rows:
            e = entry(row["roommate"])
            e["main_bill"] += row["energy_charge"]
            e["dg_bill"] += row["dg_share"]

    last_day = _month_end_date(upto) if upto is not None else None
    for _, rec in data.get_recharges().iterrows():
        date = str(rec["date"]) if pd.notna(rec["date"]) else ""
        if last_day is not None and date > last_day:
            continue
        amount = float(rec["amount"]) if pd.notna(rec["amount"]) else 0.0
        entry(str(rec["roommate"]).strip())[_meter(rec)] += amount

    balances = []
    for name in sorted(totals):
        t = totals[name]
        main_bill, dg_bill = round(t["main_bill"], 2), round(t["dg_bill"], 2)
        main_paid, dg_paid = round(t["main"], 2), round(t["dg"], 2)
        total_bill = round(t["main_bill"] + t["dg_bill"], 2)
        recharges = round(t["main"] + t["dg"], 2)
        balances.append({
            "roommate": name,
            "total_bill_cumulative": total_bill,
            "total_recharges_cumulative": recharges,
            "balance": round(total_bill - recharges, 2),
            "main_bill_cumulative": main_bill,
            "main_recharges_cumulative": main_paid,
            "main_balance": round(main_bill - main_paid, 2),
            "dg_bill_cumulative": dg_bill,
            "dg_recharges_cumulative": dg_paid,
            "dg_balance": round(dg_bill - dg_paid, 2),
        })
    return balances


def _meter(rec: Any) -> str:
    """Which meter a recharge row paid for; rows from before the column existed are main."""
    return "dg" if rec.get("meter") == "dg" else "main"


def calculate_month(month: str, data: HouseholdData) -> Dict[str, Any]:
    """
    Calculate the full split for ``month``.

    Returns a dict matching ``MonthCalculation`` in ``models.py``.
    """
    summary, split_rows = _split_month(month, data)

    # ------------------------------------------------------------------
    # Shape response for the frontend.
    # ------------------------------------------------------------------
    frontend_roommates = []
    for row in split_rows:
        rid = data.get_roommate_id_by_name(row["roommate"])
        if rid is None:
            # Should not happen for active roommates, but guard anyway.
            continue
        frontend_roommates.append({
            "roommate_id": rid,
            "name": row["roommate"],
            "previous_reading": row["previous_reading"],
            "current_reading": row["current_reading"],
            "sub_units": row["sub_units"],
            "common_share": row["common_share"],
            "total_units": row["total_units"],
            "energy_charge": row["energy_charge"],
            "dg_share": row["dg_share"],
            "total_bill": row["total_bill"],
            "recharges": row["recharges"],
            "balance": row["balance"],
            "recharges_main": row["recharges_main"],
            "recharges_dg": row["recharges_dg"],
            "main_balance": row["main_balance"],
            "dg_balance": row["dg_balance"],
        })

    return {
        "month": month,
        "summary": summary,
        "roommates": frontend_roommates,
        "running_balances": household_balances(data, upto=month),
    }


def household_balances(data: HouseholdData, upto: Optional[str] = None) -> List[Dict[str, Any]]:
    """``running_balances`` shaped for the frontend (``RunningBalance`` in models.py)."""
    shaped = []
    for b in running_balances(data, upto):
        rid = data.get_roommate_id_by_name(b["roommate"])
        if rid is None:
            # Skip non-roommate entries such as "DG".
            continue
        shaped.append({"roommate_id": rid, "name": b["roommate"],
                       **{k: v for k, v in b.items() if k != "roommate"}})
    return shaped


def personal_dashboard(roommate: str, data: HouseholdData) -> Dict[str, Any]:
    """
    One roommate's view of every month: their readings, their split of the
    bill once it can be calculated, what they paid, and the balance to date.
    """
    recharges_df = data.get_recharges()
    mine = recharges_df[recharges_df["roommate"] == roommate]

    months = []
    for m in sorted(data.get_months()["month"].dropna().astype(str).tolist()):
        prev_month = data.get_previous_month(m)
        carried = data.get_reading(prev_month, roommate) if prev_month else None
        start = data.get_start_reading(m, roommate)
        previous = carried if carried is not None else start
        current = data.get_reading(m, roommate)
        this_month = mine[mine["date"].astype(str).str.startswith(m)]
        is_dg = this_month["meter"] == "dg"
        paid_dg = float(this_month[is_dg]["amount"].sum())
        paid_main = float(this_month[~is_dg]["amount"].sum())
        paid = paid_main + paid_dg
        row: Dict[str, Any] = {
            "month": m,
            "previous_reading": previous,
            # No reading last month: the start reading can be entered for this month.
            "previous_editable": carried is None,
            "start_reading": start,
            "current_reading": current,
            "sub_units": None if current is None else (current if previous is None else current - previous),
            "is_active": _roommate_is_active(roommate, m, data.get_roommates()),
            "billed": False,
            "rate_per_unit": None,
            "common_share": None,
            "total_units": None,
            "energy_charge": None,
            "dg_share": None,
            "total_bill": None,
            "recharges": paid,
            "recharges_main": paid_main,
            "recharges_dg": paid_dg,
            "balance": None,
            "main_balance": None,
            "dg_balance": None,
        }
        try:
            summary, split_rows = _split_month(m, data)
        except ValueError:
            split_rows = []
        split = next((r for r in split_rows if r["roommate"] == roommate), None)
        if split is not None:
            row.update({
                "billed": True,
                "rate_per_unit": summary["rate_per_unit"],
                "sub_units": split["sub_units"],
                "common_share": split["common_share"],
                "total_units": split["total_units"],
                "energy_charge": split["energy_charge"],
                "dg_share": split["dg_share"],
                "total_bill": split["total_bill"],
                "balance": split["total_bill"] - paid,
                "main_balance": split["energy_charge"] - paid_main,
                "dg_balance": split["dg_share"] - paid_dg,
            })
        months.append(row)

    totals = next((b for b in running_balances(data) if b["roommate"] == roommate), None)
    if totals is None:  # nothing billed or paid yet
        totals = {k: 0.0 for k in TOTAL_KEYS}
    return {"months": months, **{k: totals[k] for k in TOTAL_KEYS}}


TOTAL_KEYS = [
    "total_bill_cumulative", "total_recharges_cumulative", "balance",
    "main_bill_cumulative", "main_recharges_cumulative", "main_balance",
    "dg_bill_cumulative", "dg_recharges_cumulative", "dg_balance",
]
