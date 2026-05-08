from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from backend.webhooks import router as webhook_router
from backend.admin import router as admin_router
from backend.practitioner import router as practitioner_router

app = FastAPI(title="Dora", version="0.1.0")

app.include_router(webhook_router)
app.include_router(admin_router)
app.include_router(practitioner_router)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def root():
    return {"status": "Dora is alive"}


@app.get("/console")
def console():
    return FileResponse(STATIC_DIR / "index.html")
