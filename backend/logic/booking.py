from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from backend.models.schema import Booking, Client, Package, Practitioner
from backend.logic.availability import is_available
from backend.logic.packages import active_package
from backend.timezone import ROME_TZ


class BookingError(Exception):
    pass


def get_or_create_client(db: Session, practitioner_id, phone: str, name: Optional[str] = None) -> Client:
    client = db.query(Client).filter_by(phone=phone).first()
    if client:
        client.last_seen = datetime.now(ROME_TZ)
        db.commit()
        return client
    client = Client(practitioner_id=practitioner_id, phone=phone, name=name or phone)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def set_client_name(db: Session, client: Client, first_name: str, last_name: Optional[str] = None) -> Client:
    client.first_name = first_name
    if last_name:
        client.last_name = last_name
    client.name = f"{first_name} {last_name}".strip() if last_name else first_name
    db.commit()
    db.refresh(client)
    return client


def create_booking(
    db: Session,
    practitioner_id,
    client_id,
    starts_at: datetime,
    service: str = "Pilates Individuale",
    duration_minutes: int = 55,
    created_via: str = "whatsapp",
) -> Booking:
    if not is_available(db, practitioner_id, starts_at, duration_minutes):
        raise BookingError(f"Slot {starts_at} not available")

    booking = Booking(
        practitioner_id=practitioner_id,
        client_id=client_id,
        service=service,
        starts_at=starts_at,
        duration_minutes=duration_minutes,
        created_via=created_via,
    )
    db.add(booking)

    pkg = active_package(db, client_id)
    if pkg:
        pkg.used_sessions += 1

    db.commit()
    db.refresh(booking)
    return booking


def cancel_booking(db: Session, booking_id) -> Booking:
    booking = db.get(Booking, booking_id)
    if not booking:
        raise BookingError(f"Booking {booking_id} not found")
    if booking.status == "cancelled":
        return booking

    booking.status = "cancelled"
    booking.cancelled_at = datetime.now(ROME_TZ)

    pkg = active_package(db, booking.client_id)
    if pkg and pkg.used_sessions > 0:
        pkg.used_sessions -= 1

    db.commit()
    db.refresh(booking)
    return booking


def reschedule_booking(db: Session, booking_id, new_starts_at: datetime) -> Booking:
    booking = db.get(Booking, booking_id)
    if not booking:
        raise BookingError(f"Booking {booking_id} not found")
    if not is_available(db, booking.practitioner_id, new_starts_at, booking.duration_minutes):
        raise BookingError(f"Slot {new_starts_at} not available")

    booking.starts_at = new_starts_at
    db.commit()
    db.refresh(booking)
    return booking


def get_upcoming_bookings(db: Session, client_id, limit: int = 5):
    return (
        db.query(Booking)
        .filter(
            Booking.client_id == client_id,
            Booking.status == "confirmed",
            Booking.starts_at >= datetime.now(ROME_TZ),
        )
        .order_by(Booking.starts_at.asc())
        .limit(limit)
        .all()
    )


def get_next_booking(db: Session, client_id) -> Optional[Booking]:
    bookings = get_upcoming_bookings(db, client_id, limit=1)
    return bookings[0] if bookings else None
