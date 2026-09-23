"""
FastAPI backend for the electricity bill splitter.

Every data route needs a Supabase access token (``Authorization: Bearer``)
and an ``X-Household-Id`` header naming a household the user belongs to.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from . import calc, db, export
from .auth import current_user_id
from .models import (
    HouseholdCreate,
    HouseholdJoin,
    HouseholdOut,
    MonthCalculation,
    MonthCreate,
    MonthDetail,
    MonthOut,
    MonthUpdate,
    ReadingUpdate,
    RechargeCreate,
    RechargeOut,
    RechargeUpdate,
    RoommateCreate,
    RoommateOut,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.open_pool()
    yield
    db.close_pool()


app = FastAPI(title="Electricity Bill Splitter", lifespan=lifespan)

# CORS for the Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MonthParam = Annotated[str, Path(pattern=r"^\d{4}-\d{2}$")]
UserId = Annotated[str, Depends(current_user_id)]


def current_household(user_id: UserId, x_household_id: UUID = Header(...)) -> UUID:
    """FastAPI dependency: the household in X-Household-Id, if the user is a member."""
    if not db.is_member(user_id, x_household_id):
        raise HTTPException(status_code=403, detail="You are not a member of this household")
    return x_household_id


HouseholdId = Annotated[UUID, Depends(current_household)]


def _recharge_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "date": row["date"],
        "roommate_id": row["roommate_id"],
        "amount": row["amount"],
        "notes": row["notes"],
        "month": row["date"][:7],
    }


def _require_roommate(hid: UUID, roommate_id: int) -> None:
    if db.get_roommate(hid, roommate_id) is None:
        raise HTTPException(status_code=404, detail="Roommate not found")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Households
# ---------------------------------------------------------------------------
@app.get("/api/households", response_model=List[HouseholdOut])
def list_households(user_id: UserId):
    return db.list_households(user_id)


@app.post("/api/households", response_model=HouseholdOut, status_code=201)
def create_household(payload: HouseholdCreate, user_id: UserId):
    return db.create_household(user_id, payload.name)


@app.post("/api/households/join", response_model=HouseholdOut)
def join_household(payload: HouseholdJoin, user_id: UserId):
    household = db.join_household(user_id, payload.invite_code)
    if household is None:
        raise HTTPException(status_code=404, detail="No household with that invite code")
    return household


# ---------------------------------------------------------------------------
# Roommates
# ---------------------------------------------------------------------------
@app.get("/api/roommates", response_model=List[RoommateOut])
def list_roommates(hid: HouseholdId):
    return db.list_roommates(hid)


@app.post("/api/roommates", response_model=RoommateOut, status_code=201)
def create_roommate(payload: RoommateCreate, hid: HouseholdId):
    try:
        return db.add_roommate(
            hid,
            name=payload.name,
            join_date=payload.join_date or "",
            leave_date=payload.leave_date or "",
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.put("/api/roommates/{roommate_id}", response_model=RoommateOut)
def update_roommate(roommate_id: int, payload: RoommateCreate, hid: HouseholdId):
    try:
        updated = db.update_roommate(
            hid,
            roommate_id,
            name=payload.name,
            join_date=payload.join_date or "",
            leave_date=payload.leave_date or "",
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if updated is None:
        raise HTTPException(status_code=404, detail="Roommate not found")
    return updated


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------
@app.get("/api/months", response_model=List[MonthOut])
def list_months(hid: HouseholdId):
    return db.list_months(hid)


@app.get("/api/months/{month}", response_model=MonthDetail)
def get_month(month: MonthParam, hid: HouseholdId):
    row = db.get_month(hid, month)
    if row is None:
        raise HTTPException(status_code=404, detail="Month not found")
    return {**row, "readings": db.list_readings(hid, month)}


@app.post("/api/months", response_model=MonthOut, status_code=201)
def create_month(payload: MonthCreate, hid: HouseholdId):
    try:
        return db.add_month(
            hid,
            month=payload.month,
            monthly_bill=payload.monthly_bill,
            dg_bill=payload.dg_bill,
            main_start_reading=payload.main_start_reading,
            main_end_reading=payload.main_end_reading,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.put("/api/months/{month}", response_model=MonthOut)
def update_month(month: MonthParam, payload: MonthUpdate, hid: HouseholdId):
    updated = db.update_month(hid, month, **payload.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="Month not found")
    return updated


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------
@app.put("/api/readings/{month}/{roommate_id}")
def update_reading(month: MonthParam, roommate_id: int, payload: ReadingUpdate, hid: HouseholdId):
    if db.get_month(hid, month) is None:
        raise HTTPException(status_code=404, detail="Month not found")
    _require_roommate(hid, roommate_id)
    db.set_reading(hid, month, roommate_id, payload.current_reading)
    return {"month": month, "roommate_id": roommate_id, "current_reading": payload.current_reading}


# ---------------------------------------------------------------------------
# Recharges
# ---------------------------------------------------------------------------
@app.get("/api/recharges", response_model=List[RechargeOut])
def list_recharges(hid: HouseholdId, month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$")):
    return [_recharge_out(r) for r in db.list_recharges(hid, month)]


@app.post("/api/recharges", response_model=RechargeOut, status_code=201)
def create_recharge(payload: RechargeCreate, hid: HouseholdId):
    _require_roommate(hid, payload.roommate_id)
    rid = db.add_recharge(
        hid,
        date=payload.recharge_date.isoformat(),
        roommate_id=payload.roommate_id,
        amount=payload.amount,
        notes=payload.notes or "",
    )
    return _recharge_out(db.get_recharge(hid, rid))


@app.put("/api/recharges/{recharge_id}", response_model=RechargeOut)
def update_recharge(recharge_id: int, payload: RechargeUpdate, hid: HouseholdId):
    data = payload.model_dump(exclude_unset=True, by_alias=True)
    if data.get("roommate_id") is not None:
        _require_roommate(hid, data["roommate_id"])
    if data.get("date") is not None:
        data["date"] = data["date"].isoformat()
    if not db.update_recharge(hid, recharge_id, **data):
        raise HTTPException(status_code=404, detail="Recharge not found")
    return _recharge_out(db.get_recharge(hid, recharge_id))


@app.delete("/api/recharges/{recharge_id}", status_code=204)
def delete_recharge(recharge_id: int, hid: HouseholdId):
    if not db.delete_recharge(hid, recharge_id):
        raise HTTPException(status_code=404, detail="Recharge not found")
    return None


# ---------------------------------------------------------------------------
# Calculation & history
# ---------------------------------------------------------------------------
@app.get("/api/calculate/{month}", response_model=MonthCalculation)
def calculate_month(month: MonthParam, hid: HouseholdId):
    try:
        return calc.calculate_month(month, db.HouseholdData(hid))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/history")
def history(hid: HouseholdId):
    """Return running balances for all roommates across all months."""
    data = db.HouseholdData(hid)
    latest_month = data.latest_month_with_readings()
    if latest_month is None:
        return []
    try:
        result = calc.calculate_month(latest_month, data)
    except ValueError:
        return []
    return result["running_balances"]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
@app.get("/api/export/{month}")
def export_month(month: MonthParam, hid: HouseholdId):
    try:
        content = export.generate_month_report(month, db.HouseholdData(hid))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{month}_report.xlsx"'},
    )
