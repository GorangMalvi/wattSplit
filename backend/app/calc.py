"""
Bill-splitting logic per the spec formula.
"""
from __future__ import annotations

from calendar import monthrange
from typing import Any, Dict, List, Optional

import pandas as pd

from . import db


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


def calculate_month(month: str) -> Dict[str, Any]:
    """
    Calculate the full split for ``month``.

    Returns a dict matching ``MonthCalculation`` in ``models.py``.
    """
    month_row = db.get_month(month)
    if month_row is None:
        raise ValueError(f"Month {month} not found")

    monthly_bill = float(month_row["monthly_bill"]) if pd.notna(month_row["monthly_bill"]) else 0.0
    dg_bill = float(month_row["dg_bill"]) if pd.notna(month_row["dg_bill"]) else 0.0
    main_start = float(month_row["main_start_reading"]) if pd.notna(month_row["main_start_reading"]) else 0.0
    main_end = float(month_row["main_end_reading"]) if pd.notna(month_row["main_end_reading"]) else main_start

    main_units = main_end - main_start

    readings_df = db.get_readings(month)
    if readings_df.empty:
        raise ValueError(f"No readings found for {month}")

    roommates_df = db.get_roommates()

    prev_month = db.get_previous_month(month)
    prev_readings: Dict[str, float] = {}
    if prev_month:
        prev_df = db.get_readings(prev_month)
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
        active_rows.append((name, float(r["current_reading"])))

    active_count = len(active_rows)
    if active_count == 0:
        raise ValueError(f"No active roommates for {month}")

    sum_sub_units = 0.0
    split_rows: List[Dict[str, Any]] = []
    for name, current in active_rows:
        previous = prev_readings.get(name)
        if previous is None:
            # No prior reading => treat the whole current reading as consumption.
            # This only happens for the very first month of a roommate.
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

    # Recharges for this month only.
    recharges_df = db.get_recharges()
    month_start = f"{month}-01"
    month_end = _month_end_date(month)
    month_recharges: Dict[str, float] = {}
    for _, rec in recharges_df.iterrows():
        name = str(rec["roommate"]).strip()
        amount = float(rec["amount"]) if pd.notna(rec["amount"]) else 0.0
        date = str(rec["date"]) if pd.notna(rec["date"]) else ""
        if month_start <= date <= month_end:
            month_recharges[name] = month_recharges.get(name, 0.0) + amount

    for row in split_rows:
        total_units = row["sub_units"] + common_share
        energy_charge = total_units * rate
        total_bill = energy_charge + dg_share
        rec = month_recharges.get(row["roommate"], 0.0)
        row.update({
            "common_share": common_share,
            "total_units": total_units,
            "energy_charge": energy_charge,
            "dg_share": dg_share,
            "total_bill": total_bill,
            "recharges": rec,
            "balance": total_bill - rec,
        })

    # Running (cumulative) balances up to and including this month.
    all_months = sorted(db.get_months()["month"].dropna().astype(str).tolist())
    running: Dict[str, Dict[str, float]] = {}
    for m in all_months:
        if m > month:
            break
        mrow = db.get_month(m)
        if mrow is None:
            continue
        m_monthly = float(mrow["monthly_bill"]) if pd.notna(mrow["monthly_bill"]) else 0.0
        m_dg = float(mrow["dg_bill"]) if pd.notna(mrow["dg_bill"]) else 0.0
        m_readings = db.get_readings(m)
        m_roommates = set(m_readings["roommate"].dropna().astype(str).tolist())
        m_count = len(m_roommates)
        if m_count == 0:
            continue
        m_end = _month_end_date(m)
        for rname in m_roommates:
            cur = db.get_reading(m, rname)
            if cur is None:
                continue
            prev = db.get_reading(db.get_previous_month(m) or "", rname) if db.get_previous_month(m) else None
            sub = cur if prev is None else cur - prev
            # Use the monthly bill/dg from that month; approximate main units
            # from the stored main readings.
            ms = float(mrow["main_start_reading"]) if pd.notna(mrow["main_start_reading"]) else 0.0
            me = float(mrow["main_end_reading"]) if pd.notna(mrow["main_end_reading"]) else ms
            mu = me - ms
            cu = mu - sub  # rough common units for that month
            if cu < 0:
                cu = 0.0
            r = m_monthly / mu if mu else 0.0
            share = cu / m_count
            energy = (sub + share) * r
            dgs = m_dg / m_count
            tb = energy + dgs
            if rname not in running:
                running[rname] = {"total_bill": 0.0, "recharges": 0.0}
            running[rname]["total_bill"] += tb

        # Recharges up to the end of this month.
        for _, rec in recharges_df.iterrows():
            date = str(rec["date"]) if pd.notna(rec["date"]) else ""
            if date <= m_end:
                rname = str(rec["roommate"]).strip()
                amount = float(rec["amount"]) if pd.notna(rec["amount"]) else 0.0
                if rname not in running:
                    running[rname] = {"total_bill": 0.0, "recharges": 0.0}
                running[rname]["recharges"] += amount

    running_balances = []
    for name in sorted(running.keys()):
        total_bill = round(running[name]["total_bill"], 2)
        recharges = round(running[name]["recharges"], 2)
        running_balances.append({
            "roommate": name,
            "total_bill_cumulative": total_bill,
            "total_recharges_cumulative": recharges,
            "balance": round(total_bill - recharges, 2),
        })

    # ------------------------------------------------------------------
    # Shape response for the frontend.
    # ------------------------------------------------------------------
    summary = {
        "main_units": main_units,
        "rate_per_unit": rate,
        "total_bill": monthly_bill + dg_bill,
        "dg_bill": dg_bill,
    }

    frontend_roommates = []
    for row in split_rows:
        rid = db.get_roommate_id_by_name(row["roommate"])
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
        })

    frontend_running = []
    for b in running_balances:
        rid = db.get_roommate_id_by_name(b["roommate"])
        if rid is None:
            # Skip non-roommate entries such as "DG".
            continue
        frontend_running.append({
            "roommate_id": rid,
            "name": b["roommate"],
            "total_bill_cumulative": b["total_bill_cumulative"],
            "total_recharges_cumulative": b["total_recharges_cumulative"],
            "balance": b["balance"],
        })

    return {
        "month": month,
        "summary": summary,
        "roommates": frontend_roommates,
        "running_balances": frontend_running,
    }
