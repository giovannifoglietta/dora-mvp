# Dora MVP

AI-powered WhatsApp booking assistant for wellness professionals.

## Quick start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m backend.seed         # one-time: creates Silvia
uvicorn backend.main:app --reload
```

Visit:
- `http://localhost:8000` — health check
- `http://localhost:8000/console` — test console (chat as a client + live DB state)
- `http://localhost:8000/practitioner` — practitioner panel (PIN: 1234)

## Production URL

`https://web-production-816f6.up.railway.app/` — same pages as above.

## Environment variables

| Name | Required | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Claude Haiku for NLU |
| `DATABASE_URL` | yes | Use Supabase **transaction pooler** URL (IPv4) |
| `WHATSAPP_WEBHOOK_TOKEN` | yes | Random string used for Meta webhook handshake |
| `WHATSAPP_API_KEY` | when SIM is live | 360dialog API key. Without it, `send_message` is a console stub. |
| `PRACTITIONER_PIN` | optional | Practitioner panel PIN. Defaults to `1234`. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | for calendar sync | Full JSON content of service-account key |
| `GOOGLE_CALENDAR_ID` | for calendar sync | e.g. `abc...@group.calendar.google.com` |

## Google Calendar setup

This connects bookings to a Google Calendar so Silvia sees them in her usual calendar app.

1. **Create a GCP project**: <https://console.cloud.google.com/projectcreate>
2. **Enable the Google Calendar API**: APIs & Services → Library → "Google Calendar API" → Enable.
3. **Create a service account**:
   - IAM & Admin → Service Accounts → Create.
   - Name it e.g. `dora-calendar-sync`.
   - Skip the "grant access" steps.
4. **Create a key**: open the service account → Keys → Add Key → JSON. Download the file.
5. **Create the calendar in Google Calendar**:
   - In <https://calendar.google.com>, "+ Other calendars" → Create new calendar.
   - Name it e.g. "Dora — Pilates" and save.
6. **Find the calendar ID**:
   - Settings → pick the calendar → "Integrate calendar" → copy **Calendar ID**.
7. **Share it with the service account**:
   - Same settings page → "Share with specific people" → Add the service account's email
     (looks like `dora-calendar-sync@<project>.iam.gserviceaccount.com`) with permission
     **"Make changes to events"**.
8. **Set Railway env vars**:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` = paste the **entire JSON** from step 4 (Railway accepts multi-line)
   - `GOOGLE_CALENDAR_ID` = the ID from step 6

Bookings created/cancelled/rescheduled in Dora will now sync to that calendar. Failures
in calendar sync are logged but never block the booking.

## Reminder cron

Every booking 23–25h away gets a WhatsApp reminder. Trigger via:

```bash
curl -X POST https://web-production-816f6.up.railway.app/api/send-reminders
```

Set this up as a cron job:

**Railway cron** (recommended): Project → Settings → Cron Schedule
- Schedule: `0 * * * *` (hourly)
- Command: `curl -X POST $RAILWAY_PUBLIC_URL/api/send-reminders`

Or use **GitHub Actions**, **cron-job.org**, etc.

## Test scenarios

In `/console`, click **Demo** to wipe and seed 5 demo clients with bookings + a low-balance package on Marco. Useful for showing off the system to others.

For the practitioner side, login at `/practitioner` and try the "Comandi" tab:
- "mostra le prenotazioni di lunedì"
- "cancella le lezioni di Marco"
- "cancella tutto domani" (will require explicit confirmation)
