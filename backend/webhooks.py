from fastapi import APIRouter, Request, Query, Response
from backend.config import settings
from backend.ai.classifier import classify_intent
from backend.ai.extractor import extract_entities

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
async def receive_message(request: Request):
    payload = await request.json()
    messages = (
        payload.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
        .get("messages", [])
    )
    for msg in messages:
        if msg.get("type") != "text":
            continue
        text = msg["text"]["body"]
        phone = msg["from"]
        intent_result = await classify_intent(text)
        entities = await extract_entities(text) if intent_result["intent"] in ("book", "reschedule", "cancel") else {}
        print(f"[webhook] {phone}: '{text}' → intent={intent_result}, entities={entities}")
    return {"status": "ok"}
