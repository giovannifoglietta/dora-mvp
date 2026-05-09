import json
import re
from typing import Optional, Tuple
import anthropic
from backend.config import settings

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

_NAME_PROMPT = """Estrai il nome e cognome della persona che scrive (cioè il mittente del messaggio).

Regole:
- Cerca un'auto-presentazione: "sono Marco Rossi", "mi chiamo Anna", "Marco" come risposta secca, "Marco Rossi" come risposta secca.
- IGNORA nomi di altre persone ("vorrei prenotare per Maria" → niente nome).
- IGNORA saluti e parole comuni ("ciao", "buongiorno" non sono nomi).
- Se c'è solo il nome senza cognome, lascia il cognome vuoto.

Rispondi SOLO con un JSON, senza spiegazioni e senza markdown:
{"first_name": "Marco", "last_name": "Rossi"}
oppure se non c'è nome:
{"first_name": null, "last_name": null}"""


def _clean(s: Optional[str]) -> Optional[str]:
    if not s or not isinstance(s, str):
        return None
    s = re.sub(r"[^\w\sÀ-ÿ'-]", "", s).strip()
    if len(s) < 2:
        return None
    parts = [p for p in s.split() if p][:2]
    return " ".join(parts).title() if parts else None


async def extract_name(message: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (first_name, last_name). Either or both can be None."""
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=80,
        system=_NAME_PROMPT,
        messages=[{"role": "user", "content": message}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, None
    return _clean(data.get("first_name")), _clean(data.get("last_name"))
