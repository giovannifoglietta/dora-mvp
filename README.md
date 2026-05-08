# Dora MVP

AI-powered WhatsApp booking assistant for wellness professionals.

## Quick start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload
```

Visit `http://localhost:8000` — you should see `{"status": "Dora is alive"}`.
