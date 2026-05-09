"""Practitioner-facing endpoints.

Auth: simple PIN check → returns a session cookie. Cookie carries the practitioner_id
so the rest of the routes can scope queries.
"""
from datetime import datetime, timedelta, date, time
from typing import Optional
from fastapi import APIRouter, Request, Response, Cookie, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from pathlib import Path

from backend.config import settings
from backend.db.database import get_db
from backend.models.schema import Practitioner, Client, Booking, Message, Package, TimeBlock
from backend.logic.availability import get_working_slots
from backend.logic.booking import (
    create_booking,
    cancel_booking,
    reschedule_booking,
    get_or_create_client,
    set_client_name,
    BookingError,
)
from backend.logic.packages import create_package, list_packages, sessions_remaining
from backend.timezone import ROME_TZ

router = APIRouter()

STATIC_DIR = Path(__file__).parent / "static"
COOKIE_NAME = "dora_pract"


def _get_practitioner(db: Session, pid: Optional[str]) -> Practitioner:
    if not pid:
        raise HTTPException(status_code=401, detail="Login required")
    p = db.query(Practitioner).filter_by(id=pid).first()
    if not p:
        raise HTTPException(status_code=401, detail="Invalid session")
    return p


@router.get("/practitioner")
def practitioner_page():
    return FileResponse(STATIC_DIR / "practitioner.html")


@router.post("/practitioner/api/login")
async def login(request: Request, response: Response, db: Session = Depends(get_db)):
    body = await request.json()
    pin = str(body.get("pin", ""))
    if pin != settings.practitioner_pin:
        raise HTTPException(status_code=401, detail="PIN errato")
    p = db.query(Practitioner).first()
    if not p:
        raise HTTPException(status_code=500, detail="No practitioner configured")
    response.set_cookie(
        COOKIE_NAME, str(p.id),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
    )
    return {"status": "ok", "name": p.name}


@router.post("/practitioner/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"status": "ok"}


@router.get("/practitioner/api/me")
def me(db: Session = Depends(get_db), dora_pract: Optional[str] = Cookie(None)):
    p = _get_practitioner(db, dora_pract)
    return {
        "id": str(p.id),
        "name": p.name,
        "profession": p.profession,
        "working_hours": p.working_hours,
        "services": p.services,
    }


@router.get("/practitioner/api/agenda")
def agenda(
    week_start: Optional[str] = None,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    if week_start:
        start_date = date.fromisoformat(week_start)
    else:
        today = date.today()
        start_date = today - timedelta(days=today.weekday())
    end_date = start_date + timedelta(days=7)

    bookings = (
        db.query(Booking)
        .filter(
            Booking.practitioner_id == p.id,
            Booking.starts_at >= datetime.combine(start_date, time.min, tzinfo=ROME_TZ),
            Booking.starts_at < datetime.combine(end_date, time.min, tzinfo=ROME_TZ),
        )
        .order_by(Booking.starts_at)
        .all()
    )

    clients_by_id = {c.id: c for c in db.query(Client).filter_by(practitioner_id=p.id).all()}

    return {
        "week_start": start_date.isoformat(),
        "week_end": end_date.isoformat(),
        "bookings": [
            {
                "id": str(b.id),
                "client_id": str(b.client_id),
                "client_name": clients_by_id[b.client_id].full_name if b.client_id in clients_by_id else "?",
                "client_phone": clients_by_id[b.client_id].phone if b.client_id in clients_by_id else "",
                "service": b.service,
                "starts_at": b.starts_at.isoformat(),
                "duration_minutes": b.duration_minutes,
                "status": b.status,
                "created_via": b.created_via,
            }
            for b in bookings
        ],
    }


@router.get("/practitioner/api/today")
def today_summary(db: Session = Depends(get_db), dora_pract: Optional[str] = Cookie(None)):
    """Compact 'now' view: today's bookings + the next upcoming one."""
    p = _get_practitioner(db, dora_pract)
    now = datetime.now(ROME_TZ)
    day_start = datetime.combine(now.date(), time.min, tzinfo=ROME_TZ)
    day_end = day_start + timedelta(days=1)

    todays = (
        db.query(Booking)
        .filter(
            Booking.practitioner_id == p.id,
            Booking.starts_at >= day_start,
            Booking.starts_at < day_end,
        )
        .order_by(Booking.starts_at)
        .all()
    )

    next_upcoming = (
        db.query(Booking)
        .filter(
            Booking.practitioner_id == p.id,
            Booking.status == "confirmed",
            Booking.starts_at >= now,
        )
        .order_by(Booking.starts_at)
        .first()
    )

    clients = {c.id: c for c in db.query(Client).filter_by(practitioner_id=p.id).all()}

    def serialize(b):
        return {
            "id": str(b.id),
            "client_name": clients[b.client_id].full_name if b.client_id in clients else "?",
            "client_phone": clients[b.client_id].phone if b.client_id in clients else "",
            "service": b.service,
            "starts_at": b.starts_at.isoformat(),
            "duration_minutes": b.duration_minutes,
            "status": b.status,
        }

    return {
        "now": now.isoformat(),
        "today": [serialize(b) for b in todays],
        "next_upcoming": serialize(next_upcoming) if next_upcoming else None,
    }


@router.get("/practitioner/api/clients")
def list_clients(db: Session = Depends(get_db), dora_pract: Optional[str] = Cookie(None)):
    p = _get_practitioner(db, dora_pract)
    clients = (
        db.query(Client)
        .filter_by(practitioner_id=p.id)
        .order_by(desc(Client.last_seen))
        .all()
    )
    # Count upcoming bookings per client
    now = datetime.now(ROME_TZ)
    upcoming_counts = {}
    rows = (
        db.query(Booking.client_id)
        .filter(
            Booking.practitioner_id == p.id,
            Booking.status == "confirmed",
            Booking.starts_at >= now,
        )
        .all()
    )
    for (cid,) in rows:
        upcoming_counts[cid] = upcoming_counts.get(cid, 0) + 1

    return {
        "clients": [
            {
                "id": str(c.id),
                "first_name": c.first_name,
                "last_name": c.last_name,
                "name": c.full_name,
                "phone": c.phone,
                "notes": c.notes,
                "last_seen": c.last_seen.isoformat() if c.last_seen else None,
                "upcoming_bookings": upcoming_counts.get(c.id, 0),
            }
            for c in clients
        ]
    }


@router.get("/practitioner/api/availability")
def get_availability(
    target_date: str,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    d = date.fromisoformat(target_date)
    slots = get_working_slots(db, p.id, d)
    return {"date": target_date, "slots": [s.isoformat() for s in slots]}


@router.post("/practitioner/api/bookings")
async def create_manual_booking(
    request: Request,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    body = await request.json()
    client_id = body.get("client_id")
    starts_at = datetime.fromisoformat(body["starts_at"])
    service = body.get("service", "Pilates Individuale")
    duration = int(body.get("duration_minutes", 55))
    try:
        booking = create_booking(
            db, p.id, client_id, starts_at, service, duration, created_via="dashboard"
        )
        return {"id": str(booking.id), "starts_at": booking.starts_at.isoformat()}
    except BookingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/practitioner/api/bookings/{booking_id}")
def cancel_manual_booking(
    booking_id: str,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    b = db.get(Booking, booking_id)
    if not b or b.practitioner_id != p.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    cancel_booking(db, b.id)
    return {"status": "cancelled"}


@router.patch("/practitioner/api/bookings/{booking_id}")
async def reschedule_manual_booking(
    booking_id: str,
    request: Request,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    b = db.get(Booking, booking_id)
    if not b or b.practitioner_id != p.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    body = await request.json()
    new_when = datetime.fromisoformat(body["starts_at"])
    try:
        reschedule_booking(db, b.id, new_when)
        return {"status": "rescheduled", "starts_at": new_when.isoformat()}
    except BookingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/practitioner/api/packages")
def get_packages(db: Session = Depends(get_db), dora_pract: Optional[str] = Cookie(None)):
    p = _get_practitioner(db, dora_pract)
    pkgs = list_packages(db, p.id)
    clients_by_id = {c.id: c for c in db.query(Client).filter_by(practitioner_id=p.id).all()}
    return {
        "packages": [
            {
                "id": str(pkg.id),
                "client_id": str(pkg.client_id),
                "client_name": clients_by_id[pkg.client_id].full_name if pkg.client_id in clients_by_id else "?",
                "total_sessions": pkg.total_sessions,
                "used_sessions": pkg.used_sessions,
                "remaining": sessions_remaining(pkg),
                "purchase_date": pkg.purchase_date.isoformat() if pkg.purchase_date else None,
                "expiry_date": pkg.expiry_date.isoformat() if pkg.expiry_date else None,
                "payment_status": pkg.payment_status,
                "notes": pkg.notes,
            }
            for pkg in pkgs
        ]
    }


@router.post("/practitioner/api/packages")
async def create_pkg(
    request: Request,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    body = await request.json()
    expiry = date.fromisoformat(body["expiry_date"]) if body.get("expiry_date") else None
    pkg = create_package(
        db, p.id, body["client_id"],
        total_sessions=int(body["total_sessions"]),
        expiry_date=expiry,
        payment_status=body.get("payment_status", "paid"),
        notes=body.get("notes"),
    )
    return {"id": str(pkg.id)}


@router.get("/practitioner/api/messages/{client_id}")
def get_client_messages(
    client_id: str,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    client = db.get(Client, client_id)
    if not client or client.practitioner_id != p.id:
        raise HTTPException(status_code=404, detail="Client not found")
    msgs = (
        db.query(Message)
        .filter_by(client_id=client.id)
        .order_by(Message.created_at)
        .limit(100)
        .all()
    )
    return {
        "client": {"name": client.full_name, "phone": client.phone},
        "messages": [
            {
                "direction": m.direction,
                "body": m.body,
                "intent": m.intent,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ],
    }


@router.post("/practitioner/api/instruct")
async def natural_language_instruction(
    request: Request,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    """Receive a natural-language instruction from the practitioner and execute it."""
    p = _get_practitioner(db, dora_pract)
    body = await request.json()
    instruction = body.get("instruction", "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="Empty instruction")
    from backend.ai.practitioner_nlp import execute_instruction
    confirm = bool(body.get("confirm", False))
    result = await execute_instruction(db, p, instruction, confirm=confirm)
    return result


# ---------------------------------------------------------------------------
# Clients (manual create)
# ---------------------------------------------------------------------------

@router.post("/practitioner/api/clients")
async def create_client_manual(
    request: Request,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    body = await request.json()
    phone = body.get("phone", "").strip()
    first_name = body.get("first_name", "").strip()
    last_name = body.get("last_name", "").strip() or None
    if not phone or not first_name:
        raise HTTPException(status_code=400, detail="phone and first_name required")
    existing = db.query(Client).filter_by(phone=phone).first()
    if existing:
        if not existing.first_name:
            set_client_name(db, existing, first_name, last_name)
        return {"id": str(existing.id), "created": False}
    client = get_or_create_client(db, p.id, phone, first_name)
    set_client_name(db, client, first_name, last_name)
    return {"id": str(client.id), "created": True}


# ---------------------------------------------------------------------------
# Time blocks (vacation, day off, blocked hours)
# ---------------------------------------------------------------------------

@router.get("/practitioner/api/blocks")
def list_blocks(db: Session = Depends(get_db), dora_pract: Optional[str] = Cookie(None)):
    p = _get_practitioner(db, dora_pract)
    now = datetime.now(ROME_TZ)
    blocks = (
        db.query(TimeBlock)
        .filter(TimeBlock.practitioner_id == p.id, TimeBlock.ends_at >= now)
        .order_by(TimeBlock.starts_at)
        .all()
    )
    return {
        "blocks": [
            {
                "id": str(b.id),
                "starts_at": b.starts_at.isoformat(),
                "ends_at": b.ends_at.isoformat(),
                "reason": b.reason,
            }
            for b in blocks
        ]
    }


@router.post("/practitioner/api/blocks")
async def create_block(
    request: Request,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    body = await request.json()
    starts_at = datetime.fromisoformat(body["starts_at"])
    ends_at = datetime.fromisoformat(body["ends_at"])
    if ends_at <= starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    # Localize naive datetimes to Europe/Rome (UI sends local times)
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=ROME_TZ)
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=ROME_TZ)
    block = TimeBlock(
        practitioner_id=p.id,
        starts_at=starts_at,
        ends_at=ends_at,
        reason=body.get("reason"),
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return {"id": str(block.id)}


@router.delete("/practitioner/api/blocks/{block_id}")
def delete_block(
    block_id: str,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    b = db.get(TimeBlock, block_id)
    if not b or b.practitioner_id != p.id:
        raise HTTPException(status_code=404, detail="Block not found")
    db.delete(b)
    db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Settings: working hours, services, profession
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Google OAuth: connect, callback, disconnect, list/select calendar
# ---------------------------------------------------------------------------

OAUTH_STATE_COOKIE = "dora_oauth_state"


@router.get("/practitioner/api/gcal/status")
def gcal_oauth_status(db: Session = Depends(get_db), dora_pract: Optional[str] = Cookie(None)):
    p = _get_practitioner(db, dora_pract)
    from backend.integrations import google_oauth
    return {
        "configured": google_oauth.is_configured(),
        "connected": bool(p.gcal_oauth_refresh_token),
        "email": p.gcal_oauth_email,
        "calendar_id": p.gcal_oauth_calendar_id,
    }


@router.get("/practitioner/api/gcal/connect")
def gcal_connect(response: Response, db: Session = Depends(get_db), dora_pract: Optional[str] = Cookie(None)):
    """Build the Google authorize URL and set a state cookie for CSRF protection."""
    _get_practitioner(db, dora_pract)  # auth check
    from backend.integrations import google_oauth
    if not google_oauth.is_configured():
        raise HTTPException(status_code=500, detail="OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID/SECRET.")
    url, state = google_oauth.make_authorize_url()
    response.set_cookie(
        OAUTH_STATE_COOKIE, state,
        max_age=600, httponly=True, samesite="lax",
        secure=settings.app_env == "production",
    )
    return {"authorize_url": url}


@router.get("/practitioner/api/gcal/callback")
async def gcal_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
    dora_oauth_state: Optional[str] = Cookie(None),
):
    """Google redirects here after the user grants consent."""
    p = _get_practitioner(db, dora_pract)
    if error:
        return RedirectResponse(f"/practitioner?gcal_error={error}")
    if not code or not state or state != dora_oauth_state:
        return RedirectResponse("/practitioner?gcal_error=state_mismatch")

    from backend.integrations import google_oauth
    try:
        tokens = await google_oauth.exchange_code(code)
    except Exception as e:
        return RedirectResponse(f"/practitioner?gcal_error=exchange_failed")

    refresh = tokens.get("refresh_token")
    access = tokens.get("access_token")
    if not refresh:
        # User has previously consented and refresh_token wasn't returned. Try the
        # alternate flow next time by forcing prompt=consent (already in our URL).
        return RedirectResponse("/practitioner?gcal_error=no_refresh_token")

    email = ""
    if access:
        info = await google_oauth.fetch_userinfo(access)
        email = info.get("email", "")

    p.gcal_oauth_refresh_token = refresh
    p.gcal_oauth_email = email
    p.gcal_oauth_calendar_id = "primary"  # default; user can change later
    db.commit()

    response = RedirectResponse("/practitioner?gcal=connected")
    response.delete_cookie(OAUTH_STATE_COOKIE)
    return response


@router.post("/practitioner/api/gcal/disconnect")
def gcal_disconnect(db: Session = Depends(get_db), dora_pract: Optional[str] = Cookie(None)):
    p = _get_practitioner(db, dora_pract)
    p.gcal_oauth_refresh_token = None
    p.gcal_oauth_email = None
    p.gcal_oauth_calendar_id = None
    db.commit()
    return {"status": "disconnected"}


@router.get("/practitioner/api/gcal/calendars")
def gcal_list_calendars(db: Session = Depends(get_db), dora_pract: Optional[str] = Cookie(None)):
    p = _get_practitioner(db, dora_pract)
    from backend.integrations import google_calendar
    return {"calendars": google_calendar.list_calendars_for_practitioner(p)}


@router.patch("/practitioner/api/gcal/calendar")
async def gcal_set_calendar(
    request: Request,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    body = await request.json()
    cal_id = body.get("calendar_id")
    if not cal_id:
        raise HTTPException(status_code=400, detail="calendar_id required")
    p.gcal_oauth_calendar_id = cal_id
    db.commit()
    return {"calendar_id": cal_id}


@router.patch("/practitioner/api/settings")
async def update_settings(
    request: Request,
    db: Session = Depends(get_db),
    dora_pract: Optional[str] = Cookie(None),
):
    p = _get_practitioner(db, dora_pract)
    body = await request.json()
    if "working_hours" in body:
        # Expect {mon: [{start, end}], ...}; sanitize to known day keys
        valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        wh = {k: v for k, v in body["working_hours"].items() if k in valid_days and isinstance(v, list)}
        p.working_hours = wh
    if "services" in body:
        p.services = body["services"]
    if "profession" in body:
        p.profession = body["profession"]
    if "break_minutes" in body:
        p.break_minutes = int(body["break_minutes"])
    db.commit()
    db.refresh(p)
    return {"working_hours": p.working_hours, "services": p.services, "profession": p.profession, "break_minutes": p.break_minutes}
