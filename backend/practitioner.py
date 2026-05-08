"""Practitioner-facing endpoints.

Auth: simple PIN check → returns a session cookie. Cookie carries the practitioner_id
so the rest of the routes can scope queries.
"""
from datetime import datetime, timedelta, date, time
from typing import Optional
from fastapi import APIRouter, Request, Response, Cookie, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from pathlib import Path

from backend.config import settings
from backend.db.database import get_db
from backend.models.schema import Practitioner, Client, Booking
from backend.logic.availability import get_working_slots
from backend.logic.booking import (
    create_booking,
    cancel_booking,
    reschedule_booking,
    BookingError,
)

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
            Booking.starts_at >= datetime.combine(start_date, time.min),
            Booking.starts_at < datetime.combine(end_date, time.min),
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
    now = datetime.utcnow()
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
    result = await execute_instruction(db, p, instruction)
    return result
