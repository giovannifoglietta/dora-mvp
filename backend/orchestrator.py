from datetime import datetime, date, time, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from backend.models.schema import Practitioner, Booking, Message
from backend.ai import context
from backend.ai.classifier import classify_intent
from backend.ai.extractor import extract_entities
from backend.ai.name_extractor import extract_name
from backend.logic.availability import is_available, find_next_available
from backend.logic.packages import active_package, sessions_remaining
from backend.logic.booking import (
    get_or_create_client,
    set_client_name,
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


def _log_message(
    db: Session,
    client_id,
    direction: str,
    body: str,
    intent: Optional[str] = None,
    entities: Optional[dict] = None,
    confidence: Optional[float] = None,
):
    msg = Message(
        client_id=client_id,
        direction=direction,
        body=body,
        intent=intent,
        entities=entities,
        confidence=confidence,
    )
    db.add(msg)
    db.commit()


def _normalize_phone(phone: str) -> str:
    """Strip whatsapp/sip prefixes and non-digits except leading +."""
    p = phone.strip()
    if p.startswith("whatsapp:"):
        p = p[len("whatsapp:"):]
    return p


async def handle_message(db: Session, phone: str, text: str, profile_name: Optional[str] = None) -> str:
    """Process an incoming message and return the reply text.

    profile_name: name from WhatsApp profile (passed by 360dialog webhook).
    If provided and we don't have one yet, we use it directly.
    """
    silvia = db.query(Practitioner).first()
    if not silvia:
        return "Configurazione mancante. Contatta Silvia."

    # If the message comes from the practitioner herself, treat it as an instruction
    phone_norm = _normalize_phone(phone)
    pract_phones = {_normalize_phone(silvia.phone or ""), _normalize_phone(silvia.whatsapp_number or "")}
    pract_phones.discard("")
    if phone_norm in pract_phones:
        from backend.ai.practitioner_nlp import execute_instruction
        result = await execute_instruction(db, silvia, text)
        return result.get("summary", "Ok.")

    client = get_or_create_client(db, silvia.id, phone, profile_name)

    # Skip the recursive call's logging (recursive calls happen during onboarding flows
    # when we replay the original message after capturing a name)
    state = context.get(phone)
    is_top_level = not state.get("_replaying")

    reply = await _route(db, silvia, client, phone, text, state, is_top_level)

    if is_top_level:
        _log_message(db, client.id, "outbound", reply)
    return reply


async def _route(db: Session, silvia, client, phone: str, text: str, state: dict, is_top_level: bool) -> str:
    # Onboarding: do we know the client's name yet?
    if not client.first_name:
        if is_top_level:
            _log_message(db, client.id, "inbound", text, intent="onboarding_name")
        return await _handle_name_capture(db, client, phone, text, state)
    if not client.last_name and not state.get("skipped_last_name"):
        if is_top_level:
            _log_message(db, client.id, "inbound", text, intent="onboarding_lastname")
        return await _handle_lastname_capture(db, client, phone, text, state)

    # Quick keyword shortcuts before LLM classification
    short = text.strip().lower()
    if short in ("aiuto", "help", "info", "che puoi fare", "cosa puoi fare"):
        return ("Posso aiutarti a:\n"
                "• Prenotare una lezione (es. 'giovedì alle 10')\n"
                "• Spostare o cancellare una lezione\n"
                "• Dirti quando è il tuo prossimo appuntamento\n"
                "• Vedere quante lezioni hai nel pacchetto\n"
                "Cosa vuoi fare?")

    intent_result = await classify_intent(text)
    intent = intent_result.get("intent", "off_topic")
    confidence = intent_result.get("confidence", 0.0)

    needs_entities = intent in ("book", "reschedule", "cancel") or state.get("pending_intent")
    entities = await extract_entities(text) if needs_entities else {}

    # Merge entities with pending state (multi-turn)
    if state.get("pending_intent") and not confidence > 0.8:
        intent = state["pending_intent"]
    merged = {**state.get("entities", {}), **entities}

    if is_top_level:
        _log_message(db, client.id, "inbound", text, intent=intent, entities=entities or None, confidence=confidence)

    if intent == "greeting":
        # Preserve onboarding-completion flags; only clear in-flight intent state
        context.update(phone, pending_intent=None, entities=None, awaiting_name=None, original_text=None)
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
        pkg = active_package(db, client.id)
        if not pkg:
            return f"{client.first_name}, non risulta nessun pacchetto attivo. Vuoi parlarne con Silvia?"
        remaining = sessions_remaining(pkg)
        expiry = f" (scade il {pkg.expiry_date.strftime('%d/%m/%Y')})" if pkg.expiry_date else ""
        return f"Hai {remaining} lezioni rimanenti su {pkg.total_sessions}{expiry}."

    return _fallback_reply(client, text, confidence)


def _fallback_reply(client, text: str, confidence: float) -> str:
    """Generate a contextual fallback when intent is unclear or off-topic."""
    short = text.strip().lower()
    name = client.first_name or ""
    # Common patterns we can heuristically nudge
    if any(w in short for w in ["grazie", "ok", "perfetto", "va bene"]):
        return f"Di nulla{', ' + name if name else ''}! Se ti serve altro, scrivimi pure."
    if any(w in short for w in ["aiuto", "help", "info"]):
        return ("Posso aiutarti a:\n"
                "• Prenotare una lezione (es. 'giovedì alle 10')\n"
                "• Spostare o cancellare una lezione\n"
                "• Dirti quando è il tuo prossimo appuntamento\n"
                "Cosa vuoi fare?")
    if "?" in text:
        return ("Su questo non saprei risponderti. Posso aiutarti con prenotazioni, "
                "spostamenti o cancellazioni. Vuoi fare una di queste cose?")
    return ("Non sono sicura di aver capito. "
            "Vuoi prenotare, spostare o cancellare una lezione?")


_SKIP_PATTERNS = ("non voglio", "preferisco di no", "no grazie", "lascia stare", "skip", "salta")


def _is_skip(text: str) -> bool:
    t = text.lower().strip()
    return any(p in t for p in _SKIP_PATTERNS)


async def _handle_name_capture(db: Session, client, phone, text, state) -> str:
    """First step of onboarding: collect first (and optionally last) name."""
    awaiting = state.get("awaiting_name")
    first, last = await extract_name(text)

    if first:
        set_client_name(db, client, first, last)
        original_text = state.get("original_text", text)
        context.update(phone, awaiting_name=None, original_text=None)

        if last:
            # Got both — greet and replay original request
            greeting = f"Piacere di conoscerti, {first}! "
            context.update(phone, _replaying=True)
            try:
                return greeting + await handle_message(db, phone, original_text)
            finally:
                context.update(phone, _replaying=None)
        # Only first name — ask for last name next
        context.update(phone, original_text=original_text)
        return f"Piacere, {first}! Mi dici anche il cognome?"

    if awaiting:
        return "Non ho capito il tuo nome. Come ti chiami?"

    context.update(phone, awaiting_name=True, original_text=text)
    return "Ciao! Sono Dora, l'assistente di Silvia. Come posso chiamarti? (nome e cognome)"


async def _handle_lastname_capture(db: Session, client, phone, text, state) -> str:
    """Second step of onboarding: optional last name."""
    if _is_skip(text):
        context.update(phone, skipped_last_name=True)
        original_text = state.get("original_text")
        if original_text and original_text != text:
            context.update(phone, _replaying=True)
            try:
                return await handle_message(db, phone, original_text)
            finally:
                context.update(phone, _replaying=None)
        return f"Va bene, {client.first_name}. Vuoi prenotare una lezione?"

    first, last = await extract_name(text)
    # If user wrote a single word as their last name, use it
    if not last and first:
        last = first
        first = client.first_name
    if last:
        set_client_name(db, client, first or client.first_name, last)
        original_text = state.get("original_text")
        context.update(phone, original_text=None)
        if original_text and original_text != text:
            context.update(phone, _replaying=True)
            try:
                return f"Grazie {client.first_name}! " + await handle_message(db, phone, original_text)
            finally:
                context.update(phone, _replaying=None)
        return f"Grazie {client.first_name} {last}! Vuoi prenotare una lezione?"

    return "Mi dici il cognome? (oppure scrivi 'salta' se preferisci)"


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
        context.update(phone, pending_intent=None, entities=None, awaiting_name=None, original_text=None)
        confirmation = f"Perfetto {client.first_name}! Ti ho prenotata per {_fmt_dt(booking.starts_at.replace(tzinfo=None))}. A presto!"
        # Low-balance package alert
        pkg = active_package(db, client.id)
        if pkg:
            remaining = sessions_remaining(pkg)
            if remaining == 0:
                confirmation += f"\n\n⚠️ Era l'ultima lezione del tuo pacchetto. Parla con Silvia per rinnovarlo."
            elif remaining <= 2:
                confirmation += f"\n\nP.S. Ti restano {remaining} lezioni del pacchetto."
        return confirmation
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
        context.update(phone, pending_intent=None, entities=None, awaiting_name=None, original_text=None)
        return f"Fatto! Lezione spostata a {_fmt_dt(new_when)}."
    except BookingError:
        suggestions = find_next_available(db, practitioner.id, new_when.date(), new_when.time())
        return (
            f"{_fmt_dt(new_when)} non è disponibile. "
            f"Ho liberi: " + ", ".join(_fmt_dt(s) for s in suggestions[:3])
        )
