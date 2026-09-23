"""
Pydantic request/response models for the electricity bill splitter backend.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Roommates
# ---------------------------------------------------------------------------
class RoommateBase(BaseModel):
    name: str = Field(..., min_length=1, description="Display name of the roommate")
    join_date: Optional[str] = Field(None, description="YYYY-MM month the roommate joined")
    leave_date: Optional[str] = Field(None, description="YYYY-MM month the roommate left")
    is_active: bool = Field(True, description="Whether the roommate is currently active")


class RoommateCreate(RoommateBase):
    pass


class RoommateOut(RoommateBase):
    id: int = Field(..., description="Row id in the roommates sheet")


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------
class MonthBase(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="Billing month in YYYY-MM format")
    main_start_reading: Optional[float] = Field(None, description="Main meter reading at start of month")
    main_end_reading: Optional[float] = Field(None, description="Main meter reading at end of month")
    monthly_bill: float = Field(..., ge=0, description="Electricity bill amount (excluding DG)")
    dg_bill: float = Field(0.0, ge=0, description="DG bill amount")
    notes: Optional[str] = Field(None, description="Free-form notes")


class MonthCreate(MonthBase):
    pass


class MonthOut(MonthBase):
    pass


class MonthDetail(MonthOut):
    readings: List[ReadingOut] = []


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------
class ReadingBase(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    roommate_id: int = Field(..., ge=1)
    current_reading: float = Field(..., ge=0)


class ReadingCreate(ReadingBase):
    pass


class ReadingUpdate(BaseModel):
    current_reading: float = Field(..., ge=0)


class ReadingOut(ReadingBase):
    pass


# ---------------------------------------------------------------------------
# Recharges
# ---------------------------------------------------------------------------
class RechargeBase(BaseModel):
    model_config = {"populate_by_name": True}
    recharge_date: date = Field(..., alias="date", description="Date of payment / recharge")
    roommate_id: int = Field(..., ge=1)
    amount: float = Field(..., gt=0)
    notes: Optional[str] = Field(None, description="Free-form notes")


class RechargeCreate(RechargeBase):
    month: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}$", description="Optional month tag")


class RechargeUpdate(BaseModel):
    model_config = {"populate_by_name": True}
    recharge_date: Optional[date] = Field(None, alias="date")
    roommate_id: Optional[int] = Field(None, ge=1)
    amount: Optional[float] = Field(None, gt=0)
    notes: Optional[str] = None


class RechargeOut(RechargeBase):
    id: int
    month: str


# ---------------------------------------------------------------------------
# Calculation / split
# ---------------------------------------------------------------------------
class RoommateSplit(BaseModel):
    roommate_id: int
    name: str
    previous_reading: Optional[float]
    current_reading: float
    sub_units: float
    common_share: float
    total_units: float
    energy_charge: float
    dg_share: float
    total_bill: float
    recharges: float
    balance: float


class RunningBalance(BaseModel):
    roommate_id: int
    name: str
    total_bill_cumulative: float
    total_recharges_cumulative: float
    balance: float


class CalculationSummary(BaseModel):
    main_units: float
    rate_per_unit: float
    total_bill: float
    dg_bill: float


class MonthCalculation(BaseModel):
    month: str
    summary: CalculationSummary
    roommates: List[RoommateSplit]
    running_balances: List[RunningBalance]
