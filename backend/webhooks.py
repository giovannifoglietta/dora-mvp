from fastapi import APIRouter, Request, Query, Response, Depends
from sqlalchemy.orm import Session
from backend.config import settings
from backend.db.database import get_db
from backend.orchestrator import handle_message
from backend.whatsapp import send_message

router = APIRouter()


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
    payload = await request.json()
    messages = (
        payload.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
        .get("messages", [])
    )
    replies = []
    for msg in messages:
        if msg.get("type") != "text":
            continue
        text = msg["text"]["body"]
        phone = msg["from"]
        reply = await handle_message(db, phone, text)
        await send_message(phone, reply)
        replies.append({"to": phone, "reply": reply})
        print(f"[webhook] {phone}: '{text}' → '{reply}'")
    return {"status": "ok", "replies": replies}


@router.post("/test/message")
async def test_message(request: Request, db: Session = Depends(get_db)):
    """Test endpoint: POST {phone, text} → returns Dora's reply without WhatsApp roundtrip."""
    body = await request.json()
    reply = await handle_message(db, body["phone"], body["text"])
    return {"reply": reply}
