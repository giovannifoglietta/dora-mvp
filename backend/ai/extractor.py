import json
import re
from datetime import date, timedelta
import anthropic
from backend.config import settings
from backend.ai.prompts import EXTRACT_ENTITIES

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

DAYS_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def _build_calendar(today: date, days: int = 14) -> str:
    rows = []
    for i in range(days):
        d = today + timedelta(days=i)
        marker = " (OGGI)" if i == 0 else " (domani)" if i == 1 else ""
        rows.append(f"  {DAYS_IT[d.weekday()]} {d.isoformat()}{marker}")
    return "\n".join(rows)


def _named_day_in_text(text: str):
    """Return the weekday index (0=Mon) named in the text, or None."""
    t = text.lower()
    for i, name in enumerate(DAYS_IT):
        if re.search(r"\b" + name + r"\b", t):
            return i, "prossim" in t
    return None


def _correct_date_for_named_day(message: str, parsed_date_iso: str, today: date) -> str:
    """If the message names a weekday and the parsed date doesn't match, fix it."""
    named = _named_day_in_text(message)
    if not named:
        return parsed_date_iso
    target_idx, is_next_week = named
    try:
        d = date.fromisoformat(parsed_date_iso)
    except (ValueError, TypeError):
        return parsed_date_iso
    if d.weekday() == target_idx:
        return parsed_date_iso
    # Find the next occurrence of target_idx from today
    days_ahead = (target_idx - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7  # avoid landing on today unless the message clearly says "oggi"
    if is_next_week:
        days_ahead += 7
    corrected = today + timedelta(days=days_ahead)
    return corrected.isoformat()


async def extract_entities(message: str) -> dict:
    today = date.today()
    prompt = EXTRACT_ENTITIES.format(
        weekday_it=DAYS_IT[today.weekday()],
        today=today.isoformat(),
        day_calendar=_build_calendar(today),
    )
    response = client.messages.create(
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
        return {}

    # Verify against named weekday in message — Haiku occasionally drifts by a day
    if result.get("date"):
        result["date"] = _correct_date_for_named_day(message, result["date"], today)

    return result
