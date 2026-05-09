from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.db.database import get_db
from backend.models.schema import Booking, Client, Practitioner, Package, Message
from backend.timezone import ROME_TZ

router = APIRouter(prefix="/api")


@router.get("/state")
def get_state(db: Session = Depends(get_db)):
    """Snapshot of current DB state — used by the test UI."""
    practitioners = db.query(Practitioner).all()
    clients = db.query(Client).order_by(desc(Client.last_seen)).all()
    bookings = (
        db.query(Booking)
        .order_by(desc(Booking.created_at))
        .limit(20)
        .all()
    )

    client_by_id = {c.id: c for c in clients}

    return {
        "practitioners": [
            {"id": str(p.id), "name": p.name, "profession": p.profession}
            for p in practitioners
        ],
        "clients": [
            {
                "id": str(c.id),
                "name": c.full_name,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "phone": c.phone,
                "last_seen": c.last_seen.isoformat() if c.last_seen else None,
            }
            for c in clients
        ],
        "bookings": [
            {
                "id": str(b.id),
                "client_phone": client_by_id[b.client_id].phone if b.client_id in client_by_id else None,
                "client_name": client_by_id[b.client_id].full_name if b.client_id in client_by_id else None,
                "service": b.service,
                "starts_at": b.starts_at.isoformat() if b.starts_at else None,
                "duration_minutes": b.duration_minutes,
                "status": b.status,
                "created_via": b.created_via,
            }
            for b in bookings
        ],
    }


@router.post("/reset")
def reset_test_data(db: Session = Depends(get_db)):
    """Wipe all clients/bookings/packages/messages (keep practitioners)."""
    db.query(Message).delete()
    db.query(Package).delete()
    db.query(Booking).delete()
    db.query(Client).delete()
    db.commit()
    return {"status": "reset"}


_DEMO_CLIENTS = [
    ("Marco", "Rossi", "+393331110001"),
    ("Giulia", "Bianchi", "+393331110002"),
    ("Luca", "Verdi", "+393331110003"),
    ("Anna", "Ferrari", "+393331110004"),
    ("Federico", "Gallo", "+393331110005"),
]


@router.post("/seed-demo")
def seed_demo(db: Session = Depends(get_db)):
    """Wipe and seed 5 demo clients with a few bookings — for showing off the UI."""
    db.query(Message).delete()
    db.query(Package).delete()
    db.query(Booking).delete()
    db.query(Client).delete()
    db.commit()

    silvia = db.query(Practitioner).first()
    if not silvia:
        return {"error": "No practitioner — run seed.py first."}

    created = []
    today = datetime.now(ROME_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    times_to_add = [
        (1, 9, 0),    # tomorrow 9:00
        (1, 10, 0),   # tomorrow 10:00
        (2, 14, 0),   # day after, 14:00
        (3, 11, 0),
        (4, 16, 0),
    ]

    for i, (first, last, phone) in enumerate(_DEMO_CLIENTS):
        c = Client(
            practitioner_id=silvia.id,
            phone=phone,
            name=f"{first} {last}",
            first_name=first,
            last_name=last,
        )
        db.add(c)
        db.flush()  # get id

        days_ahead, hour, minute = times_to_add[i]
        when = today + timedelta(days=days_ahead, hours=hour, minutes=minute)
        b = Booking(
            practitioner_id=silvia.id,
            client_id=c.id,
            service="Pilates Individuale",
            starts_at=when,
            duration_minutes=55,
            created_via="seed",
        )
        db.add(b)
        created.append({"client": f"{first} {last}", "phone": phone, "starts_at": when.isoformat()})

    # Give Marco a low-balance package (1 lesson left)
    marco = db.query(Client).filter_by(first_name="Marco").first()
    if marco:
        db.add(Package(
            practitioner_id=silvia.id,
            client_id=marco.id,
            total_sessions=10,
            used_sessions=9,
            purchase_date=date.today() - timedelta(days=60),
        ))

    db.commit()
    return {"status": "seeded", "clients": len(_DEMO_CLIENTS), "bookings": len(created)}


@router.post("/send-reminders")
async def trigger_reminders(db: Session = Depends(get_db)):
    """Send 24h reminders. Hit this from a cron (Railway cron, GitHub Actions,
    or any external scheduler) every hour."""
    from backend.logic.reminders import send_reminders
    return await send_reminders(db)


@router.get("/gcal-status")
def gcal_status():
    """Diagnostic: confirm whether Google Calendar integration is wired."""
    from backend.config import settings
    from backend.integrations import google_calendar
    json_set = bool(settings.google_service_account_json)
    cal_set = bool(settings.google_calendar_id)
    enabled = google_calendar.is_enabled()
    return {
        "json_set": json_set,
        "json_length": len(settings.google_service_account_json or ""),
        "calendar_id_set": cal_set,
        "calendar_id_value": settings.google_calendar_id[:50] + "..." if cal_set else None,
        "is_enabled": enabled,
        "disabled_reason": google_calendar._disabled_reason,
    }


@router.post("/gcal-test")
def gcal_test():
    """Try creating a real event right now. Returns event id or error."""
    from datetime import datetime, timedelta
    from backend.timezone import ROME_TZ
    from backend.integrations import google_calendar

    class _B:
        id = "diagnostic-test"
        service = "Diagnostic Test"
        duration_minutes = 30
        created_via = "diagnostic"
        starts_at = datetime.now(ROME_TZ) + timedelta(hours=1)

    class _C:
        full_name = "Diagnostic Test"
        phone = "+39000000000"

    event_id = google_calendar.create_event(_B(), _C())
    return {
        "event_id": event_id,
        "is_enabled": google_calendar.is_enabled(),
        "disabled_reason": google_calendar._disabled_reason,
    }
