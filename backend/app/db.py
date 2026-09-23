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
import time
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

# The database is a long round trip away (~75 ms), so each request should cost
# as few trips as possible. A connection idle longer than this gets a liveness
# check before reuse (Supabase's pooler may have dropped it); recently used
# ones skip that extra trip.
STALE_AFTER_SECONDS = 30.0


# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------
def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def _mark_used(conn) -> None:
    # Pool "reset" hook: runs each time a connection goes back to the pool.
    conn.wattsplit_last_used = time.monotonic()


def _check_if_stale(conn) -> None:
    if time.monotonic() - getattr(conn, "wattsplit_last_used", 0.0) > STALE_AFTER_SECONDS:
        ConnectionPool.check_connection(conn)


def open_pool() -> None:
    """Open the pool and fail fast if the database is unreachable."""
    global _pool
    _pool = ConnectionPool(
        database_url(),
        min_size=1,
        max_size=5,
        # prepare_threshold=None keeps it compatible with Supabase's poolers.
        # autocommit: single statements need no BEGIN/COMMIT round trips;
        # multi-statement writes use conn.transaction() explicitly.
        kwargs={"prepare_threshold": None, "row_factory": dict_row, "autocommit": True},
        check=_check_if_stale,
        reset=_mark_used,
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
    with _pool.connection() as conn, conn.transaction():
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


def get_membership(user_id: str, household_id: UUID) -> Optional[Dict[str, Any]]:
    """
    ``{"role": "owner" | "member", "roommate_id": int | None}`` (the roommate
    this login is linked to), or None when the user isn't in the household.
    """
    return _fetch_one(
        """
        SELECT m.role, r.id AS roommate_id
        FROM household_members m
        LEFT JOIN roommates r ON r.household_id = m.household_id AND r.user_id = m.user_id
        WHERE m.household_id = %s AND m.user_id = %s
        """,
        (household_id, user_id),
    )


# ---------------------------------------------------------------------------
# Roommates
# ---------------------------------------------------------------------------
ROOMMATE_COLS = ["id", "name", "join_date", "leave_date", "is_active", "linked"]
# "linked": some login is this roommate. The user id itself isn't exposed.
_ROOMMATE_FIELDS = "id, name, join_date, leave_date, is_active, (user_id IS NOT NULL) AS linked"
_ROOMMATE_SELECT = f"SELECT {_ROOMMATE_FIELDS} FROM roommates"


def list_roommates(hid: UUID) -> List[Dict[str, Any]]:
    return _fetch(f"{_ROOMMATE_SELECT} WHERE household_id = %s ORDER BY id", (hid,))


def get_roommate(hid: UUID, rid: int) -> Optional[Dict[str, Any]]:
    return _fetch_one(f"{_ROOMMATE_SELECT} WHERE household_id = %s AND id = %s", (hid, rid))


ALREADY_LINKED = "You are already linked to a roommate in this household"


def _roommate_conflict(exc: errors.UniqueViolation, name: Optional[str]) -> ValueError:
    if exc.diag.constraint_name == "roommates_household_user_idx":
        return ValueError(ALREADY_LINKED)
    return ValueError(f"A roommate named {(name or '').strip()!r} already exists")


def add_roommate(hid: UUID, name: str, join_date: str = "", leave_date: str = "",
                 is_active: bool = True, user_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        return _fetch_one(
            f"""
            INSERT INTO roommates (household_id, name, join_date, leave_date, is_active, user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING {_ROOMMATE_FIELDS}
            """,
            (hid, name.strip(), join_date or "", leave_date or "", is_active, user_id),
        )
    except errors.UniqueViolation as exc:
        raise _roommate_conflict(exc, name)


def link_roommate(hid: UUID, rid: int, user_id: str) -> Optional[Dict[str, Any]]:
    """Link the login to an unlinked roommate; None if it's missing or already taken."""
    try:
        return _fetch_one(
            f"""
            UPDATE roommates SET user_id = %s
            WHERE household_id = %s AND id = %s AND user_id IS NULL
            RETURNING {_ROOMMATE_FIELDS}
            """,
            (user_id, hid, rid),
        )
    except errors.UniqueViolation:
        raise ValueError(ALREADY_LINKED)


def unlink_user(hid: UUID, user_id: str) -> bool:
    """Detach this login from its roommate."""
    return _execute(
        "UPDATE roommates SET user_id = NULL WHERE household_id = %s AND user_id = %s",
        (hid, user_id),
    ) > 0


def unlink_roommate(hid: UUID, rid: int) -> bool:
    """Detach whichever login is linked to this roommate."""
    return _execute(
        "UPDATE roommates SET user_id = NULL WHERE household_id = %s AND id = %s",
        (hid, rid),
    ) > 0


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
            RETURNING {_ROOMMATE_FIELDS}
            """,
            (*updates.values(), hid, rid),
        )
    except errors.UniqueViolation as exc:
        raise _roommate_conflict(exc, updates.get("name"))


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------
METER_COLS = ["meter_opening_balance", "meter_recharge", "meter_closing_balance"]
MONTH_COLS = ["month", "main_start_reading", "main_end_reading", "monthly_bill", "dg_bill", "notes", *METER_COLS]
_MONTH_SELECT = f"SELECT {', '.join(MONTH_COLS)} FROM months"


def list_months(hid: UUID) -> List[Dict[str, Any]]:
    return _fetch(f"{_MONTH_SELECT} WHERE household_id = %s ORDER BY month", (hid,))


def get_month(hid: UUID, month: str) -> Optional[Dict[str, Any]]:
    return _fetch_one(f"{_MONTH_SELECT} WHERE household_id = %s AND month = %s", (hid, month))


def meter_bill(opening: Optional[float], recharge: Optional[float],
               closing: Optional[float]) -> Optional[float]:
    """What the prepaid meter deducted: opening + recharge - closing (None until all three are known)."""
    if opening is None or recharge is None or closing is None:
        return None
    bill = round(opening + recharge - closing, 2)
    if bill < 0:
        raise ValueError("Closing balance can't be more than opening balance + recharge")
    return bill


def add_month(hid: UUID, month: str, monthly_bill: float, dg_bill: float = 0.0,
              main_start_reading: Optional[float] = None,
              main_end_reading: Optional[float] = None,
              notes: Optional[str] = None,
              meter_opening_balance: Optional[float] = None,
              meter_recharge: Optional[float] = None,
              meter_closing_balance: Optional[float] = None) -> Dict[str, Any]:
    # Carry the main meter reading (and meter balance) over from the previous month.
    prev = _fetch_one(
        """
        SELECT main_end_reading, meter_closing_balance FROM months
        WHERE household_id = %s AND month < %s ORDER BY month DESC LIMIT 1
        """,
        (hid, month),
    )
    if main_start_reading is None:
        main_start_reading = prev["main_end_reading"] if prev else 0.0
    if main_end_reading is None:
        main_end_reading = main_start_reading
    if meter_opening_balance is None and (meter_recharge is not None or meter_closing_balance is not None):
        meter_opening_balance = prev["meter_closing_balance"] if prev else None
    bill = meter_bill(meter_opening_balance, meter_recharge, meter_closing_balance)
    if bill is not None:
        monthly_bill = bill

    try:
        return _fetch_one(
            f"""
            INSERT INTO months (household_id, month, main_start_reading, main_end_reading,
                                monthly_bill, dg_bill, notes, {", ".join(METER_COLS)})
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {', '.join(MONTH_COLS)}
            """,
            (hid, month, float(main_start_reading), float(main_end_reading),
             float(monthly_bill), float(dg_bill), notes or "",
             meter_opening_balance, meter_recharge, meter_closing_balance),
        )
    except errors.UniqueViolation:
        raise ValueError(f"Month {month} already exists")


def update_month(hid: UUID, month: str, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Update the given fields. Meter balances may be set to None (cleared); once
    all three are set, monthly_bill is worked out from them.
    """
    allowed = {"main_start_reading", "main_end_reading", "monthly_bill", "dg_bill", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    updates.update({k: v for k, v in kwargs.items() if k in METER_COLS})
    with _pool.connection() as conn, conn.transaction():
        row = conn.execute(f"{_MONTH_SELECT} WHERE household_id = %s AND month = %s FOR UPDATE",
                           (hid, month)).fetchone()
        if row is None:
            return None
        merged = {**row, **updates}
        bill = meter_bill(*(merged[c] for c in METER_COLS))
        if bill is not None:
            updates["monthly_bill"] = bill
        if not updates:
            return row
        return conn.execute(
            f"""
            UPDATE months SET {_set_clause(updates)}
            WHERE household_id = %s AND month = %s
            RETURNING {', '.join(MONTH_COLS)}
            """,
            (*updates.values(), hid, month),
        ).fetchone()


def import_meter_months(hid: UUID, months: List[Dict[str, Any]]) -> None:
    """
    Create or update months from the meter report: main meter readings, the
    amount deducted (as monthly_bill) and the meter balances. DG bill and
    notes of existing months are kept.
    """
    with _pool.connection() as conn, conn.transaction():
        conn.cursor().executemany(
            """
            INSERT INTO months (household_id, month, main_start_reading, main_end_reading, monthly_bill,
                                meter_opening_balance, meter_recharge, meter_closing_balance)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (household_id, month) DO UPDATE SET
                main_start_reading    = excluded.main_start_reading,
                main_end_reading      = excluded.main_end_reading,
                monthly_bill          = excluded.monthly_bill,
                meter_opening_balance = excluded.meter_opening_balance,
                meter_recharge        = excluded.meter_recharge,
                meter_closing_balance = excluded.meter_closing_balance
            """,
            [
                (hid, m["month"], m["main_start_reading"], m["main_end_reading"], m["monthly_bill"],
                 m["meter_opening_balance"], m["meter_recharge"], m["meter_closing_balance"])
                for m in months
            ],
        )


# ---------------------------------------------------------------------------
# Personal invites
# ---------------------------------------------------------------------------
INVITE_DAYS = 14


class InviteError(ValueError):
    """An invite that can't be used; ``status`` is the HTTP status to answer with."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:2]}{'*' * max(len(name) - 2, 1)}@{domain}"


_INVITE_SELECT = """
    SELECT i.id, i.household_id, i.roommate_id, rm.name AS roommate, i.email, i.code,
           i.expires_at, i.accepted_at, (i.expires_at <= now()) AS expired,
           h.name AS household, (rm.user_id IS NOT NULL) AS linked
    FROM invites i
    JOIN roommates rm ON rm.id = i.roommate_id
    JOIN households h ON h.id = i.household_id
"""


def create_invite(hid: UUID, rid: int, email: str, created_by: str) -> Dict[str, Any]:
    """New invite for the roommate, replacing any unused one."""
    with _pool.connection() as conn, conn.transaction():
        conn.execute(
            "DELETE FROM invites WHERE household_id = %s AND roommate_id = %s AND accepted_at IS NULL",
            (hid, rid),
        )
        row = None
        while row is None:
            row = conn.execute(
                f"""
                INSERT INTO invites (household_id, roommate_id, email, code, created_by, expires_at)
                VALUES (%s, %s, %s, %s, %s, now() + interval '{INVITE_DAYS} days')
                ON CONFLICT (code) DO NOTHING
                RETURNING id
                """,
                (hid, rid, email.strip().lower(), "".join(secrets.choice(INVITE_ALPHABET) for _ in range(10)),
                 created_by),
            ).fetchone()
        return conn.execute(_INVITE_SELECT + " WHERE i.id = %s", (row["id"],)).fetchone()


def list_invites(hid: UUID) -> List[Dict[str, Any]]:
    """Invites not yet used or expired."""
    return _fetch(
        _INVITE_SELECT + " WHERE i.household_id = %s AND i.accepted_at IS NULL AND i.expires_at > now()"
        " ORDER BY i.created_at",
        (hid,),
    )


def delete_invite(hid: UUID, invite_id: int) -> bool:
    return _execute("DELETE FROM invites WHERE household_id = %s AND id = %s", (hid, invite_id)) > 0


def _usable_invite(conn, code: str, lock: bool = False) -> Dict[str, Any]:
    row = conn.execute(
        _INVITE_SELECT + " WHERE i.code = %s" + (" FOR UPDATE OF i" if lock else ""),
        (code.strip().upper(),),
    ).fetchone()
    if row is None:
        raise InviteError(404, "This invite link isn't valid. Ask the owner for a new one.")
    if row["accepted_at"] is not None:
        raise InviteError(410, "This invite has already been used.")
    if row["expired"]:
        raise InviteError(410, "This invite has expired. Ask the owner for a new one.")
    return row


def lookup_invite(code: str) -> Dict[str, Any]:
    with _pool.connection() as conn:
        return _usable_invite(conn, code)


def accept_invite(code: str, user_id: str, email: Optional[str]) -> Dict[str, Any]:
    """
    Join the invite's household and become its roommate. The signed-in email
    must be the invited one. Returns the household as list_households does.
    """
    with _pool.connection() as conn, conn.transaction():
        invite = _usable_invite(conn, code, lock=True)
        if (email or "").strip().lower() != invite["email"]:
            raise InviteError(
                403, f"This invite is for {_mask_email(invite['email'])}. Sign in with that email to accept it."
            )
        hid = invite["household_id"]
        conn.execute(
            "INSERT INTO household_members (household_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (hid, user_id),
        )
        mine = conn.execute(
            "SELECT id, name FROM roommates WHERE household_id = %s AND user_id = %s", (hid, user_id)
        ).fetchone()
        if mine is not None and mine["id"] != invite["roommate_id"]:
            raise InviteError(409, f"You are already {mine['name']} in {invite['household']}.")
        if mine is None:
            linked = conn.execute(
                "UPDATE roommates SET user_id = %s WHERE household_id = %s AND id = %s AND user_id IS NULL",
                (user_id, hid, invite["roommate_id"]),
            ).rowcount
            if not linked:
                raise InviteError(409, f"Someone else is already {invite['roommate']} in {invite['household']}.")
        conn.execute("UPDATE invites SET accepted_by = %s, accepted_at = now() WHERE id = %s",
                     (user_id, invite["id"]))
        return conn.execute(
            """
            SELECT h.id, h.name, h.invite_code, m.role
            FROM household_members m JOIN households h ON h.id = m.household_id
            WHERE m.household_id = %s AND m.user_id = %s
            """,
            (hid, user_id),
        ).fetchone()


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------
READING_COLS = ["month", "roommate_id", "roommate", "current_reading", "start_reading"]
_READING_SELECT = """
    SELECT r.month, r.roommate_id, rm.name AS roommate, r.current_reading, r.start_reading
    FROM readings r JOIN roommates rm ON rm.id = r.roommate_id
"""


def list_readings(hid: UUID, month: Optional[str] = None) -> List[Dict[str, Any]]:
    query = _READING_SELECT + " WHERE r.household_id = %s"
    params: tuple = (hid,)
    if month is not None:
        query += " AND r.month = %s"
        params += (month,)
    return _fetch(query + " ORDER BY r.month, rm.name", params)


def previous_readings(hid: UUID, month: str) -> List[Dict[str, Any]]:
    """Month-end readings of the month before ``month``: that month's starting point."""
    return _fetch(
        """
        SELECT roommate_id, current_reading FROM readings
        WHERE household_id = %s AND current_reading IS NOT NULL
          AND month = (SELECT max(month) FROM months WHERE household_id = %s AND month < %s)
        """,
        (hid, hid, month),
    )


def set_reading(hid: UUID, month: str, roommate_id: int, **fields: Optional[float]) -> None:
    """
    Set ``current_reading`` and/or ``start_reading`` (only the ones given; None
    clears it). A row left with neither is removed.
    """
    cols = [c for c in ("current_reading", "start_reading") if c in fields]
    if not cols:
        return
    values = [None if fields[c] is None else float(fields[c]) for c in cols]
    with _pool.connection() as conn, conn.transaction():
        conn.execute(
            f"""
            INSERT INTO readings (household_id, month, roommate_id, {", ".join(cols)})
            VALUES (%s, %s, %s, {", ".join(["%s"] * len(cols))})
            ON CONFLICT (household_id, month, roommate_id)
            DO UPDATE SET {", ".join(f"{c} = excluded.{c}" for c in cols)}
            """,
            (hid, month, roommate_id, *values),
        )
        conn.execute(
            """
            DELETE FROM readings WHERE household_id = %s AND month = %s AND roommate_id = %s
              AND current_reading IS NULL AND start_reading IS NULL
            """,
            (hid, month, roommate_id),
        )


def delete_reading(hid: UUID, month: str, roommate_id: int) -> bool:
    return _execute(
        "DELETE FROM readings WHERE household_id = %s AND month = %s AND roommate_id = %s",
        (hid, month, roommate_id),
    ) > 0


# ---------------------------------------------------------------------------
# Recharges
# ---------------------------------------------------------------------------
RECHARGE_COLS = ["id", "date", "roommate_id", "roommate", "amount", "notes", "meter"]
_RECHARGE_SELECT = """
    SELECT r.id, to_char(r.date, 'YYYY-MM-DD') AS date, r.roommate_id,
           rm.name AS roommate, r.amount, r.notes, r.meter
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
                 notes: Optional[str] = None, meter: str = "main") -> int:
    row = _fetch_one(
        """
        INSERT INTO recharges (household_id, date, roommate_id, amount, notes, meter)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (hid, date, roommate_id, float(amount), notes or "", meter),
    )
    return row["id"]


def update_recharge(hid: UUID, rid: int, **kwargs) -> bool:
    allowed = {"date", "roommate_id", "amount", "notes", "meter"}
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
# All four tables of one household in a single round trip, each as a JSON
# array in the same order the list_* helpers use.
_SNAPSHOT_SQL = f"""
SELECT
    (SELECT coalesce(json_agg(t ORDER BY t.id), '[]')
     FROM ({_ROOMMATE_SELECT} WHERE household_id = %(h)s) t) AS roommates,
    (SELECT coalesce(json_agg(t ORDER BY t.month), '[]')
     FROM ({_MONTH_SELECT} WHERE household_id = %(h)s) t) AS months,
    (SELECT coalesce(json_agg(t ORDER BY t.month, t.roommate), '[]')
     FROM ({_READING_SELECT} WHERE r.household_id = %(h)s) t) AS readings,
    (SELECT coalesce(json_agg(t ORDER BY t.date, t.id), '[]')
     FROM ({_RECHARGE_SELECT} WHERE r.household_id = %(h)s) t) AS recharges
"""


class HouseholdData:
    """One household's tables loaded once, with the lookups calc/export need."""

    def __init__(self, hid: UUID):
        rows = _fetch_one(_SNAPSHOT_SQL, {"h": hid})
        # Plain dicts too, for API responses (DataFrames hold numpy types).
        self.roommate_rows: List[Dict[str, Any]] = rows["roommates"]
        self.recharge_rows: List[Dict[str, Any]] = rows["recharges"]
        self.roommates = pd.DataFrame(rows["roommates"], columns=ROOMMATE_COLS)
        self.months = pd.DataFrame(rows["months"], columns=MONTH_COLS)
        self.readings = pd.DataFrame(rows["readings"], columns=READING_COLS)
        self.recharges = pd.DataFrame(rows["recharges"], columns=RECHARGE_COLS)

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

    def get_start_reading(self, month: str, roommate: str) -> Optional[float]:
        rows = self.readings[(self.readings["month"] == month) & (self.readings["roommate"] == roommate)]
        if rows.empty or pd.isna(rows.iloc[0]["start_reading"]):
            return None
        return float(rows.iloc[0]["start_reading"])

    def get_previous_month(self, month: str) -> Optional[str]:
        earlier = sorted(m for m in self.months["month"].astype(str) if m < month)
        return earlier[-1] if earlier else None

    def get_roommate_id_by_name(self, name: str) -> Optional[int]:
        rows = self.roommates[self.roommates["name"] == name]
        return None if rows.empty else int(rows.iloc[0]["id"])

    def latest_month_with_readings(self) -> Optional[str]:
        months = self.readings["month"].dropna().astype(str)
        return months.max() if not months.empty else None
