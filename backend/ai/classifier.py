import json
import anthropic
from backend.config import settings
from backend.ai.prompts import CLASSIFY_INTENT

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def classify_intent(message: str) -> dict:
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        system=CLASSIFY_INTENT,
        messages=[{"role": "user", "content": message}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"intent": "off_topic", "confidence": 0.0}
