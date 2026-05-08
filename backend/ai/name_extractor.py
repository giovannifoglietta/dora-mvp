import re
from typing import Optional
import anthropic
from backend.config import settings

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

_NAME_PROMPT = """Estrai il nome di battesimo (e cognome se presente) della persona che scrive.

Regole:
- Se il messaggio contiene un nome chiaramente attribuibile al mittente (es. "sono Marco", "mi chiamo Anna Rossi", o solo "Marco" come risposta), restituiscilo.
- Ignora nomi di altre persone (es. "vorrei prenotare per Maria" → NONE).
- Ignora saluti generici e parole comuni (es. "ciao" non è un nome).
- Se non c'è un nome chiaro, rispondi esattamente: NONE

Rispondi SOLO con il nome (max 2 parole, es. "Marco" o "Anna Rossi") oppure "NONE"."""


def _clean(name: str) -> str:
    name = re.sub(r"[^\w\sÀ-ÿ'-]", "", name).strip()
    parts = [p for p in name.split() if p][:2]
    return " ".join(parts).title()


async def extract_name(message: str) -> Optional[str]:
    """Use Claude to extract a self-attributed name from the message. Returns None if absent."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=20,
        system=_NAME_PROMPT,
        messages=[{"role": "user", "content": message}],
    )
    text = response.content[0].text.strip()
    if text.upper().startswith("NONE") or len(text) < 2 or len(text) > 60:
        return None
    cleaned = _clean(text)
    return cleaned if len(cleaned) >= 2 else None
