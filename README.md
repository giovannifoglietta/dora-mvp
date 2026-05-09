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

## Google Calendar — OAuth (recommended)

This is the right setup for production: each practitioner connects their own
Google Calendar with a single click. No JSON files, no calendar sharing.

### One-time GCP setup

1. **Create a GCP project** at <https://console.cloud.google.com/projectcreate>.
2. **Enable the Google Calendar API**: APIs & Services → Library → "Google Calendar API" → Enable.
3. **Configure the OAuth consent screen**:
   - APIs & Services → OAuth consent screen → User Type: **External** → Create.
   - App name: "Dora", support email: yours.
   - Add scopes: `auth/calendar`, `auth/userinfo.email`, `openid`.
   - Add yourself + a few testers as Test users (the consent screen stays in Testing
     mode until you submit for verification — fine up to 100 users).
4. **Create OAuth credentials**: APIs & Services → Credentials → **+ Create Credentials**
   → **OAuth client ID** → Application type: **Web application**.
   - Authorized redirect URIs: `<your-base-url>/practitioner/api/gcal/callback`
     (e.g. `https://web-production-816f6.up.railway.app/practitioner/api/gcal/callback`).
5. Copy the **Client ID** and **Client secret** into Railway env vars:
   - `GOOGLE_OAUTH_CLIENT_ID`
   - `GOOGLE_OAUTH_CLIENT_SECRET`
   - `GOOGLE_OAUTH_REDIRECT_URI` (same URI as in step 4)

### Practitioner flow (no setup, just one click)

1. Practitioner logs into `/practitioner` → **Impostazioni** tab.
2. Clicks **"Connetti Google Calendar"**.
3. Google's consent screen opens. They pick their account, approve.
4. They're back in Dora. They can choose which of their calendars to use.
5. Done. Every booking now syncs to their calendar.

## Google Calendar — Service account (legacy / single-tenant fallback)

For single-tenant testing, you can use a service account that owns a shared
calendar. This is what we used for Silvia's testing. Set:

- `GOOGLE_SERVICE_ACCOUNT_JSON` — the service-account JSON, base64-encoded
- `GOOGLE_CALENDAR_ID` — the calendar's ID

If a practitioner has connected via OAuth, that takes precedence. Otherwise the
service-account fallback is used. If neither is configured, calendar sync is a no-op.

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
