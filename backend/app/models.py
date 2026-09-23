"""
Pydantic request/response models for the electricity bill splitter backend.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Households
# ---------------------------------------------------------------------------
class HouseholdCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80, description="Flat / household name")


class HouseholdJoin(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=16)


class HouseholdOut(BaseModel):
    id: UUID
    name: str
    invite_code: str
    role: str


EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class InviteCreate(BaseModel):
    email: str = Field(..., max_length=254, pattern=EMAIL_PATTERN)


class InviteOut(BaseModel):
    id: int
    roommate_id: int
    roommate: str
    email: str
    code: str
    link: Optional[str] = Field(None, description="Join link, when the app's public URL is known")
    expires_at: datetime


class InviteSent(InviteOut):
    email_sent: bool
    email_error: Optional[str] = None


class InviteLookup(BaseModel):
    """What an invite link shows before signing in."""
    household: str
    roommate: str
    email: str


class InviteAccept(BaseModel):
    code: str = Field(..., min_length=4, max_length=16)


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
    id: int = Field(..., description="Roommate id")
    linked: bool = Field(False, description="Whether a login is linked to this roommate")


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


class MeterBalances(BaseModel):
    """
    Prepaid main meter money for the month (entered by hand or from the meter
    report). When all three are set, monthly_bill = opening + recharge - closing.
    """
    meter_opening_balance: Optional[float] = Field(None, description="Balance at month start (can be negative)")
    meter_recharge: Optional[float] = Field(None, ge=0, description="Recharged into the meter this month")
    meter_closing_balance: Optional[float] = Field(None, description="Balance at month end, carried forward")


class MonthCreate(MonthBase, MeterBalances):
    """A blank opening balance is carried over from the previous month's closing balance."""


class MonthUpdate(MeterBalances):
    main_start_reading: Optional[float] = None
    main_end_reading: Optional[float] = None
    monthly_bill: Optional[float] = Field(None, ge=0)
    dg_bill: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class MonthOut(MonthBase, MeterBalances):
    pass


class MeterReportMonth(BaseModel):
    month: str
    main_start_reading: float
    main_end_reading: float
    units: float
    energy_charge: Optional[float]
    meter_opening_balance: float
    meter_recharge: float
    meter_closing_balance: float
    monthly_bill: float = Field(..., description="Amount deducted: opening + recharge - closing")
    rate_per_unit: float
    exists: bool = Field(..., description="Month already in the app (will be updated)")
    current_bill: Optional[float] = Field(None, description="Its monthly bill before this import")


class MeterReportResult(BaseModel):
    imported: bool
    months: List[MeterReportMonth]


class MonthDetail(MonthOut):
    readings: List[ReadingOut] = []
    # Last month's month-end readings: where this month starts for each roommate.
    previous_readings: List[PreviousReading] = []


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------
class ReadingOut(BaseModel):
    month: str
    roommate_id: int
    current_reading: Optional[float] = Field(None, description="Sub-meter at month end")
    start_reading: Optional[float] = Field(None, description="Sub-meter at month start, when entered")


class PreviousReading(BaseModel):
    roommate_id: int
    current_reading: float


class ReadingUpdate(BaseModel):
    """Send either or both; a field sent as null is cleared."""
    current_reading: Optional[float] = Field(None, ge=0)
    start_reading: Optional[float] = Field(None, ge=0)

    @model_validator(mode="after")
    def something_to_set(self) -> "ReadingUpdate":
        if not self.model_fields_set & {"current_reading", "start_reading"}:
            raise ValueError("Send current_reading and/or start_reading")
        return self


# ---------------------------------------------------------------------------
# Recharges
# ---------------------------------------------------------------------------
Meter = Literal["main", "dg"]


class RechargeBase(BaseModel):
    model_config = {"populate_by_name": True}
    recharge_date: date = Field(..., alias="date", description="Date of payment / recharge")
    roommate_id: int = Field(..., ge=1)
    amount: float = Field(..., gt=0)
    notes: Optional[str] = Field(None, description="Free-form notes")
    meter: Meter = Field("main", description="Paid towards the main meter or the DG")


class RechargeCreate(RechargeBase):
    month: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}$", description="Optional month tag")


class RechargeUpdate(BaseModel):
    model_config = {"populate_by_name": True}
    recharge_date: Optional[date] = Field(None, alias="date")
    roommate_id: Optional[int] = Field(None, ge=1)
    amount: Optional[float] = Field(None, gt=0)
    notes: Optional[str] = None
    meter: Optional[Meter] = None


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
    # Per meter: energy charge vs main payments, DG share vs DG payments.
    recharges_main: float
    recharges_dg: float
    main_balance: float
    dg_balance: float


class RunningBalance(BaseModel):
    roommate_id: int
    name: str
    total_bill_cumulative: float
    total_recharges_cumulative: float
    balance: float
    main_bill_cumulative: float
    main_recharges_cumulative: float
    main_balance: float
    dg_bill_cumulative: float
    dg_recharges_cumulative: float
    dg_balance: float


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


# ---------------------------------------------------------------------------
# The signed-in user ("My dashboard")
# ---------------------------------------------------------------------------
class MeOut(BaseModel):
    role: str
    roommate: Optional[RoommateOut] = None


class LinkRoommate(BaseModel):
    """Either pick an existing roommate or add a new one with this name."""
    roommate_id: Optional[int] = Field(None, ge=1)
    name: Optional[str] = Field(None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def exactly_one(self) -> "LinkRoommate":
        if (self.roommate_id is None) == (self.name is None):
            raise ValueError("Send either roommate_id or name")
        return self


class DashboardMonth(BaseModel):
    month: str
    previous_reading: Optional[float]
    previous_editable: bool = Field(..., description="No reading last month: start_reading can be set")
    start_reading: Optional[float]
    current_reading: Optional[float]
    sub_units: Optional[float]
    is_active: bool
    billed: bool = Field(..., description="False until the month's split can be calculated")
    rate_per_unit: Optional[float]
    common_share: Optional[float]
    total_units: Optional[float]
    energy_charge: Optional[float]
    dg_share: Optional[float]
    total_bill: Optional[float]
    recharges: float
    recharges_main: float
    recharges_dg: float
    balance: Optional[float]
    main_balance: Optional[float]
    dg_balance: Optional[float]


class Dashboard(BaseModel):
    roommate: RoommateOut
    months: List[DashboardMonth]
    recharges: List[RechargeOut]
    total_bill_cumulative: float
    total_recharges_cumulative: float
    balance: float
    main_bill_cumulative: float
    main_recharges_cumulative: float
    main_balance: float
    dg_bill_cumulative: float
    dg_recharges_cumulative: float
    dg_balance: float
