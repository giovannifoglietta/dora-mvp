from datetime import datetime, date, time, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from backend.models.schema import Practitioner, Booking
from backend.ai import context
from backend.ai.classifier import classify_intent
from backend.ai.extractor import extract_entities
from backend.logic.availability import is_available, find_next_available
from backend.logic.booking import (
    get_or_create_client,
    create_booking,
    cancel_booking,
    reschedule_booking,
    get_upcoming_bookings,
    get_next_booking,
    BookingError,
)

DAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MONTHS_IT = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
             "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _fmt_dt(dt: datetime) -> str:
    return f"{DAYS_IT[dt.weekday()]} {dt.day} {MONTHS_IT[dt.month]} alle {dt.strftime('%H:%M')}"


def _fmt_slots(slots) -> str:
    return ", ".join(s.strftime("%H:%M") for s in slots)


def _parse_dt(date_str: Optional[str], time_str: Optional[str]) -> Optional[datetime]:
    if not date_str or not time_str:
        return None
    try:
        d = date.fromisoformat(date_str)
        t = time.fromisoformat(time_str if len(time_str) == 5 else time_str + ":00")
        return datetime.combine(d, t)
    except (ValueError, TypeError):
        return None


async def handle_message(db: Session, phone: str, text: str) -> str:
    """Process an incoming message and return the reply text."""
    silvia = db.query(Practitioner).first()
    if not silvia:
        return "Configurazione mancante. Contatta Silvia."

    client = get_or_create_client(db, silvia.id, phone)
    state = context.get(phone)

    intent_result = await classify_intent(text)
    intent = intent_result.get("intent", "off_topic")

    needs_entities = intent in ("book", "reschedule", "cancel") or state.get("pending_intent")
    entities = await extract_entities(text) if needs_entities else {}

    # Merge entities with pending state (multi-turn)
    if state.get("pending_intent") and not intent_result.get("confidence", 0) > 0.8:
        intent = state["pending_intent"]
    merged = {**state.get("entities", {}), **entities}

    if intent == "greeting":
        context.clear(phone)
        return f"Ciao! Sono Dora, l'assistente di Silvia. Vuoi prenotare una lezione?"

    if intent == "book":
        return await _handle_book(db, silvia, client, phone, merged)

    if intent == "cancel":
        return await _handle_cancel(db, client, phone, merged)

    if intent == "reschedule":
        return await _handle_reschedule(db, silvia, client, phone, merged)

    if intent == "query":
        nb = get_next_booking(db, client.id)
        if nb:
            return f"La tua prossima lezione è {_fmt_dt(nb.starts_at.replace(tzinfo=None))}."
        return "Non hai lezioni in programma. Vuoi prenotarne una?"

    if intent == "package_info":
        return "La gestione pacchetti arriva presto. Per ora chiedi a Silvia."

    return "Non sono sicura di aver capito. Vuoi prenotare, spostare o cancellare una lezione?"


async def _handle_book(db: Session, practitioner, client, phone, entities) -> str:
    when = _parse_dt(entities.get("date"), entities.get("time"))
    if not when:
        # Need more info — store state
        context.update(phone, pending_intent="book", entities=entities)
        if entities.get("date") and not entities.get("time"):
            d = date.fromisoformat(entities["date"])
            slots = find_next_available(db, practitioner.id, d)
            if not slots:
                return f"Quel giorno non ho disponibilità. Vuoi un altro giorno?"
            same_day = [s for s in slots if s.date() == d]
            if same_day:
                return f"Per {DAYS_IT[d.weekday()]} ho disponibile: {_fmt_slots(same_day[:5])}. Quale preferisci?"
            return f"{DAYS_IT[d.weekday()]} è pieno. Ho liberi: " + ", ".join(_fmt_dt(s) for s in slots[:3])
        return "Per quando vorresti prenotare? (es. 'giovedì alle 10')"

    if not is_available(db, practitioner.id, when):
        suggestions = find_next_available(db, practitioner.id, when.date(), when.time())
        if suggestions:
            return (
                f"Mi spiace, {_fmt_dt(when)} è già occupato. "
                f"Ho disponibile: " + ", ".join(_fmt_dt(s) for s in suggestions[:3])
            )
        return f"Mi spiace, {_fmt_dt(when)} non è disponibile."

    try:
        booking = create_booking(
            db, practitioner.id, client.id, when,
            service=entities.get("service") or "Pilates Individuale",
        )
        context.clear(phone)
        return f"Perfetto! Ti ho prenotata per {_fmt_dt(booking.starts_at.replace(tzinfo=None))}. A presto!"
    except BookingError as e:
        return f"Errore: {e}"


async def _handle_cancel(db: Session, client, phone, entities) -> str:
    upcoming = get_upcoming_bookings(db, client.id)
    if not upcoming:
        return "Non hai lezioni da cancellare."

    target = None
    if entities.get("date"):
        target_date = date.fromisoformat(entities["date"])
        for b in upcoming:
            if b.starts_at.date() == target_date:
                target = b
                break
    elif len(upcoming) == 1:
        target = upcoming[0]

    if not target:
        listing = "; ".join(_fmt_dt(b.starts_at.replace(tzinfo=None)) for b in upcoming[:3])
        return f"Quale lezione vuoi cancellare? Hai: {listing}"

    cancel_booking(db, target.id)
    context.clear(phone)
    return f"Ho cancellato la lezione di {_fmt_dt(target.starts_at.replace(tzinfo=None))}. Vuoi prenotare un altro giorno?"


async def _handle_reschedule(db: Session, practitioner, client, phone, entities) -> str:
    upcoming = get_upcoming_bookings(db, client.id)
    if not upcoming:
        return "Non hai lezioni da spostare. Vuoi prenotarne una?"

    new_when = _parse_dt(entities.get("date"), entities.get("time"))
    if not new_when:
        context.update(phone, pending_intent="reschedule", entities=entities)
        next_b = upcoming[0]
        return (
            f"Hai la lezione {_fmt_dt(next_b.starts_at.replace(tzinfo=None))}. "
            f"Quando vorresti spostarla?"
        )

    target = upcoming[0]
    try:
        reschedule_booking(db, target.id, new_when)
        context.clear(phone)
        return f"Fatto! Lezione spostata a {_fmt_dt(new_when)}."
    except BookingError:
        suggestions = find_next_available(db, practitioner.id, new_when.date(), new_when.time())
        return (
            f"{_fmt_dt(new_when)} non è disponibile. "
            f"Ho liberi: " + ", ".join(_fmt_dt(s) for s in suggestions[:3])
        )
