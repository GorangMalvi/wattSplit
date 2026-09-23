"""
FastAPI backend for the electricity bill splitter.

Every data route needs a Supabase access token (``Authorization: Bearer``)
and an ``X-Household-Id`` header naming a household the user belongs to.

Any member can read the household. The owner can change anything; other
members can only change the readings and payments of the roommate their
login is linked to (see ``/api/me``).
"""
from __future__ import annotations

import html
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from . import calc, db, export, mailer, meter_report
from .auth import current_claims, current_user_id
from .models import (
    Dashboard,
    HouseholdCreate,
    HouseholdJoin,
    HouseholdOut,
    InviteAccept,
    InviteCreate,
    InviteLookup,
    InviteOut,
    InviteSent,
    LinkRoommate,
    MeOut,
    MeterReportResult,
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
    RunningBalance,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.open_pool()
    yield
    db.close_pool()


app = FastAPI(title="Electricity Bill Splitter", lifespan=lifespan)

# CORS for the Vite dev server and the Android app (Capacitor serves it from
# https://localhost). Extra origins: comma-separated CORS_ORIGINS.
CORS_ORIGINS = ["http://localhost:5173", "https://localhost"] + [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MonthParam = Annotated[str, Path(pattern=r"^\d{4}-\d{2}$")]
UserId = Annotated[str, Depends(current_user_id)]


@dataclass(frozen=True)
class Member:
    hid: UUID
    user_id: str
    role: str
    roommate_id: Optional[int]  # the roommate this login is linked to

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


def current_member(user_id: UserId, x_household_id: UUID = Header(...)) -> Member:
    """FastAPI dependency: the user's membership of the household in X-Household-Id."""
    membership = db.get_membership(user_id, x_household_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="You are not a member of this household")
    return Member(x_household_id, user_id, membership["role"], membership["roommate_id"])


CurrentMember = Annotated[Member, Depends(current_member)]


def current_household(member: CurrentMember) -> UUID:
    return member.hid


def owned_household(member: CurrentMember) -> UUID:
    """Like current_household, but only for the household owner."""
    if not member.is_owner:
        raise HTTPException(status_code=403, detail="Only the household owner can change this")
    return member.hid


HouseholdId = Annotated[UUID, Depends(current_household)]
OwnedHouseholdId = Annotated[UUID, Depends(owned_household)]


def _recharge_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "date": row["date"],
        "roommate_id": row["roommate_id"],
        "amount": row["amount"],
        "notes": row["notes"],
        "meter": row.get("meter") or "main",
        "month": row["date"][:7],
    }


def _require_roommate(hid: UUID, roommate_id: int) -> None:
    if db.get_roommate(hid, roommate_id) is None:
        raise HTTPException(status_code=404, detail="Roommate not found")


def _require_editable_roommate(member: Member, roommate_id: int) -> None:
    """The owner may edit any roommate's readings/payments, others only their own."""
    if member.is_owner:
        _require_roommate(member.hid, roommate_id)
    elif member.roommate_id != roommate_id:
        raise HTTPException(status_code=403, detail="You can only change your own readings and payments")


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
def join_household(payload: HouseholdJoin, claims: Annotated[dict, Depends(current_claims)]):
    """Join with the household's code, or with a personal invite code."""
    household = db.join_household(claims["sub"], payload.invite_code)
    if household is not None:
        return household
    try:
        return db.accept_invite(payload.invite_code, claims["sub"], claims.get("email"))
    except db.InviteError as exc:
        if exc.status == 404:
            raise HTTPException(status_code=404, detail="No household or invite with that code")
        raise HTTPException(status_code=exc.status, detail=str(exc))


# ---------------------------------------------------------------------------
# Personal invites (owner invites someone by email to be a roommate)
# ---------------------------------------------------------------------------
def _app_url(request: Request) -> Optional[str]:
    """
    Public web address of the app for invite links: APP_URL, else the web page
    the owner is using. The Android app's origin (https://localhost) is not
    reachable from anyone else's device, so it gives no link.
    """
    url = os.environ.get("APP_URL", "").strip().rstrip("/")
    if url:
        return url
    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin.startswith(("http://", "https://")) and origin != "https://localhost":
        return origin
    return None


def _invite_out(row: dict, app_url: Optional[str]) -> dict:
    return {
        **{k: row[k] for k in ("id", "roommate_id", "roommate", "email", "code", "expires_at")},
        "link": f"{app_url}/?invite={row['code']}" if app_url else None,
    }


def _send_invite_email(invite: dict) -> Optional[str]:
    """Email the invite; returns None when sent, else why it wasn't."""
    household, roommate = invite["household"], invite["roommate"]
    expires = invite["expires_at"].strftime("%d %b %Y")
    steps = (
        f"Open wattSplit, sign in with this email ({invite['email']}), choose "
        f"\"Join with a code\" and enter: {invite['code']}"
    )
    text = (
        f"You've been added as {roommate} in {household} on wattSplit, the flat's electricity bill "
        f"splitter.\n\n"
        + (f"Join here: {invite['link']}\n\nOr: " if invite["link"] else "")
        + f"{steps}\n\nThis invite expires on {expires}."
    )
    e = html.escape
    button = (
        f'<p><a href="{e(invite["link"])}" style="background:#4f46e5;color:#fff;padding:10px 18px;'
        f'border-radius:6px;text-decoration:none;display:inline-block">Join {e(household)}</a></p>'
        if invite["link"] else ""
    )
    body = (
        f"<p>You've been added as <b>{e(roommate)}</b> in <b>{e(household)}</b> on wattSplit, the flat's "
        f"electricity bill splitter.</p>{button}"
        f"<p>{'Or open' if button else 'Open'} wattSplit, sign in with this email ({e(invite['email'])}), "
        f"choose <i>Join with a code</i> and enter:</p>"
        f"<p style=\"font-size:22px;letter-spacing:4px;font-family:monospace\"><b>{e(invite['code'])}</b></p>"
        f"<p style=\"color:#64748b\">This invite expires on {expires}.</p>"
    )
    try:
        result = mailer.send_email(
            invite["email"], f"You're invited to {household} on wattSplit", text, html=body,
            category="Roommate invite",
        )
    except Exception as exc:  # Mailtrap/SDK errors: report, the owner can share the link instead
        return str(exc)[:200] or type(exc).__name__
    if not getattr(result, "success", None) and not (isinstance(result, dict) and result.get("success")):
        return "The email service didn't accept the message"
    return None


@app.post("/api/roommates/{roommate_id}/invite", response_model=InviteSent)
def invite_roommate(roommate_id: int, payload: InviteCreate, request: Request, member: CurrentMember):
    """Owner: invite someone by email to be this roommate (link + code, emailed to them)."""
    if not member.is_owner:
        raise HTTPException(status_code=403, detail="Only the household owner can invite roommates")
    roommate = db.get_roommate(member.hid, roommate_id)
    if roommate is None:
        raise HTTPException(status_code=404, detail="Roommate not found")
    if roommate["linked"]:
        raise HTTPException(status_code=409, detail=f"{roommate['name']} has already joined")
    invite = db.create_invite(member.hid, roommate_id, payload.email, member.user_id)
    out = _invite_out(invite, _app_url(request))
    error = _send_invite_email({**invite, "link": out["link"]})
    return {**out, "email_sent": error is None, "email_error": error}


@app.get("/api/invites", response_model=List[InviteOut])
def list_invites(request: Request, hid: OwnedHouseholdId):
    app_url = _app_url(request)
    return [_invite_out(i, app_url) for i in db.list_invites(hid)]


@app.delete("/api/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: int, hid: OwnedHouseholdId):
    if not db.delete_invite(hid, invite_id):
        raise HTTPException(status_code=404, detail="Invite not found")
    return None


@app.get("/api/invites/lookup/{code}", response_model=InviteLookup)
def lookup_invite(code: str = Path(..., min_length=4, max_length=16)):
    """No sign-in needed: lets an invite link greet the person before they log in."""
    try:
        invite = db.lookup_invite(code)
    except db.InviteError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    return {"household": invite["household"], "roommate": invite["roommate"], "email": invite["email"]}


@app.post("/api/invites/accept", response_model=HouseholdOut)
def accept_invite(payload: InviteAccept, claims: Annotated[dict, Depends(current_claims)]):
    try:
        return db.accept_invite(payload.code, claims["sub"], claims.get("email"))
    except db.InviteError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


# ---------------------------------------------------------------------------
# Roommates
# ---------------------------------------------------------------------------
@app.get("/api/roommates", response_model=List[RoommateOut])
def list_roommates(hid: HouseholdId):
    return db.list_roommates(hid)


@app.post("/api/roommates", response_model=RoommateOut, status_code=201)
def create_roommate(payload: RoommateCreate, hid: OwnedHouseholdId):
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
def update_roommate(roommate_id: int, payload: RoommateCreate, hid: OwnedHouseholdId):
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


@app.delete("/api/roommates/{roommate_id}/link", status_code=204)
def unlink_roommate(roommate_id: int, hid: OwnedHouseholdId):
    """Owner: detach whichever login is linked to this roommate."""
    _require_roommate(hid, roommate_id)
    db.unlink_roommate(hid, roommate_id)
    return None


# ---------------------------------------------------------------------------
# The signed-in user ("My dashboard")
# ---------------------------------------------------------------------------
@app.get("/api/me", response_model=MeOut)
def me(member: CurrentMember):
    roommate = None if member.roommate_id is None else db.get_roommate(member.hid, member.roommate_id)
    return {"role": member.role, "roommate": roommate}


@app.post("/api/me/roommate", response_model=MeOut)
def link_my_roommate(payload: LinkRoommate, member: CurrentMember):
    """Say which roommate you are: pick an unlinked one or add yourself by name."""
    if member.roommate_id is not None:
        raise HTTPException(status_code=409, detail=db.ALREADY_LINKED)
    try:
        if payload.roommate_id is not None:
            _require_roommate(member.hid, payload.roommate_id)
            roommate = db.link_roommate(member.hid, payload.roommate_id, member.user_id)
            if roommate is None:
                raise HTTPException(status_code=409, detail="Someone else is already linked to that roommate")
        else:
            roommate = db.add_roommate(
                member.hid,
                name=payload.name,
                join_date=date.today().strftime("%Y-%m"),
                user_id=member.user_id,
            )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"role": member.role, "roommate": roommate}


@app.delete("/api/me/roommate", status_code=204)
def unlink_my_roommate(member: CurrentMember):
    db.unlink_user(member.hid, member.user_id)
    return None


@app.get("/api/me/dashboard", response_model=Dashboard)
def my_dashboard(member: CurrentMember):
    if member.roommate_id is None:
        raise HTTPException(status_code=404, detail="Link your login to a roommate first")
    data = db.HouseholdData(member.hid)
    roommate = next(r for r in data.roommate_rows if r["id"] == member.roommate_id)
    return {
        "roommate": roommate,
        **calc.personal_dashboard(roommate["name"], data),
        "recharges": [_recharge_out(r) for r in data.recharge_rows if r["roommate_id"] == roommate["id"]],
    }


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
    return {**row, "readings": db.list_readings(hid, month), "previous_readings": db.previous_readings(hid, month)}


@app.post("/api/months", response_model=MonthOut, status_code=201)
def create_month(payload: MonthCreate, hid: OwnedHouseholdId):
    try:
        return db.add_month(
            hid,
            month=payload.month,
            monthly_bill=payload.monthly_bill,
            dg_bill=payload.dg_bill,
            main_start_reading=payload.main_start_reading,
            main_end_reading=payload.main_end_reading,
            notes=payload.notes,
            meter_opening_balance=payload.meter_opening_balance,
            meter_recharge=payload.meter_recharge,
            meter_closing_balance=payload.meter_closing_balance,
        )
    except ValueError as exc:
        status = 409 if "already exists" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc))


@app.put("/api/months/{month}", response_model=MonthOut)
def update_month(month: MonthParam, payload: MonthUpdate, hid: OwnedHouseholdId):
    try:
        updated = db.update_month(hid, month, **payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if updated is None:
        raise HTTPException(status_code=404, detail="Month not found")
    return updated


MAX_REPORT_BYTES = 2 * 1024 * 1024


@app.post("/api/meter-report", response_model=MeterReportResult)
async def import_meter_report(request: Request, hid: OwnedHouseholdId, dry_run: bool = Query(False)):
    """
    Owner: upload the meter provider's Monthly Consumption Report (.xlsx, sent
    as the raw request body). ``dry_run=true`` only previews what would change.
    """
    content = await request.body()
    if len(content) > MAX_REPORT_BYTES:
        raise HTTPException(status_code=413, detail="The report file is too large (max 2 MB)")
    try:
        months = await run_in_threadpool(meter_report.parse, content)
    except meter_report.ReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    existing = {m["month"]: m for m in await run_in_threadpool(db.list_months, hid)}
    if not dry_run:
        await run_in_threadpool(db.import_meter_months, hid, months)
    return {
        "imported": not dry_run,
        "months": [
            {
                **m,
                "rate_per_unit": m["monthly_bill"] / m["units"] if m["units"] else 0.0,
                "exists": m["month"] in existing,
                "current_bill": existing.get(m["month"], {}).get("monthly_bill"),
            }
            for m in months
        ],
    }


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------
@app.put("/api/readings/{month}/{roommate_id}")
def update_reading(month: MonthParam, roommate_id: int, payload: ReadingUpdate, member: CurrentMember):
    if db.get_month(member.hid, month) is None:
        raise HTTPException(status_code=404, detail="Month not found")
    _require_editable_roommate(member, roommate_id)
    fields = payload.model_dump(include=payload.model_fields_set)
    db.set_reading(member.hid, month, roommate_id, **fields)
    return {"month": month, "roommate_id": roommate_id, **fields}


@app.delete("/api/readings/{month}/{roommate_id}", status_code=204)
def delete_reading(month: MonthParam, roommate_id: int, member: CurrentMember):
    _require_editable_roommate(member, roommate_id)
    if not db.delete_reading(member.hid, month, roommate_id):
        raise HTTPException(status_code=404, detail="No reading for that month")
    return None


# ---------------------------------------------------------------------------
# Recharges
# ---------------------------------------------------------------------------
def _require_editable_recharge(member: Member, recharge_id: int) -> None:
    existing = db.get_recharge(member.hid, recharge_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Recharge not found")
    _require_editable_roommate(member, existing["roommate_id"])


@app.get("/api/recharges", response_model=List[RechargeOut])
def list_recharges(hid: HouseholdId, month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$")):
    return [_recharge_out(r) for r in db.list_recharges(hid, month)]


@app.post("/api/recharges", response_model=RechargeOut, status_code=201)
def create_recharge(payload: RechargeCreate, member: CurrentMember):
    _require_editable_roommate(member, payload.roommate_id)
    rid = db.add_recharge(
        member.hid,
        date=payload.recharge_date.isoformat(),
        roommate_id=payload.roommate_id,
        amount=payload.amount,
        notes=payload.notes or "",
        meter=payload.meter,
    )
    return _recharge_out(db.get_recharge(member.hid, rid))


@app.put("/api/recharges/{recharge_id}", response_model=RechargeOut)
def update_recharge(recharge_id: int, payload: RechargeUpdate, member: CurrentMember):
    _require_editable_recharge(member, recharge_id)
    data = payload.model_dump(exclude_unset=True, by_alias=True)
    if data.get("roommate_id") is not None:
        _require_editable_roommate(member, data["roommate_id"])
    if data.get("date") is not None:
        data["date"] = data["date"].isoformat()
    if not db.update_recharge(member.hid, recharge_id, **data):
        raise HTTPException(status_code=404, detail="Recharge not found")
    return _recharge_out(db.get_recharge(member.hid, recharge_id))


@app.delete("/api/recharges/{recharge_id}", status_code=204)
def delete_recharge(recharge_id: int, member: CurrentMember):
    _require_editable_recharge(member, recharge_id)
    if not db.delete_recharge(member.hid, recharge_id):
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


@app.get("/api/history", response_model=List[RunningBalance])
def history(hid: HouseholdId):
    """Balances to date for every roommate: all bills so far minus all payments."""
    return calc.household_balances(db.HouseholdData(hid))


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
