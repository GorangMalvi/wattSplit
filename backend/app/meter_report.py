"""
Read the prepaid meter provider's "Monthly Grid Consumption Report" (.xlsx).

The file is a PDF table converted to Excel, so values don't sit under their
headers. Its layout:

- each month is two rows of numbers, newest month first. Row one starts with
  grid units opening, closing, consumed and ends with opening amount,
  recharge amount; row two ends with the balance amount (carried forward).
- below them, one row per month with "S.No, YYYY-MM, flat, account", in the
  same order as the number rows.

For each month the meter deducted ``opening amount + recharge - balance``
(energy charge, duty, FPPAS, fixed charges, VCAP, rebates...). That is the
month's bill, so the rate is ``deducted / units consumed``.

Only the first three and last two values of row one and the last value of row
two are used, and every month is cross-checked (units add up, and each month
starts where the previous one ended) so a shifted layout fails loudly rather
than importing wrong numbers.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

import openpyxl


class ReportError(ValueError):
    """The file isn't a consumption report this parser understands."""


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _month_label(value: Any) -> Optional[str]:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m")
    if isinstance(value, str) and MONTH_RE.match(value.strip()):
        return value.strip()
    return None


def _numbers(row: tuple) -> Optional[List[float]]:
    """The row's values if they're all numbers (blank cells skipped), else None."""
    values = [v for v in row if v is not None and not (isinstance(v, str) and not v.strip())]
    if not values or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return None
    return [float(v) for v in values]


def _previous_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    return f"{year - 1:04d}-12" if mon == 1 else f"{year:04d}-{mon - 1:02d}"


def parse(content: bytes) -> List[Dict[str, Any]]:
    """Months in the report, oldest first. Raises ReportError."""
    try:
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    except Exception:
        raise ReportError("This isn't an Excel (.xlsx) file")
    ws = wb.worksheets[0]

    number_rows: List[List[float]] = []
    labels: List[str] = []
    seen_header = False
    for row in ws.iter_rows(values_only=True):
        cells = [c for c in row if c is not None]
        if not seen_header:
            seen_header = any(isinstance(c, str) and c.strip().lower().startswith("s.no") for c in cells)
            continue
        month = next((m for m in map(_month_label, cells) if m), None)
        if month:
            labels.append(month)
        elif labels:
            break  # past the month list: totals etc.
        else:
            numbers = _numbers(row)
            if numbers is not None:
                number_rows.append(numbers)

    if not seen_header or not labels:
        raise ReportError("Couldn't find the month table. Upload the Monthly Consumption Report .xlsx")
    if len(number_rows) != 2 * len(labels):
        raise ReportError(
            f"Found {len(labels)} months but {len(number_rows)} rows of numbers (expected {2 * len(labels)})"
        )

    months = []
    for i, month in enumerate(labels):
        first, second = number_rows[2 * i], number_rows[2 * i + 1]
        if len(first) < 5:
            raise ReportError(f"{month}: too few values in the report row")
        opening_units, closing_units, units = first[0], first[1], first[2]
        opening_amount, recharge = first[-2], first[-1]
        balance = second[-1]
        if abs(closing_units - opening_units - units) > 0.5:
            raise ReportError(f"{month}: opening/closing units don't match units consumed")
        months.append({
            "month": month,
            "main_start_reading": opening_units,
            "main_end_reading": closing_units,
            "units": units,
            "energy_charge": first[3] if len(first) > 5 else None,
            "meter_opening_balance": opening_amount,
            "meter_recharge": recharge,
            "meter_closing_balance": balance,
            "monthly_bill": round(opening_amount + recharge - balance, 2),
        })

    months.sort(key=lambda m: m["month"])
    if len({m["month"] for m in months}) != len(months):
        raise ReportError("The report lists the same month twice")
    for prev, cur in zip(months, months[1:]):
        if _previous_month(cur["month"]) != prev["month"]:
            continue  # gap in the report: nothing to cross-check
        if abs(cur["main_start_reading"] - prev["main_end_reading"]) > 0.5:
            raise ReportError(f"{cur['month']}: opening units don't match {prev['month']} closing units")
        if abs(cur["meter_opening_balance"] - prev["meter_closing_balance"]) > 0.01:
            raise ReportError(f"{cur['month']}: opening amount doesn't match {prev['month']} balance")
    for m in months:
        if m["monthly_bill"] < 0:
            raise ReportError(f"{m['month']}: works out to a negative amount deducted")
    return months
