"""
Supabase Postgres data access.

Every function is scoped to a household id. The ``list_*`` helpers return
plain dicts for the API; ``HouseholdData`` loads one household into pandas
DataFrames so calc/export run in memory instead of making hundreds of round
trips to the remote database.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import pandas as pd
from psycopg import errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_pool: Optional[ConnectionPool] = None


# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------
def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def open_pool() -> None:
    """Open the pool and fail fast if the database is unreachable."""
    global _pool
    _pool = ConnectionPool(
        database_url(),
        min_size=1,
        max_size=5,
        # prepare_threshold=None keeps it compatible with Supabase's poolers.
        kwargs={"prepare_threshold": None, "row_factory": dict_row},
        check=ConnectionPool.check_connection,
        open=True,
    )
    _pool.wait(timeout=30)


def close_pool() -> None:
    if _pool is not None:
        _pool.close()


def _fetch(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with _pool.connection() as conn:
        return conn.execute(query, params).fetchall()


def _fetch_one(query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    with _pool.connection() as conn:
        return conn.execute(query, params).fetchone()


def _execute(query: str, params: tuple = ()) -> int:
    """Run a write query and return the number of affected rows."""
    with _pool.connection() as conn:
        return conn.execute(query, params).rowcount


def _set_clause(updates: Dict[str, Any]) -> str:
    # Keys are always filtered through an allow-list before reaching here.
    return ", ".join(f"{k} = %s" for k in updates)


# ---------------------------------------------------------------------------
# Households
# ---------------------------------------------------------------------------
def _new_invite_code() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(8))


def list_households(user_id: str) -> List[Dict[str, Any]]:
    return _fetch(
        """
        SELECT h.id, h.name, h.invite_code, m.role
        FROM household_members m JOIN households h ON h.id = m.household_id
        WHERE m.user_id = %s
        ORDER BY h.created_at
        """,
        (user_id,),
    )


def create_household(user_id: str, name: str) -> Dict[str, Any]:
    with _pool.connection() as conn:
        row = None
        while row is None:
            row = conn.execute(
                """
                INSERT INTO households (name, invite_code, created_by) VALUES (%s, %s, %s)
                ON CONFLICT (invite_code) DO NOTHING
                RETURNING id, name, invite_code
                """,
                (name.strip(), _new_invite_code(), user_id),
            ).fetchone()
        conn.execute(
            "INSERT INTO household_members (household_id, user_id, role) VALUES (%s, %s, 'owner')",
            (row["id"], user_id),
        )
    return {**row, "role": "owner"}


def join_household(user_id: str, invite_code: str) -> Optional[Dict[str, Any]]:
    """Add the user to the household with this code; None if the code is unknown."""
    with _pool.connection() as conn:
        household = conn.execute(
            "SELECT id, name, invite_code FROM households WHERE invite_code = %s",
            (invite_code.strip().upper(),),
        ).fetchone()
        if household is None:
            return None
        conn.execute(
            """
            INSERT INTO household_members (household_id, user_id) VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (household["id"], user_id),
        )
        role = conn.execute(
            "SELECT role FROM household_members WHERE household_id = %s AND user_id = %s",
            (household["id"], user_id),
        ).fetchone()["role"]
    return {**household, "role": role}


def is_member(user_id: str, household_id: UUID) -> bool:
    return _fetch_one(
        "SELECT 1 FROM household_members WHERE household_id = %s AND user_id = %s",
        (household_id, user_id),
    ) is not None


# ---------------------------------------------------------------------------
# Roommates
# ---------------------------------------------------------------------------
ROOMMATE_COLS = ["id", "name", "join_date", "leave_date", "is_active"]
_ROOMMATE_SELECT = f"SELECT {', '.join(ROOMMATE_COLS)} FROM roommates"


def list_roommates(hid: UUID) -> List[Dict[str, Any]]:
    return _fetch(f"{_ROOMMATE_SELECT} WHERE household_id = %s ORDER BY id", (hid,))


def get_roommate(hid: UUID, rid: int) -> Optional[Dict[str, Any]]:
    return _fetch_one(f"{_ROOMMATE_SELECT} WHERE household_id = %s AND id = %s", (hid, rid))


def add_roommate(hid: UUID, name: str, join_date: str = "", leave_date: str = "",
                 is_active: bool = True) -> Dict[str, Any]:
    try:
        return _fetch_one(
            f"""
            INSERT INTO roommates (household_id, name, join_date, leave_date, is_active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING {', '.join(ROOMMATE_COLS)}
            """,
            (hid, name.strip(), join_date or "", leave_date or "", is_active),
        )
    except errors.UniqueViolation:
        raise ValueError(f"A roommate named {name.strip()!r} already exists")


def update_roommate(hid: UUID, rid: int, **kwargs) -> Optional[Dict[str, Any]]:
    allowed = {"name", "join_date", "leave_date", "is_active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_roommate(hid, rid)
    try:
        return _fetch_one(
            f"""
            UPDATE roommates SET {_set_clause(updates)}
            WHERE household_id = %s AND id = %s
            RETURNING {', '.join(ROOMMATE_COLS)}
            """,
            (*updates.values(), hid, rid),
        )
    except errors.UniqueViolation:
        raise ValueError(f"A roommate named {updates.get('name')!r} already exists")


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------
MONTH_COLS = ["month", "main_start_reading", "main_end_reading", "monthly_bill", "dg_bill", "notes"]
_MONTH_SELECT = f"SELECT {', '.join(MONTH_COLS)} FROM months"


def list_months(hid: UUID) -> List[Dict[str, Any]]:
    return _fetch(f"{_MONTH_SELECT} WHERE household_id = %s ORDER BY month", (hid,))


def get_month(hid: UUID, month: str) -> Optional[Dict[str, Any]]:
    return _fetch_one(f"{_MONTH_SELECT} WHERE household_id = %s AND month = %s", (hid, month))


def add_month(hid: UUID, month: str, monthly_bill: float, dg_bill: float = 0.0,
              main_start_reading: Optional[float] = None,
              main_end_reading: Optional[float] = None,
              notes: Optional[str] = None) -> Dict[str, Any]:
    # Auto-carry main start reading from the previous month if not supplied.
    if main_start_reading is None:
        prev = _fetch_one(
            """
            SELECT main_end_reading FROM months
            WHERE household_id = %s AND month < %s ORDER BY month DESC LIMIT 1
            """,
            (hid, month),
        )
        main_start_reading = prev["main_end_reading"] if prev else 0.0

    if main_end_reading is None:
        main_end_reading = main_start_reading

    try:
        return _fetch_one(
            f"""
            INSERT INTO months (household_id, month, main_start_reading, main_end_reading,
                                monthly_bill, dg_bill, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING {', '.join(MONTH_COLS)}
            """,
            (hid, month, float(main_start_reading), float(main_end_reading),
             float(monthly_bill), float(dg_bill), notes or ""),
        )
    except errors.UniqueViolation:
        raise ValueError(f"Month {month} already exists")


def update_month(hid: UUID, month: str, **kwargs) -> Optional[Dict[str, Any]]:
    allowed = {"main_start_reading", "main_end_reading", "monthly_bill", "dg_bill", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return get_month(hid, month)
    return _fetch_one(
        f"""
        UPDATE months SET {_set_clause(updates)}
        WHERE household_id = %s AND month = %s
        RETURNING {', '.join(MONTH_COLS)}
        """,
        (*updates.values(), hid, month),
    )


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------
READING_COLS = ["month", "roommate_id", "roommate", "current_reading"]


def list_readings(hid: UUID, month: Optional[str] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT r.month, r.roommate_id, rm.name AS roommate, r.current_reading
        FROM readings r JOIN roommates rm ON rm.id = r.roommate_id
        WHERE r.household_id = %s
    """
    params: tuple = (hid,)
    if month is not None:
        query += " AND r.month = %s"
        params += (month,)
    return _fetch(query + " ORDER BY r.month, rm.name", params)


def set_reading(hid: UUID, month: str, roommate_id: int, current_reading: float) -> None:
    _execute(
        """
        INSERT INTO readings (household_id, month, roommate_id, current_reading)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (household_id, month, roommate_id)
        DO UPDATE SET current_reading = excluded.current_reading
        """,
        (hid, month, roommate_id, float(current_reading)),
    )


# ---------------------------------------------------------------------------
# Recharges
# ---------------------------------------------------------------------------
RECHARGE_COLS = ["id", "date", "roommate_id", "roommate", "amount", "notes"]
_RECHARGE_SELECT = """
    SELECT r.id, to_char(r.date, 'YYYY-MM-DD') AS date, r.roommate_id,
           rm.name AS roommate, r.amount, r.notes
    FROM recharges r JOIN roommates rm ON rm.id = r.roommate_id
"""


def list_recharges(hid: UUID, month: Optional[str] = None) -> List[Dict[str, Any]]:
    query = _RECHARGE_SELECT + " WHERE r.household_id = %s"
    params: tuple = (hid,)
    if month is not None:
        query += " AND to_char(r.date, 'YYYY-MM') = %s"
        params += (month,)
    return _fetch(query + " ORDER BY r.date, r.id", params)


def get_recharge(hid: UUID, rid: int) -> Optional[Dict[str, Any]]:
    return _fetch_one(_RECHARGE_SELECT + " WHERE r.household_id = %s AND r.id = %s", (hid, rid))


def add_recharge(hid: UUID, date: str, roommate_id: int, amount: float,
                 notes: Optional[str] = None) -> int:
    row = _fetch_one(
        """
        INSERT INTO recharges (household_id, date, roommate_id, amount, notes)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
        """,
        (hid, date, roommate_id, float(amount), notes or ""),
    )
    return row["id"]


def update_recharge(hid: UUID, rid: int, **kwargs) -> bool:
    allowed = {"date", "roommate_id", "amount", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_recharge(hid, rid) is not None
    return _execute(
        f"UPDATE recharges SET {_set_clause(updates)} WHERE household_id = %s AND id = %s",
        (*updates.values(), hid, rid),
    ) > 0


def delete_recharge(hid: UUID, rid: int) -> bool:
    return _execute("DELETE FROM recharges WHERE household_id = %s AND id = %s", (hid, rid)) > 0


# ---------------------------------------------------------------------------
# In-memory snapshot for calc / export
# ---------------------------------------------------------------------------
class HouseholdData:
    """One household's tables loaded once, with the lookups calc/export need."""

    def __init__(self, hid: UUID):
        self.roommates = pd.DataFrame(list_roommates(hid), columns=ROOMMATE_COLS)
        self.months = pd.DataFrame(list_months(hid), columns=MONTH_COLS)
        self.readings = pd.DataFrame(list_readings(hid), columns=READING_COLS)
        self.recharges = pd.DataFrame(list_recharges(hid), columns=RECHARGE_COLS)

    def get_roommates(self) -> pd.DataFrame:
        return self.roommates

    def get_months(self) -> pd.DataFrame:
        return self.months

    def get_recharges(self) -> pd.DataFrame:
        return self.recharges

    def get_month(self, month: str) -> Optional[pd.Series]:
        rows = self.months[self.months["month"] == month]
        return None if rows.empty else rows.iloc[0]

    def get_readings(self, month: str) -> pd.DataFrame:
        return self.readings[self.readings["month"] == month]

    def get_reading(self, month: str, roommate: str) -> Optional[float]:
        rows = self.readings[(self.readings["month"] == month) & (self.readings["roommate"] == roommate)]
        if rows.empty or pd.isna(rows.iloc[0]["current_reading"]):
            return None
        return float(rows.iloc[0]["current_reading"])

    def get_previous_month(self, month: str) -> Optional[str]:
        earlier = sorted(m for m in self.months["month"].astype(str) if m < month)
        return earlier[-1] if earlier else None

    def get_roommate_id_by_name(self, name: str) -> Optional[int]:
        rows = self.roommates[self.roommates["name"] == name]
        return None if rows.empty else int(rows.iloc[0]["id"])

    def latest_month_with_readings(self) -> Optional[str]:
        months = self.readings["month"].dropna().astype(str)
        return months.max() if not months.empty else None
