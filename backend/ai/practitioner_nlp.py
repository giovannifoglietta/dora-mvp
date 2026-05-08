"""Parse and execute natural-language instructions from the practitioner.

Examples:
- "Cancella tutto domani"  → cancel all bookings on tomorrow's date
- "Cancella le lezioni di lunedì 12 maggio" → cancel bookings on a specific date
- "Sposta la lezione di Marco di domani alle 15" → reschedule
- "Blocca martedì pomeriggio"  → (future feature: time blocks)
"""
import json
from datetime import datetime, date, timedelta
from typing import Optional
import anthropic
from sqlalchemy.orm import Session
from backend.config import settings
from backend.models.schema import Booking, Client, Practitioner
from backend.logic.booking import cancel_booking, reschedule_booking, BookingError

client_ai = anthropic.Anthropic(api_key=settings.anthropic_api_key)

_NLP_PROMPT = """Sei un assistente che interpreta istruzioni in italiano da un professionista (insegnante di Pilates) e le converte in azioni strutturate.

La data di oggi è: {today}

Azioni disponibili:
1. "cancel_day" - cancella tutte le prenotazioni di un giorno
   parametri: {{"date": "YYYY-MM-DD"}}
2. "cancel_range" - cancella tutte le prenotazioni in un intervallo di giorni
   parametri: {{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}}
3. "cancel_client" - cancella le prenotazioni di un cliente specifico (opzionalmente in un giorno)
   parametri: {{"client_name": "Marco", "date": "YYYY-MM-DD" (opzionale)}}
4. "reschedule" - sposta una prenotazione
   parametri: {{"client_name": "Marco", "from_date": "YYYY-MM-DD", "to_date": "YYYY-MM-DD", "to_time": "HH:MM"}}
5. "list_day" - mostra le prenotazioni di un giorno (azione di sola lettura)
   parametri: {{"date": "YYYY-MM-DD"}}
6. "unknown" - se l'istruzione non è chiara

Rispondi SOLO con un JSON, senza markdown:
{{"action": "<azione>", "params": {{...}}, "explanation": "breve spiegazione di cosa farai"}}"""


async def parse_instruction(instruction: str) -> dict:
    prompt = _NLP_PROMPT.format(today=date.today().isoformat())
    response = client_ai.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=prompt,
        messages=[{"role": "user", "content": instruction}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"action": "unknown", "params": {}, "explanation": "Non ho capito l'istruzione."}


def _bookings_on_date(db: Session, practitioner_id, target_date: date):
    return (
        db.query(Booking)
        .filter(
            Booking.practitioner_id == practitioner_id,
            Booking.status == "confirmed",
            Booking.starts_at >= datetime.combine(target_date, datetime.min.time()),
            Booking.starts_at < datetime.combine(target_date + timedelta(days=1), datetime.min.time()),
        )
        .order_by(Booking.starts_at)
        .all()
    )


def _find_client(db: Session, practitioner_id, name: str) -> Optional[Client]:
    name = name.strip().lower()
    clients = db.query(Client).filter_by(practitioner_id=practitioner_id).all()
    for c in clients:
        full = (c.full_name or "").lower()
        if full == name or full.startswith(name + " ") or (c.first_name and c.first_name.lower() == name):
            return c
    return None


async def execute_instruction(db: Session, practitioner: Practitioner, instruction: str) -> dict:
    parsed = await parse_instruction(instruction)
    action = parsed.get("action")
    params = parsed.get("params", {})

    if action == "cancel_day":
        d = date.fromisoformat(params["date"])
        bookings = _bookings_on_date(db, practitioner.id, d)
        for b in bookings:
            cancel_booking(db, b.id)
        return {
            "action": action,
            "executed": True,
            "summary": f"Ho cancellato {len(bookings)} prenotazioni del {d.isoformat()}.",
            "affected_bookings": [str(b.id) for b in bookings],
        }

    if action == "cancel_range":
        start = date.fromisoformat(params["start_date"])
        end = date.fromisoformat(params["end_date"])
        all_b = []
        d = start
        while d <= end:
            all_b.extend(_bookings_on_date(db, practitioner.id, d))
            d += timedelta(days=1)
        for b in all_b:
            cancel_booking(db, b.id)
        return {
            "action": action,
            "executed": True,
            "summary": f"Ho cancellato {len(all_b)} prenotazioni dal {start} al {end}.",
            "affected_bookings": [str(b.id) for b in all_b],
        }

    if action == "cancel_client":
        cname = params.get("client_name", "")
        c = _find_client(db, practitioner.id, cname)
        if not c:
            return {"action": action, "executed": False, "summary": f"Non trovo il cliente '{cname}'."}
        q = db.query(Booking).filter(
            Booking.client_id == c.id,
            Booking.status == "confirmed",
            Booking.starts_at >= datetime.utcnow(),
        )
        if params.get("date"):
            d = date.fromisoformat(params["date"])
            q = q.filter(
                Booking.starts_at >= datetime.combine(d, datetime.min.time()),
                Booking.starts_at < datetime.combine(d + timedelta(days=1), datetime.min.time()),
            )
        bookings = q.all()
        for b in bookings:
            cancel_booking(db, b.id)
        return {
            "action": action,
            "executed": True,
            "summary": f"Ho cancellato {len(bookings)} prenotazioni di {c.full_name}.",
            "affected_bookings": [str(b.id) for b in bookings],
        }

    if action == "reschedule":
        cname = params.get("client_name", "")
        c = _find_client(db, practitioner.id, cname)
        if not c:
            return {"action": action, "executed": False, "summary": f"Non trovo il cliente '{cname}'."}
        from_date = date.fromisoformat(params["from_date"])
        target = (
            db.query(Booking)
            .filter(
                Booking.client_id == c.id,
                Booking.status == "confirmed",
                Booking.starts_at >= datetime.combine(from_date, datetime.min.time()),
                Booking.starts_at < datetime.combine(from_date + timedelta(days=1), datetime.min.time()),
            )
            .first()
        )
        if not target:
            return {"action": action, "executed": False, "summary": f"Non trovo una lezione di {c.full_name} il {from_date}."}
        new_when = datetime.combine(
            date.fromisoformat(params["to_date"]),
            datetime.strptime(params["to_time"], "%H:%M").time(),
        )
        try:
            reschedule_booking(db, target.id, new_when)
            return {
                "action": action, "executed": True,
                "summary": f"Spostata la lezione di {c.full_name} a {new_when.strftime('%d/%m alle %H:%M')}.",
                "affected_bookings": [str(target.id)],
            }
        except BookingError as e:
            return {"action": action, "executed": False, "summary": f"Errore: {e}"}

    if action == "list_day":
        d = date.fromisoformat(params["date"])
        bookings = _bookings_on_date(db, practitioner.id, d)
        clients = {c.id: c for c in db.query(Client).filter_by(practitioner_id=practitioner.id).all()}
        items = [
            {
                "time": b.starts_at.strftime("%H:%M"),
                "client": clients[b.client_id].full_name if b.client_id in clients else "?",
            }
            for b in bookings
        ]
        return {
            "action": action,
            "executed": True,
            "summary": f"{len(bookings)} prenotazioni il {d}.",
            "items": items,
        }

    return {
        "action": "unknown",
        "executed": False,
        "summary": parsed.get("explanation", "Non ho capito l'istruzione. Prova a essere più specifica."),
    }
