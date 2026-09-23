"""
SQLite-backed database helpers.

The database file is ``data/bills.db``. All functions return pandas DataFrames
or Series so the rest of the codebase (calc, export, API) remains unchanged.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR.parent / "data"
EXPORTS_DIR = APP_DIR.parent / "exports"
DB_PATH = DATA_DIR / "bills.db"
# Kept for the optional Excel migration script.
EXCEL_PATH = DATA_DIR / "bills.xlsx"


# ---------------------------------------------------------------------------
# Low-level SQLite helpers
# ---------------------------------------------------------------------------
def ensure_directories() -> None:
    """Create data and exports directories if missing."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row factory enabled."""
    ensure_directories()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(force: bool = False) -> Path:
    """
    Create the SQLite database and tables if they do not exist.
    Returns the path to the database file.
    """
    ensure_directories()

    if DB_PATH.exists() and not force:
        return DB_PATH

    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS roommates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            join_date TEXT DEFAULT '',
            leave_date TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS months (
            month TEXT PRIMARY KEY,
            main_start_reading REAL DEFAULT 0,
            main_end_reading REAL DEFAULT 0,
            monthly_bill REAL DEFAULT 0,
            dg_bill REAL DEFAULT 0,
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS readings (
            month TEXT NOT NULL,
            roommate TEXT NOT NULL,
            current_reading REAL NOT NULL,
            PRIMARY KEY (month, roommate)
        );

        CREATE TABLE IF NOT EXISTS recharges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            roommate TEXT NOT NULL,
            amount REAL NOT NULL,
            notes TEXT DEFAULT ''
        );
    """)

    conn.commit()
    conn.close()
    return DB_PATH


def _df_from_query(query: str, params: tuple = ()) -> pd.DataFrame:
    """Run a query and return a DataFrame."""
    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()
    return df


def _execute(query: str, params: tuple = ()) -> int:
    """Run a write query and return the last row id."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Roommates
# ---------------------------------------------------------------------------
def get_roommates() -> pd.DataFrame:
    df = _df_from_query("SELECT id, name, join_date, leave_date, is_active FROM roommates ORDER BY id")
    if not df.empty:
        df["is_active"] = df["is_active"].astype(bool)
    return df


def add_roommate(name: str, join_date: Optional[str] = None,
                 leave_date: Optional[str] = None, is_active: bool = True) -> int:
    rid = _execute(
        "INSERT INTO roommates (name, join_date, leave_date, is_active) VALUES (?, ?, ?, ?)",
        (name, join_date or "", leave_date or "", 1 if is_active else 0),
    )
    return rid


def update_roommate(rid: int, **kwargs) -> bool:
    allowed = {"name", "join_date", "leave_date", "is_active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    if "is_active" in updates:
        updates["is_active"] = 1 if updates["is_active"] else 0
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = tuple(updates.values()) + (rid,)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE roommates SET {set_clause} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_roommate_names() -> List[str]:
    df = get_roommates()
    return df["name"].dropna().astype(str).tolist()


def get_roommate_id_by_name(name: str) -> Optional[int]:
    df = _df_from_query("SELECT id FROM roommates WHERE name = ?", (name,))
    if df.empty:
        return None
    return int(df.iloc[0]["id"])


def get_roommate_name_by_id(rid: int) -> Optional[str]:
    df = _df_from_query("SELECT name FROM roommates WHERE id = ?", (rid,))
    if df.empty:
        return None
    return str(df.iloc[0]["name"])


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------
def get_months() -> pd.DataFrame:
    return _df_from_query(
        "SELECT month, main_start_reading, main_end_reading, monthly_bill, dg_bill, notes FROM months ORDER BY month"
    )


def get_month(month: str) -> Optional[pd.Series]:
    df = _df_from_query(
        "SELECT month, main_start_reading, main_end_reading, monthly_bill, dg_bill, notes FROM months WHERE month = ?",
        (month,),
    )
    if df.empty:
        return None
    return df.iloc[0]


def add_month(month: str, monthly_bill: float, dg_bill: float = 0.0,
              main_start_reading: Optional[float] = None,
              main_end_reading: Optional[float] = None,
              notes: Optional[str] = None) -> None:
    if get_month(month) is not None:
        raise ValueError(f"Month {month} already exists")

    # Auto-carry main start reading from previous month if not supplied.
    if main_start_reading is None:
        prev = get_previous_month(month)
        if prev is not None:
            prev_row = get_month(prev)
            if prev_row is not None:
                main_start_reading = float(prev_row["main_end_reading"]) if pd.notna(prev_row["main_end_reading"]) else 0.0
        if main_start_reading is None:
            main_start_reading = 0.0

    if main_end_reading is None:
        main_end_reading = main_start_reading

    _execute(
        """
        INSERT INTO months (month, main_start_reading, main_end_reading, monthly_bill, dg_bill, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (month, float(main_start_reading), float(main_end_reading), float(monthly_bill), float(dg_bill), notes or ""),
    )


def update_month(month: str, **kwargs) -> bool:
    allowed = {"main_start_reading", "main_end_reading", "monthly_bill", "dg_bill", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = tuple(updates.values()) + (month,)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE months SET {set_clause} WHERE month = ?", params)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_previous_month(month: str) -> Optional[str]:
    """Return the chronologically previous month stored in the database."""
    df = get_months()
    if df.empty:
        return None
    months = sorted(df["month"].dropna().astype(str).tolist())
    try:
        idx = months.index(month)
    except ValueError:
        # If the month is not yet stored, return the last stored month.
        return months[-1] if months else None
    return months[idx - 1] if idx > 0 else None


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------
def get_readings(month: Optional[str] = None) -> pd.DataFrame:
    if month is not None:
        return _df_from_query(
            "SELECT month, roommate, current_reading FROM readings WHERE month = ? ORDER BY roommate",
            (month,),
        )
    return _df_from_query("SELECT month, roommate, current_reading FROM readings ORDER BY month, roommate")


def set_reading(month: str, roommate: str, current_reading: float) -> None:
    _execute(
        """
        INSERT INTO readings (month, roommate, current_reading)
        VALUES (?, ?, ?)
        ON CONFLICT(month, roommate) DO UPDATE SET current_reading = excluded.current_reading
        """,
        (month, roommate, float(current_reading)),
    )


def get_reading(month: str, roommate: str) -> Optional[float]:
    df = _df_from_query(
        "SELECT current_reading FROM readings WHERE month = ? AND roommate = ?",
        (month, roommate),
    )
    if df.empty:
        return None
    val = df.iloc[0]["current_reading"]
    return float(val) if pd.notna(val) else None


# ---------------------------------------------------------------------------
# Recharges
# ---------------------------------------------------------------------------
def get_recharges() -> pd.DataFrame:
    return _df_from_query("SELECT id, date, roommate, amount, notes FROM recharges ORDER BY date, id")


def get_recharge(rid: int) -> Optional[pd.Series]:
    df = _df_from_query("SELECT id, date, roommate, amount, notes FROM recharges WHERE id = ?", (rid,))
    if df.empty:
        return None
    return df.iloc[0]


def add_recharge(date: str, roommate: str, amount: float, notes: Optional[str] = None) -> int:
    rid = _execute(
        "INSERT INTO recharges (date, roommate, amount, notes) VALUES (?, ?, ?, ?)",
        (date, roommate, float(amount), notes or ""),
    )
    return rid


def update_recharge(rid: int, **kwargs) -> bool:
    allowed = {"date", "roommate", "amount", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = tuple(updates.values()) + (rid,)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE recharges SET {set_clause} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_recharge(rid: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recharges WHERE id = ?", (rid,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_recharges_by_month(month: str) -> pd.DataFrame:
    year, mon = int(month[:4]), int(month[5:7])
    last_day = pd.Period(f"{year}-{mon}", freq="M").days_in_month
    month_start = f"{month}-01"
    month_end = f"{year:04d}-{mon:02d}-{last_day:02d}"
    return _df_from_query(
        "SELECT id, date, roommate, amount, notes FROM recharges WHERE date BETWEEN ? AND ? ORDER BY date, id",
        (month_start, month_end),
    )


def get_recharges_for_roommate(roommate: str, up_to_month: Optional[str] = None) -> pd.DataFrame:
    if up_to_month is not None:
        return _df_from_query(
            "SELECT id, date, roommate, amount, notes FROM recharges WHERE roommate = ? AND date <= ? ORDER BY date",
            (roommate, f"{up_to_month}-31"),
        )
    return _df_from_query(
        "SELECT id, date, roommate, amount, notes FROM recharges WHERE roommate = ? ORDER BY date",
        (roommate,),
    )
