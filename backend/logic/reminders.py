"""24-hour booking reminders.

Strategy: hourly job picks up bookings starting in 23-25h and sends a reminder
to each client. Marks `reminder_sent=True` so we don't repeat.
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.models.schema import Booking, Client
from backend.whatsapp import send_message
from backend.timezone import ROME_TZ

DAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def _format_reminder(client: Client, booking: Booking) -> str:
    dt = booking.starts_at.astimezone(ROME_TZ)
    day_name = DAYS_IT[dt.weekday()]
    time_str = dt.strftime("%H:%M")
    name = client.first_name or "ciao"
    service = booking.service or "Pilates"
    return (
        f"Ciao {name}! Ti ricordo la tua lezione di {service} "
        f"domani ({day_name}) alle {time_str} con Silvia. "
        f"Se devi spostare o cancellare, scrivimi qui."
    )


async def send_reminders(db: Session) -> dict:
    """Find bookings 23-25h from now, send reminders, mark sent.
    Returns {sent: N, skipped: N, errors: N}."""
    now = datetime.now(ROME_TZ)
    window_start = now + timedelta(hours=23)
    window_end = now + timedelta(hours=25)

    bookings = (
        db.query(Booking)
        .filter(
            Booking.status == "confirmed",
            Booking.reminder_sent == False,  # noqa: E712
            Booking.starts_at >= window_start,
            Booking.starts_at <= window_end,
        )
        .all()
    )

    sent = 0
    errors = 0
    skipped = 0
    for booking in bookings:
        client = db.get(Client, booking.client_id)
        if not client or not client.phone:
            skipped += 1
            continue
        text = _format_reminder(client, booking)
        try:
            ok = await send_message(client.phone, text)
        except Exception as e:
            print(f"[reminders] failed for booking {booking.id}: {e}")
            errors += 1
            continue
        # Treat any non-False truthy result as success (stub returns dict with 'status')
        if ok is False:
            errors += 1
            continue
        booking.reminder_sent = True
        sent += 1

    db.commit()
    return {"sent": sent, "skipped": skipped, "errors": errors, "candidates": len(bookings)}
