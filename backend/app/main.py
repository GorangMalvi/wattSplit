"""
FastAPI backend for the electricity bill splitter.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import calc, db, export
from .models import (
    MonthCalculation,
    MonthCreate,
    MonthDetail,
    MonthOut,
    ReadingUpdate,
    RechargeCreate,
    RechargeOut,
    RechargeUpdate,
    RoommateCreate,
    RoommateOut,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure the Excel database exists on startup."""
    db.init_db()
    yield


app = FastAPI(title="Electricity Bill Splitter", lifespan=lifespan)

# CORS for the Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Roommates
# ---------------------------------------------------------------------------
@app.get("/api/roommates", response_model=List[RoommateOut])
def list_roommates():
    df = db.get_roommates()
    if df.empty:
        return []
    return df.to_dict(orient="records")


@app.post("/api/roommates", response_model=RoommateOut, status_code=201)
def create_roommate(payload: RoommateCreate):
    rid = db.add_roommate(
        name=payload.name,
        join_date=payload.join_date or "",
        leave_date=payload.leave_date or "",
        is_active=payload.is_active,
    )
    df = db.get_roommates()
    row = df[df["id"] == rid].iloc[0]
    return row.to_dict()


@app.put("/api/roommates/{roommate_id}", response_model=RoommateOut)
def update_roommate(roommate_id: int, payload: RoommateCreate):
    updated = db.update_roommate(
        roommate_id,
        name=payload.name,
        join_date=payload.join_date or "",
        leave_date=payload.leave_date or "",
        is_active=payload.is_active,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Roommate not found")
    df = db.get_roommates()
    row = df[df["id"] == roommate_id].iloc[0]
    return row.to_dict()


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------
@app.get("/api/months", response_model=List[MonthOut])
def list_months():
    df = db.get_months()
    if df.empty:
        return []
    # Sort chronologically.
    df = df.sort_values("month")
    return df.to_dict(orient="records")


@app.get("/api/months/{month}", response_model=MonthDetail)
def get_month(month: str):
    row = db.get_month(month)
    if row is None:
        raise HTTPException(status_code=404, detail="Month not found")
    readings = []
    for _, r in db.get_readings(month).iterrows():
        rid = db.get_roommate_id_by_name(str(r["roommate"]))
        if rid is None:
            # Skip readings for names no longer in the roommates table.
            continue
        readings.append({
            "month": str(r["month"]),
            "roommate_id": rid,
            "current_reading": float(r["current_reading"]),
        })
    return {**row.to_dict(), "readings": readings}


@app.post("/api/months", response_model=MonthOut, status_code=201)
def create_month(payload: MonthCreate):
    try:
        db.add_month(
            month=payload.month,
            monthly_bill=payload.monthly_bill,
            dg_bill=payload.dg_bill,
            main_start_reading=payload.main_start_reading,
            main_end_reading=payload.main_end_reading,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    row = db.get_month(payload.month)
    return row.to_dict()


@app.put("/api/months/{month}", response_model=MonthOut)
def update_month(month: str, payload: MonthCreate):
    # Only update the supplied fields; keep month id stable.
    data = payload.model_dump(exclude_unset=True)
    data.pop("month", None)
    updated = db.update_month(month, **data)
    if not updated:
        raise HTTPException(status_code=404, detail="Month not found")
    row = db.get_month(month)
    return row.to_dict()


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------
@app.put("/api/readings/{month}/{roommate_id}")
def update_reading(month: str, roommate_id: int, payload: ReadingUpdate):
    name = db.get_roommate_name_by_id(roommate_id)
    if name is None:
        raise HTTPException(status_code=404, detail="Roommate not found")
    db.set_reading(month, name, payload.current_reading)
    return {"month": month, "roommate_id": roommate_id, "current_reading": payload.current_reading}


# ---------------------------------------------------------------------------
# Recharges
# ---------------------------------------------------------------------------
@app.get("/api/recharges", response_model=List[RechargeOut])
def list_recharges(month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$")):
    if month:
        df = db.get_recharges_by_month(month)
    else:
        df = db.get_recharges()
    if df.empty:
        return []
    records = []
    for _, row in df.iterrows():
        rid = db.get_roommate_id_by_name(str(row["roommate"]))
        if rid is None:
            # Skip non-roommate entries such as "DG".
            continue
        records.append({
            "id": int(row["id"]),
            "date": str(row["date"]),
            "roommate_id": rid,
            "amount": float(row["amount"]),
            "notes": str(row.get("notes", "")),
            "month": str(row["date"])[:7],
        })
    return records


@app.post("/api/recharges", response_model=RechargeOut, status_code=201)
def create_recharge(payload: RechargeCreate):
    name = db.get_roommate_name_by_id(payload.roommate_id)
    if name is None:
        raise HTTPException(status_code=404, detail="Roommate not found")
    rid = db.add_recharge(
        date=payload.recharge_date.isoformat(),
        roommate=name,
        amount=payload.amount,
        notes=payload.notes or "",
    )
    return {
        "id": rid,
        "date": payload.recharge_date.isoformat(),
        "roommate_id": payload.roommate_id,
        "amount": payload.amount,
        "notes": payload.notes or "",
        "month": payload.recharge_date.isoformat()[:7],
    }


@app.put("/api/recharges/{recharge_id}", response_model=RechargeOut)
def update_recharge(recharge_id: int, payload: RechargeUpdate):
    data = payload.model_dump(exclude_unset=True, by_alias=True)
    if "roommate_id" in data:
        name = db.get_roommate_name_by_id(data["roommate_id"])
        if name is None:
            raise HTTPException(status_code=404, detail="Roommate not found")
        data["roommate"] = name
        data.pop("roommate_id")
    if "date" in data and data["date"] is not None:
        data["date"] = data["date"].isoformat()
    updated = db.update_recharge(recharge_id, **data)
    if not updated:
        raise HTTPException(status_code=404, detail="Recharge not found")
    row = db.get_recharge(recharge_id)
    rid = db.get_roommate_id_by_name(str(row["roommate"]))
    return {
        "id": int(row["id"]),
        "date": str(row["date"]),
        "roommate_id": rid,
        "amount": float(row["amount"]),
        "notes": str(row.get("notes", "")),
        "month": str(row["date"])[:7],
    }


@app.delete("/api/recharges/{recharge_id}", status_code=204)
def delete_recharge(recharge_id: int):
    deleted = db.delete_recharge(recharge_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Recharge not found")
    return None


# ---------------------------------------------------------------------------
# Calculation & history
# ---------------------------------------------------------------------------
@app.get("/api/calculate/{month}", response_model=MonthCalculation)
def calculate_month(month: str):
    try:
        return calc.calculate_month(month)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/history")
def history():
    """Return running balances for all roommates across all months."""
    months_df = db.get_months().sort_values("month")
    if months_df.empty:
        return []
    latest_month = months_df.iloc[-1]["month"]
    try:
        result = calc.calculate_month(latest_month)
    except ValueError:
        return []
    return result["running_balances"]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
@app.get("/api/export/{month}")
def export_month(month: str):
    try:
        path = export.generate_month_report(month)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )
