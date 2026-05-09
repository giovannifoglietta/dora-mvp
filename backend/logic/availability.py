from datetime import datetime, timedelta, time, date
from typing import Optional
from sqlalchemy.orm import Session
from backend.models.schema import Practitioner, Booking
from backend.timezone import ROME_TZ

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _to_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _localize(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in Europe/Rome."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ROME_TZ)
    return dt.astimezone(ROME_TZ)


def get_working_slots(db: Session, practitioner_id, target_date: date, slot_minutes: int = 55):
    """Return all valid start times (timezone-aware Europe/Rome) for a given
    practitioner on a given date, filtered by working hours and existing bookings."""
    p = db.get(Practitioner, practitioner_id)
    if not p:
        return []

    day_key = DAY_KEYS[target_date.weekday()]
    windows = p.working_hours.get(day_key, [])
    if not windows:
        return []

    break_min = p.break_minutes or 0
    slots = []
    for w in windows:
        start_dt = datetime.combine(target_date, _to_time(w["start"]), tzinfo=ROME_TZ)
        end_dt = datetime.combine(target_date, _to_time(w["end"]), tzinfo=ROME_TZ)
        cursor = start_dt
        while cursor + timedelta(minutes=slot_minutes) <= end_dt:
            slots.append(cursor)
            cursor += timedelta(minutes=slot_minutes + break_min)

    # Filter out slots that conflict with existing bookings
    day_start = datetime.combine(target_date, time.min, tzinfo=ROME_TZ)
    day_end = datetime.combine(target_date, time.max, tzinfo=ROME_TZ)
    existing = (
        db.query(Booking)
        .filter(
            Booking.practitioner_id == practitioner_id,
            Booking.status == "confirmed",
            Booking.starts_at >= day_start,
            Booking.starts_at <= day_end,
        )
        .all()
    )

    def conflicts(slot_start: datetime) -> bool:
        slot_end = slot_start + timedelta(minutes=slot_minutes)
        for b in existing:
            b_start = _localize(b.starts_at)
            b_end = b_start + timedelta(minutes=b.duration_minutes)
            if slot_start < b_end and slot_end > b_start:
                return True
        return False

    return [s for s in slots if not conflicts(s)]


def is_available(db: Session, practitioner_id, when: datetime, duration_minutes: int = 55) -> bool:
    """Check if a specific datetime slot is available."""
    when = _localize(when)
    target_date = when.date()
    slots = get_working_slots(db, practitioner_id, target_date, slot_minutes=duration_minutes)
    return any(s == when for s in slots)


def find_next_available(
    db: Session, practitioner_id, preferred_date: date, preferred_time: Optional[time] = None, max_days: int = 14
):
    """Suggest up to N nearby available slots, starting from preferred_date."""
    suggestions = []
    for offset in range(max_days):
        d = preferred_date + timedelta(days=offset)
        slots = get_working_slots(db, practitioner_id, d)
        if preferred_time and offset == 0:
            slots = [s for s in slots if s.time() >= preferred_time] + [s for s in slots if s.time() < preferred_time]
        suggestions.extend(slots)
        if len(suggestions) >= 5:
            break
    return suggestions[:5]
