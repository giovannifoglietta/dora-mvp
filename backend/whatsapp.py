"""WhatsApp client. Uses 360dialog when WHATSAPP_API_KEY is set, otherwise
falls back to a console stub for local dev / pre-SIM testing."""
import logging
import httpx
from backend.config import settings

logger = logging.getLogger(__name__)

API_URL = "https://waba.360dialog.io/v1/messages"


async def send_message(phone: str, text: str) -> bool:
    """Send a text message. Returns True on success, False on failure.
    Stub mode (no key) always returns True after logging the message."""
    if not settings.whatsapp_api_key:
        print(f"[whatsapp-stub] → {phone}: {text}")
        return True

    headers = {
        "D360-API-KEY": settings.whatsapp_api_key,
        "Content-Type": "application/json",
    }
    body = {
        "messaging_product": "whatsapp",
        "to": phone.lstrip("+"),
        "type": "text",
        "text": {"body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            response = await http.post(API_URL, json=body, headers=headers)
        if 200 <= response.status_code < 300:
            logger.info(f"WhatsApp sent to {phone}")
            return True
        logger.error(f"360dialog {response.status_code}: {response.text}")
        return False
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
        return False


async def mark_as_read(message_id: str) -> None:
    """Mark a message as read (blue checkmarks). Best-effort, never raises."""
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
        async with httpx.AsyncClient(timeout=5) as http:
            await http.post(API_URL, json=body, headers=headers)
    except Exception:
        pass
