import json
from datetime import date
import anthropic
from backend.config import settings
from backend.ai.prompts import EXTRACT_ENTITIES

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


async def extract_entities(message: str) -> dict:
    prompt = EXTRACT_ENTITIES.format(today=date.today().isoformat())
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        system=prompt,
        messages=[{"role": "user", "content": message}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}
