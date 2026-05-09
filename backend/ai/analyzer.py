"""Single-call message analyzer: returns intent + entities + confidence in one
Haiku request. Replaces the separate classifier and extractor calls — about 50%
faster and ~50% cheaper per message."""
import json
from datetime import date, timedelta
import anthropic
from backend.config import settings

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

DAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def _calendar(today: date, days: int = 14) -> str:
    rows = []
    for i in range(days):
        d = today + timedelta(days=i)
        marker = " (OGGI)" if i == 0 else " (domani)" if i == 1 else ""
        rows.append(f"  {DAYS_IT[d.weekday()]} {d.isoformat()}{marker}")
    return "\n".join(rows)


_PROMPT = """Sei l'assistente AI di un sistema di prenotazione per lezioni di Pilates.

Oggi è {weekday} {today}.
Riferimento prossimi giorni:
{calendar}

Dato il messaggio di un cliente, rispondi con un JSON che contiene:

1. "intent": una di queste categorie:
   - book: il cliente vuole prenotare una lezione (es. "vorrei venire giovedì")
   - reschedule: vuole spostare una lezione esistente (es. "posso spostare a venerdì?")
   - cancel: vuole cancellare una lezione (es. "domani non riesco")
   - query: chiede info su appuntamenti (es. "quando è il prossimo?")
   - package_info: chiede del pacchetto/lezioni rimanenti (es. "quante lezioni ho?")
   - greeting: saluto generico (es. "ciao!", "buongiorno")
   - off_topic: non c'entra con prenotazioni

2. "confidence": un valore da 0.0 a 1.0

3. "entities" (oggetto, anche vuoto):
   - "date": la data menzionata in formato ISO YYYY-MM-DD. USA la tabella sopra per "lunedì", "martedì", ecc.
   - "time": l'orario in formato HH:MM, 24h. "alle 4 del pomeriggio" = "16:00".
   - "service": tipo di servizio se menzionato ("individuale", "duo", "gruppo")

Ometti i campi non presenti.

Rispondi SOLO con un JSON valido, senza markdown:
{{"intent": "...", "confidence": 0.0, "entities": {{}}}}"""


def _correct_named_day(message: str, parsed_iso: str, today: date) -> str:
    """If the message mentions a weekday and the parsed date doesn't match it, fix it."""
    t = message.lower()
    target_idx = None
    is_next_week = "prossim" in t
    for i, name in enumerate(DAYS_IT):
        if name in t:
            target_idx = i
            break
    if target_idx is None:
        return parsed_iso
    try:
        d = date.fromisoformat(parsed_iso)
    except (ValueError, TypeError):
        return parsed_iso
    if d.weekday() == target_idx and not is_next_week:
        return parsed_iso
    days_ahead = (target_idx - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    if is_next_week:
        days_ahead += 7
    return (today + timedelta(days=days_ahead)).isoformat()


async def analyze_message(message: str) -> dict:
    """Returns: {"intent": str, "confidence": float, "date": ?, "time": ?, "service": ?}"""
    today = date.today()
    prompt = _PROMPT.format(
        today=today.isoformat(),
        weekday=DAYS_IT[today.weekday()],
        calendar=_calendar(today),
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
    except json.JSONDecodeError:
        return {"intent": "off_topic", "confidence": 0.0}

    intent = result.get("intent", "off_topic")
    confidence = float(result.get("confidence", 0.0))
    entities = result.get("entities") or {}

    if entities.get("date"):
        entities["date"] = _correct_named_day(message, entities["date"], today)

    return {"intent": intent, "confidence": confidence, **entities}
