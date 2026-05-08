from fastapi import FastAPI
from backend.webhooks import router as webhook_router

app = FastAPI(title="Dora", version="0.1.0")

app.include_router(webhook_router)


@app.get("/")
def health():
    return {"status": "Dora is alive"}
