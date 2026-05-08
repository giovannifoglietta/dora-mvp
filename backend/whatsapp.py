import httpx
from backend.config import settings


async def send_message(phone: str, text: str) -> dict:
    """Send a text message via 360dialog WhatsApp API. Stub for now."""
    print(f"[whatsapp] would send to {phone}: {text}")
    return {"status": "stub"}
