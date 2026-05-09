import traceback
from fastapi import APIRouter, Request, Query, Response, Depends
from sqlalchemy.orm import Session
from backend.config import settings
from backend.db.database import get_db
from backend.orchestrator import handle_message
from backend.whatsapp import send_message

router = APIRouter()

# In-memory dedup of inbound message ids. Cleared on server restart (fine: WhatsApp
# won't retry hours later). Reset when it gets too large.
_processed_ids: set = set()
_DEDUP_LIMIT = 10000


def _seen(msg_id: str) -> bool:
    if msg_id in _processed_ids:
        return True
    if len(_processed_ids) >= _DEDUP_LIMIT:
        _processed_ids.clear()
    _processed_ids.add(msg_id)
    return False


@router.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_webhook_token:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhook")
async def receive_message(request: Request, db: Session = Depends(get_db)):
    """Always returns 200 — even if processing fails — so WhatsApp won't retry."""
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok", "replies": []}

    entry = (payload.get("entry") or [{}])[0]
    change = (entry.get("changes") or [{}])[0]
    value = change.get("value") or {}
    messages = value.get("messages") or []
    contacts = value.get("contacts") or []
    profile_name = (contacts[0].get("profile") or {}).get("name") if contacts else None

    replies = []
    for msg in messages:
        if msg.get("type") != "text":
            continue

        msg_id = msg.get("id", "")
        if msg_id and _seen(msg_id):
            print(f"[webhook] skipping duplicate {msg_id}")
            continue

        text = msg.get("text", {}).get("body", "")
        phone = msg.get("from", "")
        if not text or not phone:
            continue

        try:
            reply = await handle_message(db, phone, text, profile_name)
            await send_message(phone, reply)
            replies.append({"to": phone, "reply": reply})
            print(f"[webhook] {phone}: '{text}' → '{reply}'")
        except Exception as e:
            print(f"[webhook] ERROR processing message from {phone}: {e}")
            traceback.print_exc()
            # Try to send a graceful fallback so the user isn't left hanging
            try:
                await send_message(phone, "Ops, qualcosa non ha funzionato. Riprova tra un momento.")
            except Exception:
                pass

    return {"status": "ok", "replies": replies}


@router.post("/test/message")
async def test_message(request: Request, db: Session = Depends(get_db)):
    """Test endpoint: POST {phone, text} → returns Dora's reply without WhatsApp roundtrip."""
    body = await request.json()
    reply = await handle_message(db, body["phone"], body["text"])
    return {"reply": reply}
