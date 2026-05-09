"""Deterministic fast-path parser for common Italian booking phrases.

Returns the same shape as analyze_message() so it's drop-in. When the rules
don't recognize the message, returns None and the caller should fall back to
the LLM analyzer.

The point: avoid a 500ms+ LLM round-trip on simple, frequent inputs like
"domani alle 10", "ciao", "quante lezioni ho?".
"""
import re
from datetime import date, timedelta
from typing import Optional

DAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
# Tolerate accents/diacritics: "lunedi", "martedi", etc.
_DAY_VARIANTS = {
    "lunedì": 0, "lunedi": 0,
    "martedì": 1, "martedi": 1,
    "mercoledì": 2, "mercoledi": 2,
    "giovedì": 3, "giovedi": 3,
    "venerdì": 4, "venerdi": 4,
    "sabato": 5,
    "domenica": 6,
}


# ---------------------------------------------------------------------------
# Greeting / package / query patterns
# ---------------------------------------------------------------------------

_GREETING_RE = re.compile(r"^\s*(ciao|buongiorno|buon giorno|buonasera|buona sera|salve|ehi|hey|hola)\s*[!.?]*\s*$", re.IGNORECASE)
_PACKAGE_QUERY_RE = re.compile(r"\b(pacchett|quante lezioni|lezioni rimaste|lezioni mi restano|sessioni rimaste|quanti credi)", re.IGNORECASE)
_QUERY_NEXT_RE = re.compile(r"\b(quando|che giorno|che ora).*(prossim|appuntament|lezione|venire)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Cancel / book / reschedule keywords
# ---------------------------------------------------------------------------

_CANCEL_RE = re.compile(r"\b(cancell\w*|disdir\w*|disdic\w*|annull\w*|non posso|non riesco|non vengo|salto)\b", re.IGNORECASE)
_BOOK_RE = re.compile(r"\b(prenot\w*|vorrei (?:venire|prenotare)|posso venire|fissare|prendere appuntamento)\b", re.IGNORECASE)
_RESCHEDULE_RE = re.compile(r"\b(spostar\w*|sposta(?:re|mi|ci|la|lo)?|riprogramma\w*|cambiar\w* (?:l'?ora|il giorno|la lezione))\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Date / time extraction
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(
    r"\b"
    r"(?:alle\s+)?"
    r"(?:(?:le|l[''])\s*)?"
    r"(\d{1,2})"
    r"(?:[:.](\d{2}))?"
    r"(?:\s*(am|pm|del mattino|di mattina|del pomeriggio|di pomeriggio|di sera))?"
    r"\b",
    re.IGNORECASE,
)


def _resolve_relative_date(text: str, today: date) -> Optional[str]:
    t = text.lower()
    if re.search(r"\boggi\b", t):
        return today.isoformat()
    if re.search(r"\bdomani\b", t):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r"\bdopodomani\b", t):
        return (today + timedelta(days=2)).isoformat()

    # Named weekday — find next occurrence (or +7 if "prossim*")
    is_next_week = bool(re.search(r"\bprossim", t))
    for name, idx in _DAY_VARIANTS.items():
        if re.search(rf"\b{name}\b", t):
            days_ahead = (idx - today.weekday()) % 7
            if days_ahead == 0 and not re.search(r"\boggi\b", t):
                days_ahead = 7
            if is_next_week:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).isoformat()
    return None


def _extract_time(text: str) -> Optional[str]:
    """Return HH:MM or None. Disambiguates with afternoon/evening hints."""
    t = text.lower()
    # First, time-of-day phrases without explicit hour
    if re.search(r"\bmattin", t) and not re.search(r"\bdel mattino\b", t):
        # "mattina" without explicit hour → no specific time, leave None
        # (we'd need a separate heuristic to default to e.g. 09:00)
        pass
    m = _TIME_RE.search(t)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    suffix = (m.group(3) or "").lower()

    # Plausibility: 0..23
    if not (0 <= hour <= 23):
        return None

    # Adjust 12h-style if hour is 1-11 and afternoon/evening suffix
    if 1 <= hour <= 11 and suffix in ("pm", "del pomeriggio", "di pomeriggio", "di sera"):
        hour += 12

    # Heuristic: bare numbers like "alle 4" → if afternoon context, bump to 16
    # (only when there's no morning suffix and no minute precision)
    if not suffix and 1 <= hour <= 7 and not m.group(2):
        # Slight bias toward afternoon for low single-digit hours
        # but only if user didn't say "mattina"
        if not re.search(r"\bmattin", t) and not re.search(r"\bdel mattino\b", t):
            hour += 12

    return f"{hour:02d}:{minute:02d}"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def try_parse(text: str, today: Optional[date] = None) -> Optional[dict]:
    """Try to parse the message deterministically.

    Returns a dict shaped like analyze_message() if confident, else None.
    Output: {"intent": str, "confidence": float, "date"?: str, "time"?: str, "service"?: str}
    """
    if not text:
        return None
    today = today or date.today()
    raw = text.strip()
    lower = raw.lower()

    # Greeting
    if _GREETING_RE.match(raw):
        return {"intent": "greeting", "confidence": 1.0}

    # Package query
    if _PACKAGE_QUERY_RE.search(lower):
        return {"intent": "package_info", "confidence": 0.95}

    # Query about next appointment
    if _QUERY_NEXT_RE.search(lower):
        return {"intent": "query", "confidence": 0.9}

    # Try to extract date/time even before classifying intent
    parsed_date = _resolve_relative_date(text, today)
    parsed_time = _extract_time(text)

    # Cancel
    if _CANCEL_RE.search(lower):
        result = {"intent": "cancel", "confidence": 0.9}
        if parsed_date:
            result["date"] = parsed_date
        return result

    # Reschedule
    if _RESCHEDULE_RE.search(lower):
        result = {"intent": "reschedule", "confidence": 0.9}
        if parsed_date:
            result["date"] = parsed_date
        if parsed_time:
            result["time"] = parsed_time
        return result

    # Book — explicit verb
    if _BOOK_RE.search(lower):
        result = {"intent": "book", "confidence": 0.9}
        if parsed_date:
            result["date"] = parsed_date
        if parsed_time:
            result["time"] = parsed_time
        return result

    # Pure date+time without verb — likely a continuation answer ("alle 10", "domani")
    # But ONLY if the message is short. Long messages defer to LLM.
    if len(lower.split()) <= 4 and (parsed_date or parsed_time):
        result = {"intent": "book", "confidence": 0.75}
        if parsed_date:
            result["date"] = parsed_date
        if parsed_time:
            result["time"] = parsed_time
        return result

    return None
