from datetime import datetime, date, time, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from backend.models.schema import Practitioner, Booking, Message
from backend.ai import context
from backend.timezone import ROME_TZ
from backend.ai.analyzer import analyze_message
from backend.ai.name_extractor import extract_name
from backend.ai import rules
from backend import responses
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
    if dt.tzinfo is not None:
        dt = dt.astimezone(ROME_TZ)
    return f"{DAYS_IT[dt.weekday()]} {dt.day} {MONTHS_IT[dt.month]} alle {dt.strftime('%H:%M')}"


def _fmt_slots(slots) -> str:
    return ", ".join(s.strftime("%H:%M") for s in slots)


def _parse_dt(date_str: Optional[str], time_str: Optional[str]) -> Optional[datetime]:
    if not date_str or not time_str:
        return None
    try:
        d = date.fromisoformat(date_str)
        t = time.fromisoformat(time_str if len(time_str) == 5 else time_str + ":00")
        return datetime.combine(d, t, tzinfo=ROME_TZ)
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
        return responses.NO_PRACTITIONER

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
    # Onboarding: do we know the client's first name yet?
    # (Last name is optional — Silvia can fill it in from the dashboard.)
    if not client.first_name:
        if is_top_level:
            _log_message(db, client.id, "inbound", text, intent="onboarding_name")
        return await _handle_name_capture(db, client, phone, text, state)

    # If a booking confirmation is pending, intercept yes/no answers before LLM classify
    if state.get("pending_intent") == "confirm_book":
        proposed = state.get("proposed_booking")
        if _is_confirmation(text) and proposed:
            if is_top_level:
                _log_message(db, client.id, "inbound", text, intent="confirm")
            return await _execute_confirmed_booking(db, silvia, client, phone, proposed)
        if _is_negation(text):
            if is_top_level:
                _log_message(db, client.id, "inbound", text, intent="negate")
            context.update(phone, pending_intent=None, entities=None, proposed_booking=None)
            return responses.NEGATION_OK
        # Fall through — they probably said something else (e.g. another time)

    # Quick keyword shortcuts before LLM classification
    short = text.strip().lower()
    if short in ("aiuto", "help", "info", "che puoi fare", "cosa puoi fare"):
        return responses.HELP

    # Try the deterministic fast path first; only call the LLM if rules don't match
    analysis = rules.try_parse(text)
    parsed_by = "rules" if analysis else "llm"
    if analysis is None:
        analysis = await analyze_message(text)

    intent = analysis.get("intent", "off_topic")
    confidence = analysis.get("confidence", 0.0)
    entities = {k: v for k, v in analysis.items() if k in ("date", "time", "service")}

    # Merge entities with pending state (multi-turn)
    if state.get("pending_intent") and not confidence > 0.8:
        intent = state["pending_intent"]
    merged = {**state.get("entities", {}), **entities}

    if is_top_level:
        log_entities = dict(entities) if entities else {}
        log_entities["_parsed_by"] = parsed_by
        _log_message(db, client.id, "inbound", text, intent=intent, entities=log_entities, confidence=confidence)

    if intent == "greeting":
        # Preserve onboarding-completion flags; only clear in-flight intent state
        context.update(phone, pending_intent=None, entities=None, awaiting_name=None, original_text=None)
        return responses.GREETING

    if intent == "book":
        return await _handle_book(db, silvia, client, phone, merged)

    if intent == "cancel":
        return await _handle_cancel(db, client, phone, merged)

    if intent == "reschedule":
        return await _handle_reschedule(db, silvia, client, phone, merged)

    if intent == "query":
        nb = get_next_booking(db, client.id)
        if nb:
            return responses.next_appointment(_fmt_dt(nb.starts_at))
        return responses.NO_NEXT_APPOINTMENT

    if intent == "package_info":
        pkg = active_package(db, client.id)
        if not pkg:
            return responses.no_active_package(client.first_name)
        remaining = sessions_remaining(pkg)
        expiry = f" (scade il {pkg.expiry_date.strftime('%d/%m/%Y')})" if pkg.expiry_date else ""
        return responses.package_balance(remaining, pkg.total_sessions, expiry)

    return _fallback_reply(client, text, confidence)


def _fallback_reply(client, text: str, confidence: float) -> str:
    """Generate a contextual fallback when intent is unclear or off-topic."""
    short = text.strip().lower()
    if any(w in short for w in ["grazie", "ok", "perfetto", "va bene"]):
        return responses.thanks_back(client.first_name)
    if any(w in short for w in ["aiuto", "help", "info"]):
        return responses.HELP
    if "?" in text:
        return responses.FALLBACK_QUESTION
    return responses.FALLBACK_GENERIC


_SKIP_PATTERNS = ("non voglio", "preferisco di no", "no grazie", "lascia stare", "skip", "salta")


def _is_skip(text: str) -> bool:
    t = text.lower().strip()
    return any(p in t for p in _SKIP_PATTERNS)


_CONFIRM_PATTERNS = ("sì", "si", "ok", "okay", "yes", "confermo", "va bene", "perfetto",
                     "certo", "esatto", "confermato", "d'accordo", "vai")
_NEGATE_PATTERNS = ("no", "annulla", "lascia stare", "non voglio", "cambia idea", "non più")


def _is_confirmation(text: str) -> bool:
    t = text.lower().strip().rstrip("!.?,")
    if t in _CONFIRM_PATTERNS:
        return True
    # Allow short responses like "sì grazie", "ok confermo"
    return any(t.startswith(p + " ") or t.startswith(p + ",") or t == p for p in _CONFIRM_PATTERNS)


def _is_negation(text: str) -> bool:
    t = text.lower().strip().rstrip("!.?,")
    if t in _NEGATE_PATTERNS:
        return True
    return any(t.startswith(p + " ") or t.startswith(p + ",") for p in _NEGATE_PATTERNS)


async def _handle_name_capture(db: Session, client, phone, text, state) -> str:
    """Onboarding: collect first name. Last name is optional and captured if user
    happens to provide it ("Marco Rossi") but never explicitly requested."""
    awaiting = state.get("awaiting_name")
    first, last = await extract_name(text)

    if first:
        set_client_name(db, client, first, last)
        # Replay the message that contains the most info: prefer current text
        # if it's longer than the saved one (e.g. "sono Marco, vorrei giovedì alle 10")
        original_text = state.get("original_text") or text
        if len(text) > len(original_text):
            original_text = text
        context.update(phone, awaiting_name=None, original_text=None)
        context.update(phone, _replaying=True)
        try:
            return responses.name_acknowledged(first) + " " + await handle_message(db, phone, original_text)
        finally:
            context.update(phone, _replaying=None)

    if awaiting:
        return responses.NAME_RETRY
    context.update(phone, awaiting_name=True, original_text=text)
    return responses.NAME_PROMPT


async def _handle_book(db: Session, practitioner, client, phone, entities) -> str:
    when = _parse_dt(entities.get("date"), entities.get("time"))
    if not when:
        # Need more info — store state
        context.update(phone, pending_intent="book", entities=entities)
        if entities.get("date") and not entities.get("time"):
            d = date.fromisoformat(entities["date"])
            slots = find_next_available(db, practitioner.id, d)
            if not slots:
                return responses.day_no_availability()
            same_day = [s for s in slots if s.date() == d]
            if same_day:
                return responses.day_options(DAYS_IT[d.weekday()], _fmt_slots(same_day[:5]))
            return responses.day_full(DAYS_IT[d.weekday()], (_fmt_dt(s) for s in slots[:3]))
        return responses.ASK_WHEN

    if not is_available(db, practitioner.id, when):
        suggestions = find_next_available(db, practitioner.id, when.date(), when.time())
        if suggestions:
            return responses.slot_taken_with_alternatives(
                _fmt_dt(when), (_fmt_dt(s) for s in suggestions[:3])
            )
        return responses.slot_unavailable(_fmt_dt(when))

    # Don't book yet — propose and wait for confirmation
    service = entities.get("service") or "Pilates Individuale"
    context.update(
        phone,
        pending_intent="confirm_book",
        proposed_booking={
            "starts_at": when.isoformat(),
            "service": service,
        },
        entities=None,
    )
    return responses.propose_booking(_fmt_dt(when), service)


async def _execute_confirmed_booking(db: Session, practitioner, client, phone, proposed: dict) -> str:
    when = datetime.fromisoformat(proposed["starts_at"])
    service = proposed.get("service", "Pilates Individuale")
    # Re-check availability — someone else may have grabbed the slot in the meantime
    if not is_available(db, practitioner.id, when):
        context.update(phone, pending_intent=None, proposed_booking=None)
        suggestions = find_next_available(db, practitioner.id, when.date(), when.time())
        return responses.slot_taken_meanwhile(_fmt_dt(s) for s in suggestions[:3])

    try:
        booking = create_booking(db, practitioner.id, client.id, when, service=service)
    except BookingError as e:
        return responses.booking_error(str(e))

    context.update(phone, pending_intent=None, entities=None, proposed_booking=None,
                   awaiting_name=None, original_text=None)
    confirmation = responses.booking_confirmed(client.first_name, _fmt_dt(booking.starts_at))
    pkg = active_package(db, client.id)
    if pkg:
        remaining = sessions_remaining(pkg)
        if remaining == 0:
            confirmation += responses.PACKAGE_LAST_LESSON_ALERT
        elif remaining <= 2:
            confirmation += responses.package_low_balance_alert(remaining)
    return confirmation


async def _handle_cancel(db: Session, client, phone, entities) -> str:
    upcoming = get_upcoming_bookings(db, client.id)
    if not upcoming:
        return responses.NO_BOOKINGS_TO_CANCEL

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
        listing = "; ".join(_fmt_dt(b.starts_at) for b in upcoming[:3])
        return responses.which_to_cancel(listing)

    cancel_booking(db, target.id)
    context.clear(phone)
    return responses.cancellation_confirmed(_fmt_dt(target.starts_at))


async def _handle_reschedule(db: Session, practitioner, client, phone, entities) -> str:
    upcoming = get_upcoming_bookings(db, client.id)
    if not upcoming:
        return responses.NO_BOOKINGS_TO_RESCHEDULE

    new_when = _parse_dt(entities.get("date"), entities.get("time"))
    if not new_when:
        context.update(phone, pending_intent="reschedule", entities=entities)
        next_b = upcoming[0]
        return responses.reschedule_prompt(_fmt_dt(next_b.starts_at))

    target = upcoming[0]
    try:
        reschedule_booking(db, target.id, new_when)
        context.update(phone, pending_intent=None, entities=None, awaiting_name=None, original_text=None)
        return responses.reschedule_confirmed(_fmt_dt(new_when))
    except BookingError:
        suggestions = find_next_available(db, practitioner.id, new_when.date(), new_when.time())
        return responses.slot_taken_with_alternatives(
            _fmt_dt(new_when), (_fmt_dt(s) for s in suggestions[:3])
        )
