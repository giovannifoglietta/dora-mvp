# Dora MVP — Code Audit & Fix Instructions

> **Purpose:** This document describes every bug, issue, and missing feature in the Dora MVP codebase. Each section includes the exact files, line numbers, what's wrong, and what the fix should look like. Work through them in order — the numbering reflects priority.

---

## Project Context

Dora is a WhatsApp-native AI booking assistant for Silvia, a Pilates instructor in Italy. Clients message Dora on WhatsApp to book, reschedule, or cancel lessons. The backend is FastAPI + SQLAlchemy (sync) + PostgreSQL (Supabase) + Anthropic Claude Haiku for NLU.

The codebase lives in the repo root. Key paths:

```
backend/
├── main.py              # FastAPI app entry point
├── config.py            # Settings from .env
├── webhooks.py          # WhatsApp webhook endpoints
├── whatsapp.py          # WhatsApp API client (currently a stub)
├── orchestrator.py      # Message handling brain — routes intents to actions
├── admin.py             # Debug/test API endpoints
├── practitioner.py      # Practitioner dashboard API
├── ai/
│   ├── classifier.py    # Intent classification (Haiku)
│   ├── extractor.py     # Entity extraction (Haiku)
│   ├── name_extractor.py # Name extraction for onboarding (Haiku)
│   ├── context.py       # In-memory conversation state
│   ├── prompts.py       # LLM system prompts
│   └── practitioner_nlp.py # NL instructions from practitioner
├── logic/
│   ├── availability.py  # Slot availability engine
│   └── booking.py       # Booking CRUD + package tracking
├── models/
│   └── schema.py        # SQLAlchemy models
├── db/
│   ├── database.py      # DB engine + session
│   └── migrations/      # SQL migration files
├── static/
│   ├── index.html       # Test console UI
│   └── practitioner.html # Practitioner dashboard UI
└── tests/
    └── __init__.py      # (empty — no tests yet)
```

---

## CRITICAL FIXES (do these first)

---

### FIX 1: AI calls are synchronous but wrapped in async — blocks the event loop

**Files:** `backend/ai/classifier.py`, `backend/ai/extractor.py`, `backend/ai/name_extractor.py`

**Problem:** All three AI modules create a sync `anthropic.Anthropic` client and call `client.messages.create()` (the synchronous method). However, the functions are declared `async def`. This is dangerous: the sync HTTP call blocks the entire asyncio event loop. While one user's message is being processed by Haiku (~0.5-1s), NO other request can be served — the server freezes.

**What to change in `backend/ai/classifier.py`:**

Line 6 — change:
```python
client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
```
to:
```python
client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
```

Line 11 — change:
```python
    response = client.messages.create(
```
to:
```python
    response = await client.messages.create(
```

**What to change in `backend/ai/extractor.py`:**

Line 6 — same change: `anthropic.Anthropic` → `anthropic.AsyncAnthropic`

Line 12 — add `await` before `client.messages.create(`

**What to change in `backend/ai/name_extractor.py`:**

Line 7 — same change: `anthropic.Anthropic` → `anthropic.AsyncAnthropic`

Line 35 — add `await` before `client.messages.create(`

**What to change in `backend/ai/practitioner_nlp.py`:**

Line 18 — change:
```python
client_ai = anthropic.Anthropic(api_key=settings.anthropic_api_key)
```
to:
```python
client_ai = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
```

Line 43 — add `await` before `client_ai.messages.create(`

**Verification:** After fixing, grep the entire `backend/` directory for `anthropic.Anthropic(` — there should be zero matches. Every instance should be `anthropic.AsyncAnthropic(`. Also grep for `client.messages.create(` and `client_ai.messages.create(` — every instance should be preceded by `await`.

---

### FIX 2: No timezone handling — all datetimes are naive, will be off by 1-2 hours

**Problem:** The entire codebase uses `datetime.utcnow()` and `datetime.combine(d, t)` without timezone info. The database schema uses `TIMESTAMPTZ` (PostgreSQL stores as UTC). Italy is UTC+1 in winter and UTC+2 in summer (DST). This means:
- When a client books "10:00", the system stores a naive `10:00` which PostgreSQL interprets as UTC — so the booking appears at 11:00 or 12:00 Italian time.
- Availability comparisons (`Booking.starts_at >= datetime.utcnow()`) compare UTC times against naive times, potentially showing already-past slots as available or hiding future slots.

The `Practitioner` model already has a `timezone` field defaulting to `"Europe/Rome"` but it's never used anywhere.

**Files to change:**

**`backend/logic/booking.py`** — lines 25, 84, 124:

Add at top of file:
```python
from zoneinfo import ZoneInfo

ROME_TZ = ZoneInfo("Europe/Rome")
```

Change every `datetime.utcnow()` to `datetime.now(ROME_TZ)`. There are 3 occurrences:
- Line 25: `client.last_seen = datetime.utcnow()` → `client.last_seen = datetime.now(ROME_TZ)`
- Line 84: `booking.cancelled_at = datetime.utcnow()` → `booking.cancelled_at = datetime.now(ROME_TZ)`
- Line 124 (in `get_upcoming_bookings`): `Booking.starts_at >= datetime.utcnow()` → `Booking.starts_at >= datetime.now(ROME_TZ)`

**`backend/logic/availability.py`** — lines 37-38:

Add at top of file:
```python
from zoneinfo import ZoneInfo

ROME_TZ = ZoneInfo("Europe/Rome")
```

Lines 37-38 — change:
```python
    day_start = datetime.combine(target_date, time.min)
    day_end = datetime.combine(target_date, time.max)
```
to:
```python
    day_start = datetime.combine(target_date, time.min, tzinfo=ROME_TZ)
    day_end = datetime.combine(target_date, time.max, tzinfo=ROME_TZ)
```

Also line 29-30, the slot generation — make slots timezone-aware:
```python
        start_dt = datetime.combine(target_date, _to_time(w["start"]), tzinfo=ROME_TZ)
        end_dt = datetime.combine(target_date, _to_time(w["end"]), tzinfo=ROME_TZ)
```

And line 54 where booking times are compared — strip or add tz for consistent comparison:
```python
            b_start = b.starts_at.astimezone(ROME_TZ).replace(tzinfo=None) if b.starts_at.tzinfo else b.starts_at
```
Actually, the cleanest fix is to make all generated slots tz-aware and compare tz-aware to tz-aware. Change line 54 to:
```python
            b_start = b.starts_at.astimezone(ROME_TZ) if b.starts_at.tzinfo else ROME_TZ.localize(b.starts_at)
```

**`backend/orchestrator.py`** — line 92:

The `_fmt_dt` call strips tzinfo with `.replace(tzinfo=None)` — this is a display workaround. Instead, ensure the formatting function handles timezone-aware datetimes:
```python
def _fmt_dt(dt: datetime) -> str:
    if dt.tzinfo:
        dt = dt.astimezone(ZoneInfo("Europe/Rome"))
    return f"{DAYS_IT[dt.weekday()]} {dt.day} {MONTHS_IT[dt.month]} alle {dt.strftime('%H:%M')}"
```
Then remove all `.replace(tzinfo=None)` calls throughout the file (lines 92, 172, 190, 210, 216, 229).

Add `from zoneinfo import ZoneInfo` to the imports.

**`backend/practitioner.py`** — line 139:
```python
    now = datetime.utcnow()
```
Change to:
```python
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Europe/Rome"))
```

**`backend/ai/practitioner_nlp.py`** — line 124:
```python
            Booking.starts_at >= datetime.utcnow(),
```
Change to:
```python
            Booking.starts_at >= datetime.now(ZoneInfo("Europe/Rome")),
```
Add `from zoneinfo import ZoneInfo` to imports.

**Verification:** Grep the entire `backend/` directory for `datetime.utcnow()` — there should be zero matches after fixing. Also grep for `datetime.combine(` and verify every call includes `tzinfo=ROME_TZ` where appropriate.

---

### FIX 3: No message logging — conversations are lost

**Files:** `backend/webhooks.py`, `backend/models/schema.py` (the `Message` model exists but is unused)

**Problem:** The `Message` model is defined in the schema and the DB table exists, but nothing ever writes to it. Every conversation is lost after the response is sent. This means:
- No audit trail for debugging
- No data to improve prompts
- No conversation history if you need to investigate a mis-booking
- The `recent_messages` feature mentioned in PIANO_MVP.md can't work

**Fix:** Add message logging in `backend/webhooks.py`. After the orchestrator returns a reply, log both the inbound message and the outbound reply.

Add a helper function to `backend/logic/booking.py` (or create a new `backend/logic/messages.py`):

```python
from backend.models.schema import Message

def log_message(
    db: Session,
    client_id,
    direction: str,  # "inbound" or "outbound"
    body: str,
    intent: str = None,
    entities: dict = None,
    confidence: float = None,
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
    return msg
```

Then in `backend/webhooks.py`, after line 37 (`reply = await handle_message(db, phone, text)`), add:

```python
        # Log messages
        from backend.logic.booking import get_or_create_client
        from backend.logic.messages import log_message  # or wherever you put it
        # We need the client_id — get_or_create_client was already called in handle_message
        # Consider having handle_message return both reply and metadata (client_id, intent, entities)
        # For now, look up client by phone:
        client = db.query(Client).filter_by(phone=phone).first()
        if client:
            log_message(db, client.id, "inbound", text)
            log_message(db, client.id, "outbound", reply)
```

A cleaner approach: modify `handle_message()` in `orchestrator.py` to return a dict `{"reply": str, "client_id": UUID, "intent": str, "entities": dict}` instead of just a string, so the webhook can log all metadata. This is a bigger refactor but worth doing.

---

## IMPORTANT FIXES (do before go-live)

---

### FIX 4: No booking confirmation step — contradicts plan rule #1

**File:** `backend/orchestrator.py`, function `_handle_book()` (lines 159-192)

**Problem:** When a user provides both date and time, the function immediately calls `create_booking()` without asking for confirmation. PIANO_MVP.md rule #1 says: "Mai prenotare senza conferma." This could lead to accidental bookings (e.g., user says "giovedì alle 10" meaning to ask about availability, and gets booked).

**Fix:** Add a `confirm_book` state. When date+time are both present and the slot is available:

1. Store the proposed booking details in context: `context.update(phone, pending_intent="confirm_book", entities=merged, proposed_booking={"date": ..., "time": ..., "service": ...})`
2. Reply with: `"Ti prenoto per {giorno} alle {ora} — confermi?"`
3. When the user's next message is classified as a confirmation (intent is `greeting` or `off_topic` but text matches confirmation patterns like "sì", "ok", "confermo", "va bene", "perfetto"), THEN call `create_booking()`.

Add a confirmation check near the top of `handle_message()` (after the name onboarding check, before `classify_intent()`):

```python
    # Check for pending booking confirmation
    if state.get("pending_intent") == "confirm_book":
        if _is_confirmation(text):
            return await _execute_confirmed_booking(db, practitioner, client, phone, state)
        elif _is_negation(text):
            context.clear(phone)
            return "Ok, nessun problema! Fammi sapere se vuoi prenotare in un altro momento."
        # If it's something else entirely, fall through to normal classification
```

Add helpers:
```python
_CONFIRM_PATTERNS = ("sì", "si", "ok", "confermo", "va bene", "perfetto", "certo", "esatto", "confermato")
_NEGATE_PATTERNS = ("no", "annulla", "lascia stare", "non voglio", "cambia")

def _is_confirmation(text: str) -> bool:
    t = text.lower().strip().rstrip("!.")
    return t in _CONFIRM_PATTERNS or any(p in t for p in _CONFIRM_PATTERNS)

def _is_negation(text: str) -> bool:
    t = text.lower().strip()
    return any(p in t for p in _NEGATE_PATTERNS)
```

---

### FIX 5: Merge classifier + extractor into a single LLM call

**Files:** `backend/ai/classifier.py`, `backend/ai/extractor.py`, `backend/ai/prompts.py`, `backend/orchestrator.py`

**Problem:** Each user message triggers 2-3 separate Haiku calls:
1. `classify_intent()` — ~0.5-1s
2. `extract_entities()` — ~0.5-1s (only for booking/cancel/reschedule intents)
3. `extract_name()` — ~0.5s (only during onboarding)

Total latency: 1-2.5s per message. Total cost: 2-3x.

**Fix:** Create a single `analyze_message()` function that returns both intent and entities in one call. Replace the separate classifier and extractor.

Create `backend/ai/analyzer.py`:

```python
import json
from datetime import date
import anthropic
from backend.config import settings

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

ANALYZE_PROMPT = """Sei l'assistente AI di un sistema di prenotazione per lezioni di Pilates.
La data di oggi è: {today} ({weekday}).

Dato il messaggio di un cliente, rispondi con un JSON che contiene:

1. "intent": una di queste categorie:
   - book: il cliente vuole prenotare una lezione
   - reschedule: vuole spostare una lezione esistente
   - cancel: vuole cancellare una lezione
   - query: chiede info su appuntamenti
   - package_info: chiede del pacchetto/lezioni rimanenti
   - greeting: saluto generico
   - off_topic: non c'entra con prenotazioni

2. "confidence": un valore da 0.0 a 1.0

3. "entities" (solo se presenti nel messaggio):
   - "date": la data menzionata (formato ISO YYYY-MM-DD). Interpreta date relative come "domani", "lunedì prossimo", ecc.
   - "time": l'orario menzionato (formato HH:MM, 24h). "alle 4 del pomeriggio" = "16:00"
   - "service": il tipo di servizio se menzionato

Se un'entità non è presente, omettila.

Rispondi SOLO con un JSON valido, senza markdown né spiegazioni:
{{"intent": "...", "confidence": 0.0, "entities": {{...}}}}"""

WEEKDAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


async def analyze_message(message: str) -> dict:
    """Single LLM call: classify intent + extract entities."""
    today = date.today()
    prompt = ANALYZE_PROMPT.format(
        today=today.isoformat(),
        weekday=WEEKDAYS_IT[today.weekday()],
    )
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=prompt,
        messages=[{"role": "user", "content": message}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(text)
        return {
            "intent": result.get("intent", "off_topic"),
            "confidence": result.get("confidence", 0.0),
            **result.get("entities", {}),
        }
    except json.JSONDecodeError:
        return {"intent": "off_topic", "confidence": 0.0}
```

Then update `backend/orchestrator.py`:
- Replace imports of `classify_intent` and `extract_entities` with `from backend.ai.analyzer import analyze_message`
- Replace the two-step flow (lines 64-73) with a single call:

```python
    result = await analyze_message(text)
    intent = result.get("intent", "off_topic")
    entities = {k: v for k, v in result.items() if k in ("date", "time", "service")}
    confidence = result.get("confidence", 0.0)
```

Keep `name_extractor.py` separate — it only runs during onboarding and has a different purpose.

You can delete `backend/ai/classifier.py` and `backend/ai/extractor.py` after migrating, or keep them as fallbacks.

---

### FIX 6: Webhook error handling + message deduplication

**File:** `backend/webhooks.py`

**Problem 1:** If `handle_message()` throws an unhandled exception, the webhook returns HTTP 500. WhatsApp will retry the webhook, causing the same message to be processed again (potentially creating duplicate bookings). The webhook should always return 200.

**Problem 2:** WhatsApp can deliver the same webhook payload multiple times (at-least-once delivery). Without deduplication, a client could get double-booked.

**Fix:** Wrap the message handling in try/except. Add a simple in-memory deduplication set.

Replace lines 23-41 with:

```python
# Simple deduplication (in-memory — good enough for MVP)
_processed_ids: set = set()
_MAX_DEDUP_SIZE = 10000


@router.post("/webhook")
async def receive_message(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    messages = (
        payload.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
        .get("messages", [])
    )
    replies = []
    for msg in messages:
        if msg.get("type") != "text":
            continue

        msg_id = msg.get("id", "")
        if msg_id in _processed_ids:
            print(f"[webhook] Skipping duplicate message {msg_id}")
            continue

        text = msg["text"]["body"]
        phone = msg["from"]
        profile_name = (
            payload.get("entry", [{}])[0]
            .get("changes", [{}])[0]
            .get("value", {})
            .get("contacts", [{}])[0]
            .get("profile", {})
            .get("name")
        )

        try:
            reply = await handle_message(db, phone, text, profile_name)
            await send_message(phone, reply)
            replies.append({"to": phone, "reply": reply})
            print(f"[webhook] {phone}: '{text}' → '{reply}'")
        except Exception as e:
            print(f"[webhook] ERROR processing message from {phone}: {e}")
            import traceback
            traceback.print_exc()
            # Don't re-raise — always return 200 to prevent WhatsApp retries

        # Track processed message
        _processed_ids.add(msg_id)
        if len(_processed_ids) > _MAX_DEDUP_SIZE:
            # Evict oldest entries (set doesn't preserve order, but this is good enough)
            _processed_ids.clear()

    return {"status": "ok", "replies": replies}
```

Note: also extract `profile_name` from the webhook payload and pass it to `handle_message()` — the function already accepts it as a parameter but the current webhook doesn't pass it.

---

### FIX 7: Practitioner instruct endpoint has no confirmation for destructive actions

**File:** `backend/ai/practitioner_nlp.py`, function `execute_instruction()` (lines 82-196)

**Problem:** When Silvia types "Cancella tutto domani", the system immediately cancels all bookings. There's no confirmation step. One typo could wipe an entire day's schedule.

**Fix:** Add a `dry_run` mode. The endpoint should first return what it WOULD do (listing affected bookings), and require a second call with `confirm=true` to execute.

Change the `execute_instruction` function signature:
```python
async def execute_instruction(db: Session, practitioner: Practitioner, instruction: str, confirm: bool = False) -> dict:
```

For destructive actions (cancel_day, cancel_range, cancel_client), when `confirm=False`, return the list of affected bookings WITHOUT executing:

```python
    if action == "cancel_day":
        d = date.fromisoformat(params["date"])
        bookings = _bookings_on_date(db, practitioner.id, d)
        if not confirm:
            clients = {c.id: c for c in db.query(Client).filter_by(practitioner_id=practitioner.id).all()}
            return {
                "action": action,
                "needs_confirmation": True,
                "summary": f"Sto per cancellare {len(bookings)} prenotazioni del {d.isoformat()}:",
                "items": [
                    {"time": b.starts_at.strftime("%H:%M"), "client": clients.get(b.client_id, None) and clients[b.client_id].full_name or "?"}
                    for b in bookings
                ],
                "confirm_params": {"instruction": instruction, "confirm": True},
            }
        for b in bookings:
            cancel_booking(db, b.id)
        # ... rest as before
```

Update the endpoint in `backend/practitioner.py` line 248:
```python
    result = await execute_instruction(db, p, instruction, confirm=body.get("confirm", False))
```

Update the frontend in `practitioner.html` to show a confirmation dialog when `needs_confirmation` is true, and re-send with `confirm: true`.

---

### FIX 8: Entity extractor doesn't know the current day of the week

**File:** `backend/ai/prompts.py`, the `EXTRACT_ENTITIES` prompt (lines 15-25)

**Problem:** The prompt tells the LLM today's date but not the day of the week. When a user says "lunedì" or "questo venerdì", the LLM has to calculate which calendar date corresponds. This is error-prone.

**Fix:** This is automatically resolved if you do FIX 5 (merge into `analyze_message()`), which includes the weekday. If you keep the separate extractor, change the prompt to:

```python
EXTRACT_ENTITIES = """Sei l'assistente AI di un sistema di prenotazione per lezioni di Pilates.
Oggi è: {weekday} {today}

Dato il messaggio di un cliente, estrai le seguenti entità se presenti:
- date: la data menzionata (formato ISO YYYY-MM-DD). Interpreta date relative come "domani", "lunedì prossimo", ecc.
- time: l'orario menzionato (formato HH:MM, 24h). Interpreta "alle 4 del pomeriggio" come "16:00".
- service: il tipo di servizio se menzionato (es. "individuale", "duo", "gruppo")

Se un'entità non è presente nel messaggio, omettila dal risultato.

Rispondi SOLO con un JSON con i campi: date, time, service."""
```

And update the call in `extractor.py`:
```python
WEEKDAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]

async def extract_entities(message: str) -> dict:
    today = date.today()
    prompt = EXTRACT_ENTITIES.format(
        today=today.isoformat(),
        weekday=WEEKDAYS_IT[today.weekday()],
    )
    # ... rest unchanged
```

---

## NEW FEATURES TO BUILD

---

### FEATURE 1: Seed script

**Create:** `backend/seed.py`

**Purpose:** Insert Silvia's practitioner record so the system is testable out of the box. This should be idempotent (safe to run multiple times).

```python
"""Seed the database with Silvia's practitioner data.

Usage: python -m backend.seed
"""
from backend.db.database import SessionLocal
from backend.models.schema import Practitioner

SILVIA_DATA = {
    "name": "Silvia",
    "phone": "393331234567",  # placeholder
    "profession": "Insegnante di Pilates",
    "working_hours": {
        "mon": [{"start": "08:00", "end": "13:00"}, {"start": "14:00", "end": "19:00"}],
        "tue": [{"start": "08:00", "end": "13:00"}, {"start": "14:00", "end": "19:00"}],
        "wed": [{"start": "08:00", "end": "13:00"}, {"start": "14:00", "end": "19:00"}],
        "thu": [{"start": "08:00", "end": "13:00"}, {"start": "14:00", "end": "19:00"}],
        "fri": [{"start": "08:00", "end": "13:00"}, {"start": "14:00", "end": "17:00"}],
    },
    "break_minutes": 5,
    "services": [
        {"name": "Pilates Individuale", "duration": 55, "price": 50},
        {"name": "Pilates Duo", "duration": 55, "price": 35},
        {"name": "Pilates Gruppo", "duration": 60, "price": 20},
    ],
    "timezone": "Europe/Rome",
}


def seed():
    db = SessionLocal()
    try:
        existing = db.query(Practitioner).filter_by(name="Silvia").first()
        if existing:
            print(f"Silvia already exists (id={existing.id}). Updating...")
            for key, value in SILVIA_DATA.items():
                setattr(existing, key, value)
        else:
            p = Practitioner(**SILVIA_DATA)
            db.add(p)
            print("Created practitioner Silvia.")
        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
```

Update the working hours to match Silvia's actual schedule once you confirm with her.

---

### FEATURE 2: Reminder scheduler

**Create:** `backend/logic/reminders.py`

**Purpose:** Send a WhatsApp reminder 24 hours before each confirmed booking. Mark as sent so it doesn't repeat.

```python
"""24-hour booking reminder scheduler.

Run as a standalone cron job or integrate with APScheduler.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from backend.models.schema import Booking, Client
from backend.whatsapp import send_message

ROME_TZ = ZoneInfo("Europe/Rome")

DAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


async def send_reminders(db: Session) -> int:
    """Find bookings 23-25h from now and send reminders. Returns count sent."""
    now = datetime.now(ROME_TZ)
    window_start = now + timedelta(hours=23)
    window_end = now + timedelta(hours=25)

    bookings = (
        db.query(Booking)
        .filter(
            Booking.status == "confirmed",
            Booking.reminder_sent == False,
            Booking.starts_at >= window_start,
            Booking.starts_at <= window_end,
        )
        .all()
    )

    sent = 0
    for booking in bookings:
        client = db.get(Client, booking.client_id)
        if not client:
            continue

        dt = booking.starts_at.astimezone(ROME_TZ)
        day_name = DAYS_IT[dt.weekday()]
        time_str = dt.strftime("%H:%M")
        name = client.first_name or "ciao"

        text = (
            f"Ciao {name}! Ti ricordo la tua lezione di {booking.service} "
            f"domani ({day_name}) alle {time_str} con Silvia. "
            f"Se hai bisogno di spostare, scrivimi qui!"
        )

        success = await send_message(client.phone, text)
        if success:
            booking.reminder_sent = True
            sent += 1

    db.commit()
    return sent
```

To run this, either:
- Add an APScheduler job in `main.py` that runs `send_reminders` every hour
- Or set up a Railway cron job that hits a `/api/send-reminders` endpoint
- Or use a simple `while True: sleep(3600)` worker process

Add an endpoint in `main.py` or `admin.py`:
```python
@router.post("/api/send-reminders")
async def trigger_reminders(db: Session = Depends(get_db)):
    count = await send_reminders(db)
    return {"sent": count}
```

---

### FEATURE 3: WhatsApp client (360dialog implementation)

**File:** `backend/whatsapp.py` (replace the stub)

The current implementation just prints to console. Replace with the real 360dialog API:

```python
import httpx
import logging
from backend.config import settings

logger = logging.getLogger(__name__)

API_URL = "https://waba.360dialog.io/v1/messages"


async def send_message(phone: str, text: str) -> bool:
    """Send a text message via 360dialog WhatsApp API."""
    if not settings.whatsapp_api_key:
        # Stub mode for local development
        print(f"[whatsapp-stub] → {phone}: {text}")
        return True

    headers = {
        "D360-API-KEY": settings.whatsapp_api_key,
        "Content-Type": "application/json",
    }

    body = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": text},
    }

    try:
        async with httpx.AsyncClient() as http:
            response = await http.post(API_URL, json=body, headers=headers, timeout=10)

        if response.status_code == 200:
            logger.info(f"Message sent to {phone}: {text[:80]}...")
            return True
        else:
            logger.error(f"360dialog API error {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {e}")
        return False


async def mark_as_read(message_id: str) -> None:
    """Mark a message as read (blue checkmarks)."""
    if not settings.whatsapp_api_key:
        return

    headers = {
        "D360-API-KEY": settings.whatsapp_api_key,
        "Content-Type": "application/json",
    }

    body = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    try:
        async with httpx.AsyncClient() as http:
            await http.post(API_URL, json=body, headers=headers, timeout=5)
    except Exception:
        pass
```

Note: check the exact 360dialog API format — it may differ slightly from the WhatsApp Cloud API. The header is `D360-API-KEY` (not `Authorization: Bearer`). The endpoint URL may be `https://waba.360dialog.io/v1/messages` or similar.

---

### FEATURE 4: Write tests

**Create:** `backend/tests/test_availability.py`, `backend/tests/test_booking.py`

At minimum, write unit tests for:

1. **Availability engine:**
   - Slot generation from working hours
   - Filtering out existing bookings
   - Handling days off (no working hours configured)
   - Break minutes between slots

2. **Booking logic:**
   - Create booking on available slot → success
   - Create booking on occupied slot → failure
   - Cancel booking → status changes, package session returned
   - Reschedule booking → old slot freed, new slot occupied
   - Get upcoming bookings → only future confirmed ones

3. **Orchestrator:**
   - Greeting → greeting response
   - Book with date+time → confirmation prompt (after FIX 4)
   - Confirmation → booking created
   - Cancel → booking cancelled
   - Unknown message → fallback response

Use SQLite in-memory for test DB (or mock the DB session).

Add `pytest` to `requirements.txt`.

---

## MINOR IMPROVEMENTS

---

### MINOR 1: Add `practitioner_id` to Message model

**File:** `backend/models/schema.py`, line 70-78

The `Message` model has `client_id` but no `practitioner_id`. The migration `001_initial_schema.sql` also doesn't have it. For multi-tenant support later, add:

```python
class Message(Base):
    __tablename__ = "messages"
    # ... existing fields ...
    practitioner_id = Column(UUID(as_uuid=True), ForeignKey("practitioners.id", ondelete="CASCADE"), nullable=True)
```

And create a migration:
```sql
ALTER TABLE messages ADD COLUMN IF NOT EXISTS practitioner_id UUID REFERENCES practitioners(id) ON DELETE CASCADE;
```

---

### MINOR 2: Add logging throughout

**Files:** Multiple

Add `import logging` and `logger = logging.getLogger(__name__)` to all modules. Use `logger.info()` for normal operations and `logger.error()` for failures. Currently only `practitioner_nlp.py` and `booking.py` have explicit print statements.

---

### MINOR 3: Add CORS middleware

**File:** `backend/main.py`

If the practitioner dashboard or test console will be served from a different domain (e.g., Vercel), add CORS:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

### MINOR 4: Add `__all__` exports and clean up imports

**File:** `backend/ai/__init__.py`, `backend/logic/__init__.py`, `backend/models/__init__.py`

These are currently empty. Consider adding convenience imports:

```python
# backend/ai/__init__.py
from backend.ai.analyzer import analyze_message
from backend.ai.name_extractor import extract_name
from backend.ai.context import get, update, clear
```

---

## SUMMARY — Execution Order

| # | Task | Priority | Est. Time |
|---|------|----------|-----------|
| 1 | Fix async AI calls (FIX 1) | CRITICAL | 15 min |
| 2 | Fix timezone handling (FIX 2) | CRITICAL | 45 min |
| 3 | Add message logging (FIX 3) | CRITICAL | 30 min |
| 4 | Add booking confirmation (FIX 4) | IMPORTANT | 45 min |
| 5 | Merge classifier+extractor (FIX 5) | IMPORTANT | 1 hour |
| 6 | Webhook error handling (FIX 6) | IMPORTANT | 30 min |
| 7 | Practitioner instruct confirmation (FIX 7) | IMPORTANT | 30 min |
| 8 | Extractor weekday fix (FIX 8) | IMPORTANT | 10 min |
| 9 | Create seed script (FEATURE 1) | NEEDED | 20 min |
| 10 | Build reminder scheduler (FEATURE 2) | NEEDED | 1 hour |
| 11 | Implement WhatsApp client (FEATURE 3) | NEEDED | 1 hour |
| 12 | Write tests (FEATURE 4) | NEEDED | 2 hours |
| 13 | Minor improvements (MINOR 1-4) | NICE TO HAVE | 30 min |
